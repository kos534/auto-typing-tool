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

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo Building AutoTypingTool.exe...
python -m PyInstaller --noconfirm AutoTypingTool.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete: %~dp0dist\AutoTypingTool.exe
pause
exit /b 0
