@echo off
rem Starts the CastForge app and opens it in the browser (http://localhost:8765).
cd /d "%~dp0"
netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo CastForge is already running.
    start "" http://localhost:8765
    exit /b 0
)
start "CastForge app" /min python castforge.py app
echo CastForge is starting... the browser opens in a moment.
echo Close it with STOP_CASTFORGE.bat
ping -n 4 127.0.0.1 >nul
