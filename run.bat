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
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5000/ >nul 2>nul
if errorlevel 1 (
    start "System Stability Monitor Server" cmd /k call "%~dp0start_server.bat"
)

echo Waiting for the local server to become ready...
set "SERVER_READY="
for /l %%i in (1,1,30) do (
    curl.exe --silent --fail --max-time 2 http://127.0.0.1:5000/ >nul 2>nul
    if not errorlevel 1 (
        set "SERVER_READY=1"
        goto server_ready
    )
    ping -n 2 127.0.0.1 >nul
)

:server_ready
if not defined SERVER_READY (
    echo The dashboard server did not start correctly.
    echo Check the "System Stability Monitor Server" window for the error message.
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000

echo Dashboard opened at http://127.0.0.1:5000
echo Keep the "System Stability Monitor Server" window open while using the dashboard.
