import hashlib
import json
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import ecdsa
import base58

@dataclass
class Transaction:
    """UTXO-based transaction"""
    inputs: List[Dict]  # [{txid, vout, signature, pubkey}]
    outputs: List[Dict]  # [{address, amount}]
    timestamp: float
    txid: Optional[str] = None
    
    def __post_init__(self):
        if self.txid is None:
            self.txid = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate transaction ID (exclude signatures so txid is stable)"""
        # exclude 'signature' fields when computing txid
        inputs_clean = []
        for inp in self.inputs:
            inputs_clean.append({k: v for k, v in inp.items() if k != 'signature'})
        tx_data = {
            'inputs': inputs_clean,
            'outputs': self.outputs,
            'timestamp': self.timestamp
        }
        tx_string = json.dumps(tx_data, sort_keys=True)
        return hashlib.sha256(tx_string.encode()).hexdigest()
    
    @staticmethod
    def pubkey_to_address(pubkey_hex: str) -> str:
        """Convert a raw public key hex to a Base58 address (same scheme as Wallet)"""
        pub_key_bytes = bytes.fromhex(pubkey_hex)
        sha256_hash = hashlib.sha256(pub_key_bytes).digest()
        ripemd160 = hashlib.new('ripemd160')
        ripemd160.update(sha256_hash)
        hashed_pub_key = ripemd160.digest()
        versioned = b'\x00' + hashed_pub_key
        checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
        address_bytes = versioned + checksum
        return base58.b58encode(address_bytes).decode()
    
    def verify(self, utxo_set: Dict[str, List[Dict]]) -> bool:
        """
        Verify this transaction:
        - For each input, signature verifies against the txid (calculated without signatures)
        - Referenced UTXO exists and address matches the provided pubkey
        """
        # compute the message that should have been signed (txid computed excluding signatures)
        message = self.calculate_hash().encode()
        for inp in self.inputs:
            txid = inp.get('txid')
            vout = inp.get('vout')
            sig_hex = inp.get('signature')
            pubkey_hex = inp.get('pubkey')
            if txid is None or vout is None:
                return False
            # coinbase / reward txs may have empty inputs
            if sig_hex is None or pubkey_hex is None:
                return False
            # ensure referenced utxo exists and not spent
            outputs = utxo_set.get(txid)
            if outputs is None or vout >= len(outputs):
                return False
            ref_out = outputs[vout]
            if ref_out is None:
                # already spent
                return False
            # check address derived from pubkey matches referenced output address
            derived_addr = Transaction.pubkey_to_address(pubkey_hex)
            if derived_addr != ref_out.get('address'):
                return False
            # verify signature
            try:
                vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(pubkey_hex), curve=ecdsa.SECP256k1)
                vk.verify(bytes.fromhex(sig_hex), message)
            except Exception:
                return False
        return True
    
    def to_dict(self) -> Dict:
        return asdict(self)