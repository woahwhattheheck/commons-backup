@echo off
title MUHLNICKEL SPECTATOR MODE
echo ================================================================
echo   MUHLNICKEL SPECTATOR MODE
echo   Built by Bryce Muhlnickel
echo   INSTRUMENT ONLY -- surface reads, no writes, no computation
echo ================================================================
echo.

:: Check if muhl_live_surface.py is already running on port 7880
netstat -ano | findstr ":7880" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Live surface server already running on port 7880
) else (
    echo [STARTING] muhl_live_surface.py on port 7880...
    start "MUHLNICKEL Live Surface" /min python "%~dp0muhl_live_surface.py" --port 7880 --no-browser
    echo [WAIT] Giving server 3 seconds to start...
    timeout /t 3 /nobreak >nul
)

echo.
echo [OPENING] Spectator UI in browser...
start "" "%~dp0muhl_spectator.html"

echo.
echo [LIVE] Spectator mode is running.
echo [LIVE] Close this window to keep the server running in background.
echo [LIVE] Or press Ctrl+C here to stop the server.
echo.
pause
