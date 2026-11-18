@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=.runtime"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

rem This runtime folder is deliberately separate from the original .venv.
rem The old .venv may be locked by an editor or tied to a removed Python installation.
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" --version >nul 2>nul
    if not errorlevel 1 goto environment_ready
    echo The local runtime is invalid. Rename or remove the .runtime folder, then run this file again.
    pause
    exit /b 1
)

set "SYSTEM_PYTHON="
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe" (
    set "SYSTEM_PYTHON=%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe"
)

if not defined SYSTEM_PYTHON (
    for %%P in (python.exe) do (
        %%P --version >nul 2>nul
        if not errorlevel 1 set "SYSTEM_PYTHON=%%~$PATH:P"
    )
)

if not defined SYSTEM_PYTHON (
    echo Python was not found. Install Python 3.11 or later from https://www.python.org/downloads/
    echo During installation, select "Add Python to PATH", then run this file again.
    pause
    exit /b 1
)

echo Creating virtual environment...
"%SYSTEM_PYTHON%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

:environment_ready

echo Installing dependencies...
"%VENV_PYTHON%" -m pip install -r requirements.txt >nul
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo Starting StabilityAI Monitor...
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5000/ >nul 2>nul
if errorlevel 1 (
    start "StabilityAI Monitor Server" cmd /k call "%~dp0start_server.bat"
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
    echo Check the "StabilityAI Monitor Server" window for the error message.
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000

echo Dashboard opened at http://127.0.0.1:5000
echo Keep the "StabilityAI Monitor Server" window open while using the dashboard.
