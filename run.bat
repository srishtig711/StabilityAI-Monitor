@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >nul

echo Starting Proactive System Stability Monitoring Framework...
start chrome http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
