import os
import json
import time
import uuid
import hashlib
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

# Initialize blockchain and node
blockchain = Blockchain(storage_path=storage_path)
# create a master CLI wallet only if needed
# wallet = Wallet()  # not used for user wallets here

node = P2PNode("0.0.0.0", 5000, blockchain)
node.start()

# ============ Authentication endpoints ============

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
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
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
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
    # Require authentication to send from user's wallet (auto sign)
    username = get_authenticated_username()
    data = request.get_json() or {}
    to_addr = data.get('to')
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

# Error handlers
@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": "endpoint not found"}), 404

@app.errorhandler(500)
def server_error(err):
    return jsonify({"error": "internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8545))
    app.run(host="0.0.0.0", port=port, debug=False)
