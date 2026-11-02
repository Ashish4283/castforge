@echo off
rem Stops the CastForge app (the web page). A render that is running keeps going on its own;
rem it is not stopped by this. Check it later in the app or with: python castforge.py status <folder>
cd /d "%~dp0"
if not exist ".app.pid" (
    echo CastForge app was not running.
    goto :end
)
set /p PID=<.app.pid
taskkill /PID %PID% /T /F >nul 2>&1
if %errorlevel%==0 (echo CastForge app stopped.) else (echo CastForge app was not running.)
del ".app.pid" >nul 2>&1
:end
ping -n 3 127.0.0.1 >nul
