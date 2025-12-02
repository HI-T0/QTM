import os
import time
from flask import Flask, jsonify, request
from flask_cors import CORS

# Determine storage path
if 'RENDER' in os.environ:
    # Render - use /tmp/blockchain.json
    storage_path = '/tmp/blockchain.json'
else:
    # Local - use ./data/blockchain.json
    storage_path = './data/blockchain.json'

print(f"Storage path: {storage_path}")

# Now import blockchain and p2p node (import after determining path)
from core.blockchain import Blockchain
from network.node import P2PNode
from core.transaction import Transaction

# Create Flask app
app = Flask(__name__)
CORS(app)

# Initialize blockchain WITH explicit path
blockchain = Blockchain(storage_path=storage_path)

# Initialize P2P node
node = P2PNode("0.0.0.0", 5000, blockchain)

# Start P2P node in background
node.start()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "name": "Quantum Blockchain API",
        "version": "1.0.0",
        "status": "running"
    }), 200

@app.route('/api/blockchain', methods=['GET'])
def get_blockchain():
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

@app.route('/api/block/<int:height>', methods=['GET'])
def get_block(height):
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

@app.route('/api/wallet-info', methods=['GET'])
def get_wallet_info():
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "address required"}), 400
    balance = blockchain.get_balance(address)
    return jsonify({"address": address, "balance": balance, "currency": "Quantum"}), 200

@app.route('/api/network-stats', methods=['GET'])
def get_network_stats():
    return jsonify({
        "difficulty": blockchain.difficulty,
        "base_difficulty": blockchain.base_difficulty,
        "chain_length": len(blockchain.chain),
        "pending_transactions": len(blockchain.pending_transactions),
        "connected_peers": len(node.peers),
        "mining_reward": blockchain.mining_reward
    }), 200

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.get_json() or {}
    from_addr = data.get('from')
    to_addr = data.get('to')
    amount = data.get('amount')
    if not from_addr or not to_addr or amount is None:
        return jsonify({"error": "from, to, amount required"}), 400
    # Create simple tx (unsigned) and queue it
    tx = Transaction(inputs=[], outputs=[{'address': to_addr, 'amount': amount}], timestamp=time.time())
    with node.lock:
        blockchain.add_transaction(tx)
    node.broadcast_transaction(tx)
    return jsonify({"result": "transaction queued", "txid": tx.txid}), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "chain_length": len(blockchain.chain)}), 200

# When running directly (or by gunicorn pointing to app:app), honor PORT env var
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8545))
    app.run(host="0.0.0.0", port=port, debug=False)
