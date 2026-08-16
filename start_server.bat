@echo off
cd /d "%~dp0"

echo Starting Flask server at http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py

echo.
echo Server stopped. If this window closed immediately, check the error above.
pause
