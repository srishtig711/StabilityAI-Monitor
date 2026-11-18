@echo off
cd /d "%~dp0"

echo Starting StabilityAI Monitor at http://127.0.0.1:5000
".runtime\Scripts\python.exe" app.py

echo.
echo Server stopped. If this window closed immediately, check the error above.
pause
