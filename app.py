1. First, update app.py to pass a proper path:
python
import os
import sys

# Determine storage path
if 'RENDER' in os.environ:
    # Render - use /tmp/blockchain.json
    storage_path = '/tmp/blockchain.json'
else:
    # Local - use ./data/blockchain.json
    storage_path = './data/blockchain.json'

print(f"Storage path: {storage_path}")

# Now import Flask and other dependencies
from flask import Flask, jsonify, request
from flask_cors import CORS
from core.blockchain import Blockchain
from core.p2p import P2PNode

# Now create Flask app
app = Flask(__name__)
CORS(app)

# Initialize blockchain WITH explicit path
blockchain = Blockchain(storage_path=storage_path)

# Initialize P2P node
node = P2PNode("0.0.0.0", 5000, blockchain)

# Start P2P node in background
node.start()

# ... rest of your routes ...
2. Update blockchain.py init method:
Replace lines around the directory creation:

python
def __init__(self, difficulty: int = 5, storage_path: str = None, difficulty_interval: int = 10):
    # ... your existing code until storage_path assignment ...
    
    if storage_path is None:
        # Use environment variable or default
        storage_dir = os.environ.get('STORAGE_PATH', './data')
        self.storage_path = os.path.join(storage_dir, 'blockchain.json')
    else:
        self.storage_path = storage_path
    
    print(f"Blockchain storage path: {self.storage_path}")
    
    # FIXED: Safe directory creation
    try:
        # Get directory part
        dir_path = os.path.dirname(self.storage_path)
        
        # Only create if dir_path is not empty
        if dir_path and dir_path.strip():
            os.makedirs(dir_path, exist_ok=True)
            print(f"Created directory: {dir_path}")
        else:
            print(f"Note: No directory to create (using current directory)")
    except Exception as e:
        print(f"Warning: Directory creation failed: {e}")
        # Don't crash - continue with current directory
    
    # ... rest of your initialization ...
