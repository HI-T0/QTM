import time
import os
import json
import statistics
from typing import List, Dict, Optional, Tuple
from core.block import Block
from core.transaction import Transaction

class Blockchain:
    """Main blockchain class"""
    def __init__(self, difficulty: int = 5, storage_path: str = None, difficulty_interval: int = 10):
        # difficulty parameter kept for backward-compatibility and is treated as base difficulty
        self.chain: List[Block] = []
        self.base_difficulty = difficulty  # base difficulty (will be adjusted as chain grows)
        self.difficulty_interval = max(1, difficulty_interval)  # increase difficulty every N blocks
        self.pending_transactions: List[Transaction] = []
        self.mining_reward = 10.2  # Quantum reward per block
        self.utxo_set: Dict[str, List[Dict]] = {}
        self.mining_cancel = False  # flag to cancel mining

        # Determine storage_path safely
        if storage_path is None:
            storage_dir = os.environ.get('STORAGE_PATH', './data')
            self.storage_path = os.path.join(storage_dir, 'blockchain.json')
        else:
            self.storage_path = storage_path

        print(f"Blockchain storage path: {self.storage_path}")

        # FIXED: Safe directory creation
        try:
            dir_path = os.path.dirname(self.storage_path)
            if dir_path and dir_path.strip():
                os.makedirs(dir_path, exist_ok=True)
                print(f"Created directory: {dir_path}")
            else:
                print("Note: No directory to create (using current directory)")
        except Exception as e:
            print(f"Warning: Directory creation failed: {e}")

        # load existing chain if present, otherwise create genesis and save
        if os.path.exists(self.storage_path):
            try:
                self.load_from_file()
                print(f"Loaded blockchain from {self.storage_path}")
            except Exception:
                # fallback create genesis
                self.create_genesis_block()
                self.save_to_file()
        else:
            self.create_genesis_block()
            self.save_to_file()

    # New property: current difficulty (increases with chain length)
    @property
    def difficulty(self) -> int:
        """
        Current proof-of-work difficulty.
        Computed as: base_difficulty + floor(chain_length / difficulty_interval)
        This makes hashing harder as more blocks are mined.
        """
        # len(self.chain) is chain length; we avoid reducing below 1
        return max(1, int(self.base_difficulty + (len(self.chain) // self.difficulty_interval)))

    def create_genesis_block(self):
        """Create the first block"""
        genesis_tx = Transaction(
            inputs=[],
            outputs=[{'address': 'genesis', 'amount': 0}],
            timestamp=time.time()
        )
        genesis_block = Block(
            index=0,
            timestamp=time.time(),
            transactions=[genesis_tx],
            previous_hash='0',
            nonce=0
        )
        genesis_block.mine_block(self.difficulty)
        self.chain.append(genesis_block)
        # update UTXO set for genesis outputs
        self.update_utxo_set(genesis_block)
        print(f"Genesis block created: {genesis_block.hash}")
    
    def get_latest_block(self) -> Block:
        """Get the last block in the chain"""
        return self.chain[-1]
    
    def add_transaction(self, transaction: Transaction) -> bool:
        """Add transaction to pending pool"""
        self.pending_transactions.append(transaction)
        return True
    
    def get_pending_transactions_count(self) -> int:
        """Get count of pending transactions waiting to be mined"""
        return len(self.pending_transactions)

    # New helper: median of timestamps of up to previous 11 blocks
    def median_time_past(self, index: int) -> float:
        """
        Returns median timestamp of up to 11 blocks prior to block at `index`.
        If there are no previous blocks, returns 0.
        """
        if index <= 0:
            return 0.0
        start = max(0, index - 11)
        times = [self.chain[i].timestamp for i in range(start, index)]
        if not times:
            return 0.0
        return float(statistics.median(times))

    # New helper: validate a single block timestamp against rules
    def is_block_timestamp_valid(self, block: Block) -> bool:
        """
        Checks:
          - Not more than 2 hours in the future (relative to local clock)
          - Not earlier than median time past of previous 11 blocks
        """
        now = time.time()
        # Rule: cannot be more than 2 hours in the future
        if block.timestamp > now + 2 * 3600:
            print(f"Block {getattr(block,'index', 'N/A')} rejected: timestamp too far in future ({block.timestamp} > {now + 2*3600})")
            return False

        # If the block has an index and we have previous blocks, check median rule
        try:
            idx = block.index
        except Exception:
            # If no index, can't perform median check - accept for now
            return True

        if idx > 0 and len(self.chain) > 0:
            median = self.median_time_past(idx)
            if median and block.timestamp < median:
                print(f"Block {idx} rejected: timestamp {block.timestamp} < median past {median}")
                return False

        return True

    def mine_pending_transactions(self, mining_reward_address: str):
        """
        Mine a new block with pending transactions.
        Steps:
          1. Check for pending transactions
          2. Create a new block with coinbase + pending txs
          3. Solve Proof-of-Work puzzle (find nonce)
          4. Add block to chain and update UTXO
        """
        self.mining_cancel = False

        # Step 1: Check pending transactions
        pending_count = self.get_pending_transactions_count()
        print(f"\n[STEP 1] Checking pending transactions... Found: {pending_count}")

        # Step 2: Create a new block
        print(f"[STEP 2] Creating new block...")
        coinbase_tx = Transaction(
            inputs=[],
            outputs=[{'address': mining_reward_address, 'amount': self.mining_reward}],
            timestamp=time.time()
        )

        transactions = [coinbase_tx] + self.pending_transactions

        # Set block timestamp at start of mining (reflects mining start)
        new_block = Block(
            index=len(self.chain),
            timestamp=time.time(),
            transactions=transactions,
            previous_hash=self.get_latest_block().hash
        )
        print(f"[STEP 2] Block #{new_block.index} created with {len(transactions)} transaction(s)")

        # Step 3: Solve Proof-of-Work puzzle
        print(f"[STEP 3] Solving Proof-of-Work puzzle (difficulty: {self.difficulty})...")
        print(f"         Mining block {new_block.index}...")
        new_block.mine_block(self.difficulty)

        if self.mining_cancel:
            print("[STEP 3] Mining cancelled!")
            return

        print(f"[STEP 3] ✓ Puzzle solved! Hash: {new_block.hash}")

        # Step 4: Add block to chain
        print(f"[STEP 4] Adding block to chain...")
        self.chain.append(new_block)
        self.update_utxo_set(new_block)
        self.pending_transactions = []

        # persist chain after successful mining
        try:
            self.save_to_file()
        except Exception:
            pass

        print(f"[STEP 4] ✓ Block #{new_block.index} added to blockchain!")
        print(f"         Chain length: {len(self.chain)}")
        print(f"         Reward: {self.mining_reward} Quantum")

    def cancel_mining(self):
        """Request mining to stop (sets cancel flag)"""
        self.mining_cancel = True

    def update_utxo_set(self, block: Block):
        """Update unspent transaction outputs"""
        for tx in block.transactions:
            for inp in tx.inputs:
                if inp.get('txid') in self.utxo_set:
                    vout = inp.get('vout')
                    if vout < len(self.utxo_set[inp['txid']]):
                        self.utxo_set[inp['txid']][vout] = None
            # store copies of outputs to avoid external mutation
            self.utxo_set[tx.txid] = [dict(o) for o in tx.outputs]
    
    def get_balance(self, address: str) -> float:
        """Get balance for an address"""
        balance = 0
        for txid, outputs in self.utxo_set.items():
            for output in outputs:
                if output and output.get('address') == address:
                    balance += output.get('amount', 0)
        return balance

    # New: find spendable outputs (simple greedy selection)
    def find_spendable_outputs(self, address: str, amount: float) -> Tuple[float, Dict[str, List[int]]]:
        """
        Find unspent outputs for an address to cover amount.
        Returns (accumulated, {txid: [vout indices]})
        """
        accumulated = 0.0
        used: Dict[str, List[int]] = {}
        for txid, outputs in self.utxo_set.items():
            for idx, out in enumerate(outputs):
                if out and out.get('address') == address:
                    if txid not in used:
                        used[txid] = []
                    used[txid].append(idx)
                    accumulated += out.get('amount', 0)
                    if accumulated >= amount:
                        return accumulated, used
        return accumulated, used

    # New: create a transaction from a Wallet instance (signs inputs)
    def create_transaction(self, wallet, to_address: str, amount: float) -> Optional[Transaction]:
        """
        Build and sign a transaction sending `amount` from wallet.address to to_address.
        - Performs simple coin selection (no fees).
        - Returns Transaction if successful, otherwise None.
        """
        # find enough UTXOs
        acc, used = self.find_spendable_outputs(wallet.address, amount)
        if accumb := acc < amount:  # brief quick-check variable for readability
            # insufficient funds
            return None

        # build inputs (without signatures yet) using wallet's public key
        pubkey_hex = wallet.get_public_key_hex()
        inputs = []
        for txid, vouts in used.items():
            for v in vouts:
                inputs.append({'txid': txid, 'vout': v, 'pubkey': pubkey_hex})

        # build outputs: recipient and change
        outputs = [{'address': to_address, 'amount': amount}]
        change = accumb if False else (acc - amount)  # placeholder; accumb unused
        if change > 0:
            outputs.append({'address': wallet.address, 'amount': change})

        # create transaction object (signatures excluded from txid)
        tx = Transaction(inputs=inputs, outputs=outputs, timestamp=time.time())

        # sign transaction (sign txid) and attach signature to all inputs
        sig_hex = wallet.sign_transaction(tx)
        for inp in tx.inputs:
            inp['signature'] = sig_hex

        # txid remains stable (signatures excluded by design)
        return tx

    def is_chain_valid(self) -> bool:
        """Validate entire blockchain"""
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i - 1]

            # Timestamp rules: reject if too far in future or earlier than median past
            if not self.is_block_timestamp_valid(current_block):
                print(f"Invalid timestamp at block {i}")
                return False

            if current_block.hash != current_block.calculate_hash():
                print(f"Invalid hash at block {i}")
                return False
            
            if current_block.previous_hash != previous_block.hash:
                print(f"Invalid previous hash at block {i}")
                return False
            
            if not current_block.hash.startswith('0' * self.difficulty):
                print(f"Invalid proof of work at block {i}")
                return False

        # Also check genesis timestamp isn't absurdly in the future
        if len(self.chain) > 0 and not self.is_block_timestamp_valid(self.chain[0]):
            print("Invalid genesis timestamp")
            return False

        return True
    
    def print_chain(self):
        """Display blockchain info"""
        print("\n" + "="*60)
        print("BLOCKCHAIN STATUS")
        print("="*60)
        for block in self.chain:
            print(f"\nBlock #{block.index}")
            print(f"Timestamp: {time.ctime(block.timestamp)}")
            print(f"Transactions: {len(block.transactions)}")
            print(f"Hash: {block.hash}")
            print(f"Previous Hash: {block.previous_hash}")
            print(f"Nonce: {block.nonce}")
            print(f"Merkle Root: {block.merkle_root}")
        print("\n" + "="*60)

    # Persistence helpers
    def save_to_file(self):
        """Serialize chain and utxo_set to disk"""
        data = {
            'chain': [],
            'utxo_set': self.utxo_set
        }
        for block in self.chain:
            block_dict = {
                'index': block.index,
                'timestamp': block.timestamp,
                'transactions': [tx.to_dict() for tx in block.transactions],
                'previous_hash': block.previous_hash,
                'nonce': block.nonce,
                'hash': block.hash,
                'merkle_root': block.merkle_root
            }
            data['chain'].append(block_dict)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def load_from_file(self):
        """Load blockchain and rebuild UTXO set from disk"""
        with open(self.storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        new_chain = []
        for block_dict in data.get('chain', []):
            transactions = []
            for tx_dict in block_dict['transactions']:
                tx = Transaction(
                    inputs=tx_dict.get('inputs', []),
                    outputs=tx_dict.get('outputs', []),
                    timestamp=tx_dict.get('timestamp', time.time()),
                    txid=tx_dict.get('txid')
                )
                transactions.append(tx)
            block = Block(
                index=block_dict['index'],
                timestamp=block_dict['timestamp'],
                transactions=transactions,
                previous_hash=block_dict['previous_hash'],
                nonce=block_dict.get('nonce', 0),
                hash=block_dict.get('hash'),
                merkle_root=block_dict.get('merkle_root')
            )
            new_chain.append(block)
        self.chain = new_chain
        # rebuild utxo set from chain to ensure consistency
        self.utxo_set = {}
        for block in self.chain:
            self.update_utxo_set(block)
