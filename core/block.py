import hashlib
import json
from typing import List, Optional
from dataclasses import dataclass
from core.transaction import Transaction

@dataclass
class Block:
    """Block structure similar to Bitcoin"""
    index: int
    timestamp: float
    transactions: List[Transaction]
    previous_hash: str
    nonce: int = 0
    hash: Optional[str] = None
    merkle_root: Optional[str] = None
    
    def __post_init__(self):
        if self.merkle_root is None:
            self.merkle_root = self.calculate_merkle_root()
        if self.hash is None:
            self.hash = self.calculate_hash()
    
    def calculate_merkle_root(self) -> str:
        """Calculate Merkle root of transactions"""
        if not self.transactions:
            return hashlib.sha256(b'').hexdigest()
        
        tx_hashes = [tx.txid for tx in self.transactions]
        
        if len(tx_hashes) % 2 != 0:
            tx_hashes.append(tx_hashes[-1])
        
        while len(tx_hashes) > 1:
            new_level = []
            for i in range(0, len(tx_hashes), 2):
                combined = tx_hashes[i] + tx_hashes[i + 1]
                new_hash = hashlib.sha256(combined.encode()).hexdigest()
                new_level.append(new_hash)
            tx_hashes = new_level
            if len(tx_hashes) % 2 != 0 and len(tx_hashes) > 1:
                tx_hashes.append(tx_hashes[-1])
        
        return tx_hashes[0]
    
    def calculate_hash(self) -> str:
        """Calculate block hash"""
        block_data = {
            'index': self.index,
            'timestamp': self.timestamp,
            'merkle_root': self.merkle_root,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce
        }
        block_string = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def mine_block(self, difficulty: int):
        """Proof of Work mining"""
        target = '0' * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()
        print(f"Block mined: {self.hash}")