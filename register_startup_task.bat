@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Run run.bat once before registering startup.
    pause
    exit /b 1
)

schtasks /Create /TN "System Stability Monitor" /SC ONLOGON /TR "\"%CD%\.venv\Scripts\pythonw.exe\" \"%CD%\app.py\"" /RL LIMITED /F

if errorlevel 1 (
    echo Failed to register startup task. Try running this file as administrator.
    pause
    exit /b 1
)

echo Startup task registered.
echo The monitor will start automatically when you log in.
pause
