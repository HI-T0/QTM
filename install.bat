@echo off
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
