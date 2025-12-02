import socket
import threading
import time
import json
from typing import Set, List, Dict
from core.blockchain import Blockchain
from core.block import Block
from core.transaction import Transaction
from network.peer import Peer
from network.message import Message

class P2PNode:
    """Peer-to-peer network node"""
    
    def __init__(self, host: str, port: int, blockchain: Blockchain):
        self.host = host
        self.port = port
        self.blockchain = blockchain
        self.peers: Set[Peer] = set()
        self.server_socket = None
        self.running = False
        self.lock = threading.Lock()
        self.seen_blocks: Set[str] = set()
        self.seen_transactions: Set[str] = set()
        self.api_running = False
        print(f"Node initialized at {self.host}:{self.port}")
    
    def start(self):
        """Start the P2P node server"""
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"Node listening on {self.host}:{self.port}")
            
            accept_thread = threading.Thread(target=self._accept_connections)
            accept_thread.daemon = True
            accept_thread.start()
            
        except Exception as e:
            print(f"Error starting node: {e}")
            self.running = False
    
    def stop(self):
        """Stop the P2P node"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        try:
            self.blockchain.save_to_file()
        except Exception:
            pass
        print(f"Node stopped at {self.host}:{self.port}")
    
    def _accept_connections(self):
        """Accept incoming peer connections"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"Connection from {address}")
                peer_thread = threading.Thread(
                    target=self._handle_peer,
                    args=(client_socket, address)
                )
                peer_thread.daemon = True
                peer_thread.start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
    
    def _handle_peer(self, client_socket: socket.socket, address):
        """Handle messages from a connected peer"""
        try:
            while self.running:
                data = client_socket.recv(65536)
                
                if not data:
                    print(f"Peer {address} closed connection")
                    break
                
                # Decode and strip first, before any JSON parsing
                try:
                    data_str = data.decode('utf-8', errors='ignore').strip()
                except Exception as e:
                    print(f"[DEBUG] Decode error from {address}: {str(e)[:50]}...")
                    break
                
                # Skip empty messages early (before JSON parse attempt)
                if not data_str:
                    continue
                
                # Now attempt JSON parsing
                try:
                    message = Message.from_json(data_str)
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] Invalid JSON from {address}: {str(e)[:50]}...")
                    break
                except Exception as e:
                    print(f"[DEBUG] Message parse error from {address}: {str(e)[:50]}...")
                    break
                
                # If we got here, message is valid—process it
                try:
                    print(f"Received {message.type} from {address}")
                    
                    if message.type == Message.REQUEST_CHAIN:
                        self._send_chain(client_socket)
                    elif message.type == Message.SEND_CHAIN:
                        self._receive_chain(message.data)
                    elif message.type == Message.NEW_BLOCK:
                        self._receive_block(message.data)
                    elif message.type == Message.NEW_TRANSACTION:
                        self._receive_transaction(message.data)
                    elif message.type == Message.REQUEST_PEERS:
                        self._send_peers(client_socket)
                    elif message.type == Message.SEND_PEERS:
                        self._receive_peers(message.data)
                    elif message.type == Message.PING:
                        self._send_message(client_socket, Message(Message.PONG, "pong"))
                    else:
                        print(f"[DEBUG] Unknown message type: {message.type}")
                
                except Exception as e:
                    print(f"[DEBUG] Error processing {message.type} from {address}: {str(e)[:50]}...")
                    # Don't break on handler errors—continue listening
                    continue
        
        except Exception as e:
            print(f"Error handling peer {address}: {str(e)[:100]}")
        
        finally:
            try:
                client_socket.close()
            except:
                pass
            print(f"Connection closed: {address}")
    
    def connect_to_peer(self, peer_host: str, peer_port: int) -> bool:
        """Connect to a peer node"""
        try:
            peer = Peer(peer_host, peer_port)
            
            if peer_host == self.host and peer_port == self.port:
                return False
            
            if peer in self.peers:
                print(f"Already connected to {peer}")
                return True
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((peer_host, peer_port))
            
            with self.lock:
                self.peers.add(peer)
            
            print(f"Connected to peer: {peer}")
            
            self._send_message(sock, Message(Message.REQUEST_CHAIN, None))
            self._send_message(sock, Message(Message.REQUEST_PEERS, None))
            
            response_thread = threading.Thread(
                target=self._handle_peer,
                args=(sock, (peer_host, peer_port))
            )
            response_thread.daemon = True
            response_thread.start()
            
            return True
        except Exception as e:
            print(f"Error connecting to {peer_host}:{peer_port}: {e}")
            return False
    
    def _send_message(self, sock: socket.socket, message: Message):
        """Send a message to a socket"""
        try:
            sock.sendall(message.to_json().encode())
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def _send_chain(self, sock: socket.socket):
        """Send our blockchain to a peer"""
        try:
            chain_data = []
            for block in self.blockchain.chain:
                block_dict = {
                    'index': block.index,
                    'timestamp': block.timestamp,
                    'transactions': [tx.to_dict() for tx in block.transactions],
                    'previous_hash': block.previous_hash,
                    'nonce': block.nonce,
                    'hash': block.hash,
                    'merkle_root': block.merkle_root
                }
                chain_data.append(block_dict)
            
            message = Message(Message.SEND_CHAIN, chain_data)
            self._send_message(sock, message)
            print("Sent blockchain to peer")
        except Exception as e:
            print(f"Error sending chain: {e}")
    
    def _receive_chain(self, chain_data: List[Dict]):
        """Receive and validate a blockchain from peer"""
        try:
            if not chain_data or len(chain_data) <= len(self.blockchain.chain):
                return
            
            new_chain = []
            for block_dict in chain_data:
                transactions = []
                for tx_dict in block_dict['transactions']:
                    tx = Transaction(
                        inputs=tx_dict['inputs'],
                        outputs=tx_dict['outputs'],
                        timestamp=tx_dict['timestamp'],
                        txid=tx_dict['txid']
                    )
                    transactions.append(tx)
                
                block = Block(
                    index=block_dict['index'],
                    timestamp=block_dict['timestamp'],
                    transactions=transactions,
                    previous_hash=block_dict['previous_hash'],
                    nonce=block_dict['nonce'],
                    hash=block_dict['hash'],
                    merkle_root=block_dict['merkle_root']
                )
                new_chain.append(block)
            
            temp_blockchain = Blockchain(difficulty=self.blockchain.base_difficulty, difficulty_interval=self.blockchain.difficulty_interval)
            temp_blockchain.chain = new_chain
            
            if temp_blockchain.is_chain_valid():
                with self.lock:
                    self.blockchain.chain = new_chain
                    self.blockchain.utxo_set = {}
                    for block in self.blockchain.chain:
                        self.blockchain.update_utxo_set(block)
                try:
                    self.blockchain.save_to_file()
                except Exception:
                    pass
                print(f"Blockchain synced! New length: {len(self.blockchain.chain)}")
        except Exception as e:
            print(f"Error receiving chain: {e}")
    
    def _receive_block(self, block_data: Dict):
        """Receive a new block from peer"""
        try:
            block_hash = block_data.get('hash')
            if block_hash in self.seen_blocks:
                return

            self.seen_blocks.add(block_hash)

            transactions = []
            for tx_dict in block_data['transactions']:
                tx = Transaction(
                    inputs=tx_dict['inputs'],
                    outputs=tx_dict['outputs'],
                    timestamp=tx_dict['timestamp'],
                    txid=tx_dict['txid']
                )
                transactions.append(tx)

            block = Block(
                index=block_data['index'],
                timestamp=block_data['timestamp'],
                transactions=transactions,
                previous_hash=block_data['previous_hash'],
                nonce=block_data['nonce'],
                hash=block_data['hash'],
                merkle_root=block_data['merkle_root']
            )

            if not self.blockchain.is_block_timestamp_valid(block):
                print(f"Rejected block {block.hash} due to invalid timestamp")
                return

            if (block.previous_hash == self.blockchain.get_latest_block().hash and
                block.hash == block.calculate_hash() and
                block.hash.startswith('0' * self.blockchain.difficulty)):

                with self.lock:
                    self.blockchain.chain.append(block)
                    self.blockchain.update_utxo_set(block)
                    self.blockchain.pending_transactions = []
                    try:
                        self.blockchain.save_to_file()
                    except Exception:
                        pass

                print(f"New block added from network: {block.hash}")
                self.broadcast_block(block)
        except Exception as e:
            print(f"Error receiving block: {e}")
    
    def _receive_transaction(self, tx_data: Dict):
        """Receive a new transaction from peer"""
        try:
            txid = tx_data.get('txid')
            if txid in self.seen_transactions:
                return
            
            self.seen_transactions.add(txid)
            
            tx = Transaction(
                inputs=tx_data['inputs'],
                outputs=tx_data['outputs'],
                timestamp=tx_data['timestamp'],
                txid=tx_data['txid']
            )
            
            with self.lock:
                self.blockchain.add_transaction(tx)
            
            print(f"New transaction added from network: {txid[:16]}...")
            self.broadcast_transaction(tx)
        except Exception as e:
            print(f"Error receiving transaction: {e}")
    
    def _send_peers(self, sock: socket.socket):
        """Send our peer list to requesting peer"""
        try:
            peer_list = [{'host': p.host, 'port': p.port} for p in self.peers]
            message = Message(Message.SEND_PEERS, peer_list)
            self._send_message(sock, message)
        except Exception as e:
            print(f"Error sending peers: {e}")
    
    def _receive_peers(self, peer_data: List[Dict]):
        """Receive peer list and connect to new peers"""
        try:
            for peer_info in peer_data:
                peer = Peer(peer_info['host'], peer_info['port'])
                if peer not in self.peers:
                    threading.Thread(
                        target=self.connect_to_peer,
                        args=(peer.host, peer.port)
                    ).start()
        except Exception as e:
            print(f"Error receiving peers: {e}")
    
    def broadcast_block(self, block: Block):
        """Broadcast a new block to all peers"""
        block_dict = {
            'index': block.index,
            'timestamp': block.timestamp,
            'transactions': [tx.to_dict() for tx in block.transactions],
            'previous_hash': block.previous_hash,
            'nonce': block.nonce,
            'hash': block.hash,
            'merkle_root': block.merkle_root
        }
        
        self.seen_blocks.add(block.hash)
        message = Message(Message.NEW_BLOCK, block_dict)
        
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((peer.host, peer.port))
                self._send_message(sock, message)
                sock.close()
            except Exception as e:
                print(f"Error broadcasting block to {peer}: {e}")
    
    def broadcast_transaction(self, tx: Transaction):
        """Broadcast a new transaction to all peers"""
        self.seen_transactions.add(tx.txid)
        message = Message(Message.NEW_TRANSACTION, tx.to_dict())
        
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((peer.host, peer.port))
                self._send_message(sock, message)
                sock.close()
            except Exception as e:
                print(f"Error broadcasting transaction to {peer}: {e}")
    
    def mine_and_broadcast(self, mining_address: str):
        """Mine a block and broadcast it to network"""
        print(f"\n{'='*60}")
        print(f"MINING PROCESS STARTED")
        print(f"{'='*60}")
        self.blockchain.mine_pending_transactions(mining_address)
        try:
            self.blockchain.save_to_file()
        except Exception:
            pass
        latest_block = self.blockchain.get_latest_block()
        print(f"\nBroadcasting block to {len(self.peers)} peers...")
        self.broadcast_block(latest_block)
        print(f"✓ Block broadcast complete")
        print(f"{'='*60}\n")
    
    def get_status(self) -> str:
        """Get node status"""
        return f"""
Node Status:
-----------
Address: {self.host}:{self.port}
Running: {self.running}
Connected Peers: {len(self.peers)}
Blockchain Length: {len(self.blockchain.chain)}
Pending Transactions: {len(self.blockchain.pending_transactions)}
Peers: {[str(p) for p in self.peers]}
"""

    def start_api(self, api_port: int = None):
        """
        Start a lightweight HTTP JSON API for the node.
        Defaults to 8545 if no api_port provided.
        """
        if api_port is None:
            api_port = 8545

        import http.server
        import socketserver
        from urllib.parse import urlparse, parse_qs

        node = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send_json(self, code, obj):
                data = json.dumps(obj).encode('utf-8')
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                q = parse_qs(parsed.query)

                if path == "/api/blockchain":
                    chain_data = []
                    for block in node.blockchain.chain:
                        chain_data.append({
                            'index': block.index,
                            'timestamp': block.timestamp,
                            'transactions': len(block.transactions),
                            'hash': block.hash,
                            'previous_hash': block.previous_hash,
                            'nonce': block.nonce,
                            'merkle_root': block.merkle_root
                        })
                    return self._send_json(200, {"blocks": chain_data, "length": len(chain_data)})

                elif path.startswith("/api/block/"):
                    try:
                        height = int(path.split("/")[-1])
                        if height < 0 or height >= len(node.blockchain.chain):
                            return self._send_json(404, {"error": "block not found"})
                        block = node.blockchain.chain[height]
                        return self._send_json(200, {
                            'index': block.index,
                            'timestamp': block.timestamp,
                            'transactions': [tx.to_dict() for tx in block.transactions],
                            'hash': block.hash,
                            'previous_hash': block.previous_hash,
                            'nonce': block.nonce,
                            'merkle_root': block.merkle_root
                        })
                    except Exception as e:
                        return self._send_json(400, {"error": str(e)})

                elif path == "/api/wallet-info":
                    addr = q.get('address', [None])[0]
                    if not addr:
                        return self._send_json(400, {"error": "address required"})
                    bal = node.blockchain.get_balance(addr)
                    return self._send_json(200, {"address": addr, "balance": bal, "currency": "Quantum"})

                elif path == "/api/network-stats":
                    return self._send_json(200, {
                        "difficulty": node.blockchain.difficulty,
                        "base_difficulty": node.blockchain.base_difficulty,
                        "chain_length": len(node.blockchain.chain),
                        "pending_transactions": len(node.blockchain.pending_transactions),
                        "connected_peers": len(node.peers),
                        "mining_reward": node.blockchain.mining_reward
                    })

                elif path == "/balance":
                    addr = q.get('address', [None])[0]
                    if not addr:
                        return self._send_json(400, {"error": "address required"})
                    bal = node.blockchain.get_balance(addr)
                    return self._send_json(200, {"address": addr, "balance": bal})

                elif path == "/chain":
                    chain_data = []
                    for block in node.blockchain.chain:
                        chain_data.append({
                            'index': block.index,
                            'timestamp': block.timestamp,
                            'transactions': [tx.to_dict() for tx in block.transactions],
                            'previous_hash': block.previous_hash,
                            'nonce': block.nonce,
                            'hash': block.hash,
                            'merkle_root': block.merkle_root
                        })
                    return self._send_json(200, {"chain": chain_data})

                elif path == "/status":
                    return self._send_json(200, {"status": node.get_status()})

                elif path == "/peers":
                    return self._send_json(200, {"peers": [{'host': p.host, 'port': p.port} for p in node.peers]})

                else:
                    self._send_json(404, {"error": "unknown endpoint"})

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length else b''
                try:
                    payload = json.loads(body.decode('utf-8')) if body else {}
                except Exception:
                    return self._send_json(400, {"error": "invalid JSON"})

                if path == "/api/send":
                    from_addr = payload.get('from')
                    to_addr = payload.get('to')
                    amount = payload.get('amount')
                    if not from_addr or not to_addr or amount is None:
                        return self._send_json(400, {"error": "from, to, amount required"})
                    tx = Transaction(
                        inputs=[],
                        outputs=[{'address': to_addr, 'amount': amount}],
                        timestamp=time.time()
                    )
                    with node.lock:
                        node.blockchain.add_transaction(tx)
                    node.broadcast_transaction(tx)
                    return self._send_json(200, {"result": "transaction queued", "txid": tx.txid})

                else:
                    self._send_json(404, {"error": "unknown endpoint"})

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def log_message(self, format, *args):
                return

        def serve():
            try:
                with socketserver.TCPServer(("0.0.0.0", api_port), Handler) as httpd:
                    print(f"\n{'='*60}")
                    print(f"API running at http://localhost:{api_port}")
                    print(f"{'='*60}\n")
                    node.api_running = True
                    httpd.serve_forever()
            except Exception as e:
                print(f"API error: {e}")

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        time.sleep(0.5)
