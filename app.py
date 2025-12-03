import os
import json
import time
import uuid
import hashlib
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

# Determine storage path based on environment
if 'RENDER' in os.environ:
    storage_path = '/tmp/blockchain.json'
else:
    storage_path = './data/blockchain.json'

print(f"Storage path: {storage_path}")

from core.blockchain import Blockchain
from core.wallet import Wallet
from network.node import P2PNode
from core.transaction import Transaction

# Ensure data dirs
os.makedirs('./data', exist_ok=True)
os.makedirs('./data/wallets', exist_ok=True)

USERS_FILE = os.path.join('data', 'users.json')
SESSIONS_FILE = os.path.join('data', 'sessions.json')

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

users = load_json(USERS_FILE)
sessions = load_json(SESSIONS_FILE)  # token -> username

def hash_password(password: str, salt: bytes = None):
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex(), key.hex()

def verify_password(password: str, salt_hex: str, key_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return key.hex() == key_hex

def create_session(username: str) -> str:
    token = uuid.uuid4().hex
    sessions[token] = {'username': username, 'created': time.time()}
    save_json(SESSIONS_FILE, sessions)
    return token

def get_username_from_token(token: str):
    s = sessions.get(token)
    return s.get('username') if isinstance(s, dict) else None

# Create Flask app
app = Flask(__name__)
CORS(app)

# Add global CORS handling so frontend preflight/requests always receive headers
@app.before_request
def _handle_options_preflight():
	# Respond to OPTIONS preflight quickly (prevents 404 for unknown OPTIONS)
	if request.method == 'OPTIONS':
		resp = app.make_response(('', 200))
		resp.headers['Access-Control-Allow-Origin'] = '*'
		resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
		resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
		return resp

@app.after_request
def _add_cors_headers(response):
	# Ensure CORS headers present on every response
	response.headers.setdefault('Access-Control-Allow-Origin', '*')
	response.headers.setdefault('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
	response.headers.setdefault('Access-Control-Allow-Headers', 'Content-Type, Authorization')
	return response

# Initialize blockchain and node
blockchain = Blockchain(storage_path=storage_path)
# create a master CLI wallet only if needed
# wallet = Wallet()  # not used for user wallets here

node = P2PNode("0.0.0.0", 5000, blockchain)
node.start()

# ============ Mining Pool System ============

mining_pool = {}  # address -> {'shares': int, 'last_active': float, 'hashrate': int}
mining_lock = threading.Lock()
mining_active = False

def verify_light_puzzle(solution: dict) -> bool:
	"""Verify a light puzzle solution from browser miner"""
	try:
		nonce = solution.get('nonce')
		target_hash = solution.get('hash')
		difficulty = solution.get('difficulty', 3)
		
		# Verify hash format (simple check)
		if not isinstance(target_hash, str) or len(target_hash) != 64:
			return False
		
		# Verify hash starts with required zeros
		if not target_hash.startswith('0' * difficulty):
			return False
		
		# Verify nonce is reasonable
		if not isinstance(nonce, int) or nonce < 0 or nonce > 2**32:
			return False
		
		return True
	except Exception:
		return False

def distribute_mining_rewards(block):
	"""Distribute block rewards to mining pool members"""
	# explicit lock use (avoid context-manager on older Python)
	mining_lock.acquire()
	try:
		total_shares = sum(user.get('shares', 0) for user in mining_pool.values())
		if total_shares == 0:
			return
		
		block_reward = blockchain.mining_reward
		distributed = {}
		
		for address, user_data in mining_pool.items():
			user_share = user_data.get('shares', 0) / total_shares
			reward = user_share * block_reward
			distributed[address] = reward
			# Reset shares for next round
			user_data['shares'] = 0
		
		print(f"[MINING POOL] Distributed {block_reward} Quantum to {len(distributed)} miners")
		return distributed
	finally:
		mining_lock.release()

def mining_worker():
	"""Background mining thread that serves the pool"""
	global mining_active
	mining_active = True
	while mining_active:
		try:
			# explicit lock use
			mining_lock.acquire()
			try:
				if not mining_pool or len(mining_pool) == 0:
					# no miners, sleep and continue
					pass
				else:
					# Mine one block for the pool
					print(f"[MINING] Mining block for pool ({len(mining_pool)} miners)...")
					blockchain.mine_pending_transactions('MINING_POOL_REWARD')
					
					# Distribute rewards
					latest_block = blockchain.get_latest_block()
					distribute_mining_rewards(latest_block)
			finally:
				mining_lock.release()
			
			time.sleep(10)  # Mine/check every 10 seconds
			
		except Exception as e:
			print(f"[MINING ERROR] {e}")
			time.sleep(5)

# Start mining worker thread
mining_thread = threading.Thread(target=mining_worker, daemon=True)
mining_thread.start()

# ============ Authentication endpoints ============

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON body"}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if username in users:
        return jsonify({"error": "user exists"}), 400

    # create per-user wallet file
    wallet_path = os.path.join('data', 'wallets', f"{username}.json")
    user_wallet = Wallet(storage_path=wallet_path)  # generates and saves keys

    salt_hex, key_hex = hash_password(password)
    users[username] = {
        "salt": salt_hex,
        "key": key_hex,
        "wallet_path": wallet_path,
        "address": user_wallet.address,
        "created": time.time()
    }
    save_json(USERS_FILE, users)
    token = create_session(username)
    return jsonify({"result": "registered", "address": user_wallet.address, "token": token}), 201

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON body"}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    user = users.get(username)
    if not user:
        return jsonify({"error": "invalid credentials"}), 401
    if not verify_password(password, user['salt'], user['key']):
        return jsonify({"error": "invalid credentials"}), 401
    token = create_session(username)
    return jsonify({"result": "ok", "token": token, "address": user.get('address')}), 200

def get_authenticated_username():
    # check Authorization: Bearer <token> or ?token=
    auth = request.headers.get('Authorization', '')
    token = None
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1].strip()
    if not token:
        token = request.args.get('token') or request.json.get('token') if request.is_json else None
    return get_username_from_token(token) if token else None

# ============ Existing API endpoints (updated to use auth) ============

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "name": "Quantum Blockchain API",
        "version": "1.0.0",
        "status": "running"
    }), 200

