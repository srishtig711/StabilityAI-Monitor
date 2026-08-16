@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment. Make sure Python is installed and added to PATH.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >nul
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo Starting Proactive System Stability Monitoring Framework...
start "System Stability Monitor Server" cmd /k "cd /d ""%~dp0"" && "".venv\Scripts\python.exe"" app.py"
ping -n 4 127.0.0.1 >nul
start "" http://127.0.0.1:5000

echo Dashboard opened at http://127.0.0.1:5000
echo Keep the "System Stability Monitor Server" window open while using the dashboard.
ping -n 6 127.0.0.1 >nul
