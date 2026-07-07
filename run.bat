@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Install it from https://www.python.org/downloads/ and check "Add to PATH".
    pause
    exit /b 1
)

python -c "import keyboard" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

start "" pythonw main.py
exit /b 0