@app.route('/api/blockchain', methods=['GET'])
def api_blockchain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append({
            'index': block.index,
            'timestamp': block.timestamp,
            'transactions': len(block.transactions),
            'hash': block.hash,
            'previous_hash': block.previous_hash,
            'nonce': block.nonce,
            'merkle_root': block.merkle_root
        })
    return jsonify({"blocks": chain_data, "length": len(chain_data)}), 200

@app.route('/api/latest-blocks', methods=['GET'])
def api_latest_blocks():
    try:
        limit = int(request.args.get('limit', 5))
        limit = max(1, min(limit, 100))
    except (ValueError, TypeError):
        limit = 5
    start_idx = max(0, len(blockchain.chain) - limit)
    chain_data = []
    for block in blockchain.chain[start_idx:]:
        chain_data.append({
            'index': block.index,
            'hash': block.hash[:20] + '...',
            'timestamp': block.timestamp,
            'transactions': len(block.transactions)
        })
    return jsonify(chain_data), 200

@app.route('/api/wallet-info', methods=['GET'])
def api_wallet_info():
    # If authenticated, return user's wallet; else accept ?address=
    username = get_authenticated_username()
    if username:
        user = users.get(username)
        if not user:
            return jsonify({"error": "user not found"}), 404
        address = user.get('address')
        bal = blockchain.get_balance(address)
        return jsonify({"address": address, "balance": bal, "status": "online", "user": username}), 200
    # fallback to public lookup
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "address required or login with token"}), 400
    bal = blockchain.get_balance(address)
    return jsonify({"address": address, "balance": bal}), 200

@app.route('/api/network-stats', methods=['GET'])
def api_network_stats():
    return jsonify({
        'difficulty': blockchain.difficulty,
        'base_difficulty': blockchain.base_difficulty,
        'total_blocks': len(blockchain.chain),
        'total_transactions': sum(len(b.transactions) for b in blockchain.chain),
        'pending_transactions': len(blockchain.pending_transactions),
        'connected_peers': len(node.peers),
        'status': 'active'
    }), 200

@app.route('/api/block/<int:height>', methods=['GET'])
def api_get_block(height):
    if height < 0 or height >= len(blockchain.chain):
        return jsonify({"error": "block not found"}), 404
    block = blockchain.chain[height]
    return jsonify({
        'index': block.index,
        'timestamp': block.timestamp,
        'transactions': [tx.to_dict() for tx in block.transactions],
        'hash': block.hash,
        'previous_hash': block.previous_hash,
        'nonce': block.nonce,
        'merkle_root': block.merkle_root
    }), 200

