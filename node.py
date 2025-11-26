import sys
import time
from core.blockchain import Blockchain
from core.wallet import Wallet
from network.node import P2PNode

def main():
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [peer_host:peer_port]")
        print("Example: python node.py 5000")
        print("Example: python node.py 5001 localhost:5000")
        sys.exit(1)
    
    port = int(sys.argv[1])
    
    # Create blockchain and node
    blockchain = Blockchain()
    node = P2PNode("localhost", port, blockchain)
    
    # Start node
    node.start()
    
    # Connect to peer if provided
    if len(sys.argv) >= 3:
        peer_info = sys.argv[2].split(':')
        peer_host = peer_info[0]
        peer_port = int(peer_info[1])
        
        time.sleep(1)
        node.connect_to_peer(peer_host, peer_port)
        time.sleep(2)
    
    # Create wallet
    wallet = Wallet()
    print(f"\nMiner Wallet: {wallet.address}")
    
    # Interactive loop
    print("\nCommands:")
    print("  mine - Mine a new block")
    print("  balance - Check wallet balance")
    print("  status - Show node status")
    print("  peers - List connected peers")
    print("  chain - Display blockchain")
    print("  quit - Exit")
    
    try:
        while True:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "mine":
                node.mine_and_broadcast(wallet.address)
                print(f"Balance: {blockchain.get_balance(wallet.address)} coins")
            
            elif cmd == "balance":
                print(f"Balance: {blockchain.get_balance(wallet.address)} coins")
            
            elif cmd == "status":
                print(node.get_status())
            
            elif cmd == "peers":
                print(f"Connected peers: {[str(p) for p in node.peers]}")
            
            elif cmd == "chain":
                blockchain.print_chain()
            
            elif cmd == "quit":
                break
            
            else:
                print("Unknown command")
    
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.stop()

if __name__ == "__main__":
    main()
