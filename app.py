import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS

# Determine storage path based on environment
if 'RENDER' in os.environ:
    storage_path = '/tmp/blockchain.json'
else:
    storage_path = './data/blockchain.json'

print(f"Storage path: {storage_path}")

# Import after path is set
from core.blockchain import Blockchain
from core.wallet import Wallet
from network.node import P2PNode

# Create Flask app
app = Flask(__name__)
CORS(app)

# Initialize blockchain and node
blockchain = Blockchain(storage_path=storage_path)
wallet = Wallet()
node = P2PNode("0.0.0.0", 5000, blockchain)
node.start()

print(f"Wallet Address: {wallet.address}")

# ============ API ENDPOINTS ============

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "name": "Quantum Blockchain API",
        "version": "1.0.0",
        "wallet": wallet.address,
        "status": "online"
    }), 200

@app.route('/api/blockchain', methods=['GET'])
def api_blockchain():
    """Get entire blockchain"""
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
    """Get last N blocks (default 5)"""
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
    """Get wallet info and balance"""
    balance = blockchain.get_balance(wallet.address)
    return jsonify({
        'address': wallet.address,
        'balance': balance,
        'status': 'online',
        'currency': 'Quantum'
    }), 200

@app.route('/api/network-stats', methods=['GET'])
def api_network_stats():
    """Get network statistics"""
    return jsonify({
        'difficulty': blockchain.difficulty,
        'base_difficulty': blockchain.base_difficulty,
        'total_blocks': len(blockchain.chain),
        'total_transactions': sum(len(b.transactions) for b in blockchain.chain),
        'pending_transactions': len(blockchain.pending_transactions),
        'connected_peers': len(node.peers),
        'mining_reward': blockchain.mining_reward,
        'status': 'active'
    }), 200

@app.route('/api/block/<int:height>', methods=['GET'])
def api_get_block(height):
    """Get specific block by height"""
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

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "endpoint not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8545))
    app.run(host="0.0.0.0", port=port, debug=False)
