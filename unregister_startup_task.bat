@echo off
setlocal

schtasks /Delete /TN "StabilityAI Monitor" /F

if errorlevel 1 (
    echo Failed to remove startup task, or it was not registered.
    pause
    exit /b 1
)

echo Startup task removed.
pause
