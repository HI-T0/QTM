#!/bin/bash

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
