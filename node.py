import sys
import time
import os
from core.blockchain import Blockchain
from core.wallet import Wallet
from network.node import P2PNode

def run_cli():
    """Run CLI mode (interactive mining and commands)"""
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [peer_host:peer_port] [--api] [--create-package]")
        print("Example: python node.py 5000")
        print("Example: python node.py 5001 localhost:5000 --api")
        sys.exit(1)
    
    port = int(sys.argv[1])
    start_api = "--api" in sys.argv
    create_package = "--create-package" in sys.argv

    # Create blockchain and node
    blockchain = Blockchain()
    node = P2PNode("localhost", port, blockchain)
    
    # Start node
    node.start()
    
    # Start API if requested or by default
    if start_api:
        node.start_api(api_port=8545)
    else:
        # Auto-start API by default
        node.start_api(api_port=8545)
    
    # Connect to peer if provided
    peer_info_provided = False
    for arg in sys.argv[2:]:
        if ':' in arg and not arg.startswith('--'):
            peer_info = arg.split(':')
            peer_host = peer_info[0]
            peer_port = int(peer_info[1])
            time.sleep(1)
            node.connect_to_peer(peer_host, peer_port)
            time.sleep(2)
            peer_info_provided = True
            break
    
    # If --create-package, generate zip and exit
    if create_package:
        print("\nGenerating package...")
        try:
            from create_package import create_package_zip
            create_package_zip()
            print("Package created successfully!")
        except ImportError:
            print("Error: create_package.py not found")
        node.stop()
        return
    
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
    print(f"\nAPI is running at http://localhost:8545")
    
    try:
        while True:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "mine":
                node.mine_and_broadcast(wallet.address)
                print(f"Balance: {blockchain.get_balance(wallet.address)} Quantum")
            
            elif cmd == "balance":
                print(f"Balance: {blockchain.get_balance(wallet.address)} Quantum")
            
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

def main():
    """Entry point: decide between CLI and Flask"""
    # If FLASK_ENV is set or PORT env var exists, run Flask
    if os.environ.get("FLASK_ENV") or os.environ.get("PORT"):
        # Flask will import and run app.py
        from app import app
        port = int(os.environ.get("PORT", 8545))
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        # Run CLI mode
        run_cli()

if __name__ == "__main__":
    main()