@app.route('/api/send', methods=['POST'])
def api_send():
    username = get_authenticated_username()
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON body"}), 400
    
    to_addr = data.get('to', '').strip()
    amount = data.get('amount')
    
    if not to_addr or amount is None:
        return jsonify({"error": "to and amount required"}), 400

    if username:
        user = users.get(username)
        wallet_path = user.get('wallet_path')
        if not wallet_path or not os.path.exists(wallet_path):
            return jsonify({"error": "wallet missing"}), 500
        user_wallet = Wallet(storage_path=wallet_path)
        tx = blockchain.create_transaction(user_wallet, to_addr, float(amount))
        if tx is None:
            return jsonify({"error": "insufficient funds"}), 400
        with node.lock:
            blockchain.add_transaction(tx)
        node.broadcast_transaction(tx)
        return jsonify({"result": "tx queued", "txid": tx.txid}), 200
    else:
        # allow anonymous unsigned tx (will be accepted as non-spendable unless protocol allows)
        tx = Transaction(inputs=[], outputs=[{'address': to_addr, 'amount': float(amount)}], timestamp=time.time())
        with node.lock:
            blockchain.add_transaction(tx)
        node.broadcast_transaction(tx)
        return jsonify({"result": "tx queued (unsigned)", "txid": tx.txid}), 200

@app.route('/api/register', methods=['GET'])
def api_info():
    return jsonify({"note": "POST /api/register with username & password to create account"}), 200

# ============ Mining Pool Endpoints ============

@app.route('/api/mining/start', methods=['POST'])
def start_mining():
	"""User joins mining pool"""
	try:
		data = request.get_json(silent=True) or {}
	except Exception:
		return jsonify({"error": "invalid JSON body"}), 400
	
	# Accept both 'address' and 'walletAddress' (frontend compat)
	address = (data.get('address') or data.get('walletAddress') or '').strip()
	if not address:
		return jsonify({"error": "address or walletAddress required"}), 400
	
	mining_lock.acquire()
	try:
		if address not in mining_pool:
			mining_pool[address] = {'shares': 0, 'last_active': time.time(), 'hashrate': 0}
		mining_pool[address]['last_active'] = time.time()
	finally:
		mining_lock.release()
	
	return jsonify({
		"message": f"Joined mining pool",
		"address": address[:10] + "...",
		"pool_size": len(mining_pool),
		"estimated_reward": f"{blockchain.mining_reward} Quantum/block"
	}), 200

@app.route('/api/mining/stop', methods=['POST'])
def stop_mining():
	"""User leaves mining pool"""
	try:
		data = request.get_json(silent=True) or {}
	except Exception:
		return jsonify({"error": "invalid JSON body"}), 400
	
	# Accept both 'address' and 'walletAddress' (frontend compat)
	address = (data.get('address') or data.get('walletAddress') or '').strip()
	if not address:
		return jsonify({"error": "address or walletAddress required"}), 400
	
	mining_lock.acquire()
	try:
		if address in mining_pool:
			del mining_pool[address]
	finally:
		mining_lock.release()
	
	return jsonify({"message": "Left mining pool"}), 200

@app.route('/api/mining/submit-work', methods=['POST'])
def submit_work():
	"""User submits browser mining proof"""
	try:
		data = request.get_json(silent=True) or {}
	except Exception:
		return jsonify({"error": "invalid JSON body"}), 400
	
	# Accept both 'address' and 'walletAddress' (frontend compat)
	address = (data.get('address') or data.get('walletAddress') or '').strip()
	solution = data.get('solution')
	if not address or not solution:
		return jsonify({"error": "address/walletAddress and solution required"}), 400
	
	if not verify_light_puzzle(solution):
		return jsonify({"success": False, "error": "Invalid solution"}), 400
	
	mining_lock.acquire()
	try:
		if address in mining_pool:
			mining_pool[address]['shares'] = mining_pool[address].get('shares', 0) + 1
			mining_pool[address]['last_active'] = time.time()
			shares = mining_pool[address]['shares']
		else:
			return jsonify({"error": "Not in mining pool"}), 400
	finally:
		mining_lock.release()
	
	return jsonify({
		"success": True,
		"message": "Work accepted!",
		"shares": shares,
		"total_pool_shares": sum(u.get('shares', 0) for u in mining_pool.values())
	}), 200

