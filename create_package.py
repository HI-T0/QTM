import os
import shutil
import zipfile
from pathlib import Path

def create_package_zip():
    """
    Bundle Quantum Blockchain into a distributable package.
    Creates Quantum_Wallet_v1.0.zip with:
      - All source code
      - requirements.txt
      - install.bat
      - install.sh
      - README.txt
    """
    
    base_dir = Path(__file__).parent
    package_name = "Quantum_Wallet_v1.0"
    zip_path = base_dir / f"{package_name}.zip"
    
    # Create temporary package directory
    temp_dir = base_dir / package_name
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    # Copy source files
    shutil.copytree(base_dir / "core", temp_dir / "core")
    shutil.copytree(base_dir / "network", temp_dir / "network")
    shutil.copy(base_dir / "node.py", temp_dir / "node.py")
    shutil.copy(base_dir / "requirements.txt", temp_dir / "requirements.txt")
    
    # Create README.txt
    readme_content = """
================================================================================
  QUANTUM BLOCKCHAIN WALLET v1.0
================================================================================

INSTALLATION:
  Windows:   Double-click install.bat
  Mac/Linux: bash install.sh

RUNNING:
  python node.py 5000

OPTIONS:
  --api              Start with API enabled (default: on)
  --create-package   Generate installation package

COMMANDS (Interactive):
  mine       - Mine a new block and earn 10.2 Quantum
  balance    - Show your wallet balance
  status     - Show node status
  peers      - List connected peers
  chain      - Display full blockchain
  quit       - Exit program

API ENDPOINTS (Running on http://localhost:8545):
  GET  /api/blockchain              - All blocks
  GET  /api/block/<height>          - Specific block
  GET  /api/wallet-info?address=... - Wallet info
  GET  /api/network-stats           - Network stats
  POST /api/send                    - Send transaction

FEATURES:
  ✓ Proof-of-Work mining with dynamic difficulty
  ✓ ECDSA cryptographic signatures
  ✓ UTXO transaction model (Bitcoin-style)
  ✓ Peer-to-peer networking
  ✓ Persistent blockchain storage
  ✓ Local REST API
  ✓ 10.2 Quantum mining reward per block

REQUIREMENTS:
  Python 3.7+
  ecdsa
  base58

For more info, visit: [your-repo-url]
================================================================================
"""
    with open(temp_dir / "README.txt", "w") as f:
        f.write(readme_content)
    
    # Create install.bat
    install_bat_content = """@echo off
setlocal enabledelayedexpansion

echo.
echo Installing Quantum Blockchain Wallet...
echo.

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.7 or later.
    pause
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Installation complete!
echo.
echo Starting Quantum node on port 5000...
echo API will be available at http://localhost:8545
echo.
python node.py 5000 --api

pause
"""
    with open(temp_dir / "install.bat", "w") as f:
        f.write(install_bat_content)
    
    # Create install.sh
    install_sh_content = """#!/bin/bash

echo ""
echo "Installing Quantum Blockchain Wallet..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Please install Python 3.7 or later."
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi

echo ""
echo "Installation complete!"
echo ""
echo "Starting Quantum node on port 5000..."
echo "API will be available at http://localhost:8545"
echo ""

python3 node.py 5000 --api
"""
    with open(temp_dir / "install.sh", "w") as f:
        f.write(install_sh_content)
    os.chmod(temp_dir / "install.sh", 0o755)
    
    # Create zip file
    if zip_path.exists():
        zip_path.unlink()
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(base_dir)
                zf.write(file_path, arcname)
    
    # Cleanup temp directory
    shutil.rmtree(temp_dir)
    
    print(f"✓ Package created: {zip_path}")
    print(f"  Size: {zip_path.stat().st_size / (1024*1024):.2f} MB")
    print(f"  Location: {zip_path.parent}")

if __name__ == "__main__":
    create_package_zip()
