@echo off
rem Stops the CastForge app (the web page). A render that is running keeps going on its own;
rem it is not stopped by this. Check it later in the app or with: python castforge.py status <folder>
cd /d "%~dp0"
set PID=
if exist ".app.pid" set /p PID=<.app.pid
if "%PID%"=="" (
    rem no pid file: find the server by its port
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765 " ^| findstr "LISTENING"') do set PID=%%p
)
if "%PID%"=="" (
    echo CastForge app was not running.
    goto :end
)
taskkill /PID %PID% /T /F >nul 2>&1
if %errorlevel%==0 (echo CastForge app stopped.) else (echo CastForge app was not running.)
del ".app.pid" >nul 2>&1
:end
ping -n 3 127.0.0.1 >nul