@app.route('/api/mining/stats', methods=['GET'])
def mining_stats():
	"""Get mining pool statistics"""
	mining_lock.acquire()
	try:
		total_shares = sum(user.get('shares', 0) for user in mining_pool.values())
		active_miners = [
			{
				'address': addr[:10] + '...',
				'shares': data.get('shares', 0),
				'share_percent': f"{(data.get('shares', 0) / total_shares * 100):.1f}%" if total_shares > 0 else "0%"
			}
			for addr, data in list(mining_pool.items())
		]
	finally:
		mining_lock.release()
	
	return jsonify({
		'pool_size': len(mining_pool),
		'total_shares': total_shares,
		'active_miners': active_miners,
		'current_block': len(blockchain.chain),
		'block_reward': blockchain.mining_reward,
		'next_block_in': '~10 seconds'
	}), 200

@app.route('/api/mining/user-stats', methods=['GET'])
def user_mining_stats():
	"""Get specific user's mining stats"""
	address = request.args.get('address')
	if not address:
		return jsonify({"error": "address required"}), 400
	
	mining_lock.acquire()
	try:
		if address not in mining_pool:
			return jsonify({"error": "Not mining"}), 404
		
		user_data = mining_pool[address]
		total_shares = sum(u.get('shares', 0) for u in mining_pool.values())
		user_shares = user_data.get('shares', 0)
		user_percent = (user_shares / total_shares * 100) if total_shares > 0 else 0
		estimated = (user_shares / total_shares * blockchain.mining_reward) if total_shares > 0 else 0
	finally:
		mining_lock.release()
	
	return jsonify({
		'address': address[:10] + '...',
		'shares': user_shares,
		'share_percentage': f'{user_percent:.2f}%',
		'estimated_reward': f'{estimated:.2f} Quantum',
		'active_seconds': int(time.time() - user_data.get('last_active', time.time()))
	}), 200

# ============ Compatibility endpoints for frontend ============
# These map old frontend paths to the current mining endpoints.

@app.route('/api/mining-stats', methods=['GET'])
def api_mining_stats_compat():
    # reuse existing mining_stats logic
    return mining_stats()

@app.route('/api/pool-info', methods=['GET'])
def api_pool_info_compat():
    # brief pool summary expected by frontend
    mining_lock.acquire()
    try:
        total_shares = sum(u.get('shares', 0) for u in mining_pool.values())
        members = [{'address': addr, 'shares': data.get('shares', 0)} for addr, data in mining_pool.items()]
    finally:
        mining_lock.release()
    return jsonify({
        'pool_size': len(mining_pool),
        'total_shares': total_shares,
        'members': members,
        'current_block': len(blockchain.chain),
        'block_reward': blockchain.mining_reward
    }), 200

@app.route('/api/mining-start', methods=['POST'])
def api_mining_start_compat():
    """Legacy endpoint (accepts walletAddress from frontend)"""
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON body"}), 400

    # Accept both 'address' and 'walletAddress' (frontend compat)
    address = (data.get('address') or data.get('walletAddress') or '').strip()
    if not address:
        return jsonify({"error": "address or walletAddress required"}), 400

    mining_lock.acquire()
    try:
        if address not in mining_pool:
            mining_pool[address] = {'shares': 0, 'last_active': time.time(), 'hashrate': 0}
        mining_pool[address]['last_active'] = time.time()
    finally:
        mining_lock.release()

    return jsonify({
        'message': f'Joined mining pool',
        'address': address[:10] + '...',
        'pool_size': len(mining_pool),
        'estimated_reward': f"{blockchain.mining_reward} Quantum/block"
    }), 200

# ============ Error handlers ============
@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": "endpoint not found"}), 404

@app.errorhandler(415)
def unsupported_media_type(err):
    return jsonify({"error": "unsupported media type (use Content-Type: application/json)"}), 415

@app.errorhandler(500)
def server_error(err):
    return jsonify({"error": "internal server error"}), 500

# Add global request validation for JSON POST/PUT requests
@app.before_request
def validate_json_request():
    """Ensure POST/PUT requests have proper Content-Type"""
    if request.method in ('POST', 'PUT'):
        # Allow empty body (some POST endpoints may not need it)
        if request.content_length and request.content_length > 0:
            # If body exists, require JSON content-type
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 415

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8545))
    app.run(host="0.0.0.0", port=port, debug=False)
