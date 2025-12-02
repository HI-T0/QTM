import os
import sys
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from core.blockchain import Blockchain
from network.node import P2PNode

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set environment variables for Render
if 'RENDER' in os.environ:
    # Render-specific settings
    os.environ['STORAGE_PATH'] = '/tmp/blockchain_data'
else:
    # Local development
    os.environ['STORAGE_PATH'] = './blockchain_data'

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize blockchain and node (singleton pattern)
blockchain = Blockchain()
node = P2PNode("0.0.0.0", 5000, blockchain)

# Start P2P node in background
node.start()

# Start API in background (optional, Flask already serves)
# node.start_api(api_port=8545)

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return jsonify({
        "name": "Quantum Blockchain API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "blockchain": "/api/blockchain",
            "block": "/api/block/<height>",
            "wallet_info": "/api/wallet-info?address=<addr>",
            "network_stats": "/api/network-stats",
            "balance": "/balance?address=<addr>",
            "chain": "/chain",
            "send": "POST /api/send"
        }
    }), 200

@app.route('/api/blockchain', methods=['GET'])
def get_blockchain():
    """Get all blocks in chain"""
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

@app.route('/api/wallet-info', methods=['GET'])
def get_wallet_info():
    """Get wallet info and balance"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "address required"}), 400
    
    balance = blockchain.get_balance(address)
    return jsonify({
        "address": address,
        "balance": balance,
        "currency": "Quantum"
    }), 200

@app.route('/balance', methods=['GET'])
def get_balance():
    """Legacy balance endpoint"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "address required"}), 400
    
    balance = blockchain.get_balance(address)
    return jsonify({"address": address, "balance": balance}), 200

@app.route('/api/network-stats', methods=['GET'])
def get_network_stats():
    """Get network statistics"""
    return jsonify({
        "difficulty": blockchain.difficulty,
        "base_difficulty": blockchain.base_difficulty,
        "chain_length": len(blockchain.chain),
        "pending_transactions": len(blockchain.pending_transactions),
        "connected_peers": len(node.peers),
        "mining_reward": blockchain.mining_reward
    }), 200

@app.route('/chain', methods=['GET'])
def get_chain():
    """Get full blockchain"""
    chain_data = []
    for block in blockchain.chain:
        chain_data.append({
            'index': block.index,
            'timestamp': block.timestamp,
            'transactions': [tx.to_dict() for tx in block.transactions],
            'previous_hash': block.previous_hash,
            'nonce': block.nonce,
            'hash': block.hash,
            'merkle_root': block.merkle_root
        })
    return jsonify({"chain": chain_data}), 200

@app.route('/peers', methods=['GET'])
def get_peers():
    """Get connected peers"""
    return jsonify({
        "peers": [{'host': p.host, 'port': p.port} for p in node.peers],
        "count": len(node.peers)
    }), 200

@app.route('/status', methods=['GET'])
def get_status():
    """Get node status"""
    return jsonify({"status": node.get_status()}), 200

@app.route('/api/send', methods=['POST'])
def send_transaction():
    """Send a transaction"""
    from core.transaction import Transaction
    
    data = request.get_json()
    from_addr = data.get('from')
    to_addr = data.get('to')
    amount = data.get('amount')
    
    if not from_addr or not to_addr or amount is None:
        return jsonify({"error": "from, to, amount required"}), 400
    
    tx = Transaction(
        inputs=[],
        outputs=[{'address': to_addr, 'amount': amount}],
        timestamp=time.time()
    )
    
    with node.lock:
        blockchain.add_transaction(tx)
    
    node.broadcast_transaction(tx)
    return jsonify({"result": "transaction queued", "txid": tx.txid}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "chain_length": len(blockchain.chain)}), 200

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8545))
    app.run(host="0.0.0.0", port=port, debug=False)
