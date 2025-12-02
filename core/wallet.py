import os
import json
import hashlib
import ecdsa
import base58

class Wallet:
    """Bitcoin-style wallet with ECDSA keys and on-disk persistence"""
    def __init__(self, storage_path: str = 'wallet.json'):
        # accept a simple filename by default; if no directory is present
        # use Render's temp path so deployments are safe.
        self.storage_path = storage_path

        # If no directory component provided (e.g. "wallet.json"), use /tmp on Render
        dir_path = os.path.dirname(self.storage_path)
        if not dir_path:
            # Use Render's temp directory as default for deployments
            self.storage_path = '/tmp/wallet.json'
            dir_path = os.path.dirname(self.storage_path)

        # Create directory only when there's a directory component
        if dir_path and dir_path.strip():
            os.makedirs(dir_path, exist_ok=True)

        # try to load existing keys, otherwise generate and save
        if os.path.exists(self.storage_path):
            try:
                self._load_from_file()
            except Exception:
                # fallback to fresh generation on any load error
                self._generate_new()
                self._save_to_file()
        else:
            self._generate_new()
            self._save_to_file()

    def _generate_new(self):
        self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = self.generate_address()

    def _save_to_file(self):
        """Persist private key (hex) to storage_path"""
        data = {
            'private_key_hex': self.private_key.to_string().hex()
        }
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def _load_from_file(self):
        """Load private key (hex) from storage_path and rebuild keys/address"""
        with open(self.storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        priv_hex = data.get('private_key_hex')
        if not priv_hex:
            raise ValueError("wallet file missing private_key_hex")
        priv_bytes = bytes.fromhex(priv_hex)
        self.private_key = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = self.generate_address()

    def generate_address(self) -> str:
        """Generate Bitcoin-style address from public key"""
        pub_key_bytes = self.public_key.to_string()
        sha256_hash = hashlib.sha256(pub_key_bytes).digest()
        ripemd160 = hashlib.new('ripemd160')
        ripemd160.update(sha256_hash)
        hashed_pub_key = ripemd160.digest()
        versioned = b'\x00' + hashed_pub_key
        checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
        address_bytes = versioned + checksum
        address = base58.b58encode(address_bytes).decode()
        return address

    def sign_transaction(self, tx_or_data) -> str:
        """
        Sign a transaction or raw string.
        - If a Transaction is provided, sign its txid (which is computed excluding signatures).
        - Otherwise sign the provided string.
        Returns signature hex.
        """
        if hasattr(tx_or_data, 'txid'):
            data = tx_or_data.txid
        else:
            data = str(tx_or_data)
        signature = self.private_key.sign(data.encode())
        return signature.hex()

    def get_public_key_hex(self) -> str:
        """Get public key as hex string"""
        return self.public_key.to_string().hex()

    # helpers for advanced use
    def export_private_key_hex(self) -> str:
        return self.private_key.to_string().hex()

    def import_private_key_hex(self, priv_hex: str, save: bool = True):
        priv_bytes = bytes.fromhex(priv_hex)
        self.private_key = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = self.generate_address()
        if save:
            self._save_to_file()

