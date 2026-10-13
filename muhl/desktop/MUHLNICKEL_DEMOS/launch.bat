@echo off
title MUHLNICKEL DEMO SUITE
color 0A
echo.
echo  ===============================================
echo   MUHLNICKEL DEMO SUITE
echo   Substrate-Resident Computer
echo  ===============================================
echo.
echo  Starting Live Surface on port 7880...
start /min py "C:\Users\lucys\OneDrive\Desktop\MUHLNICKEL_BUILD_LAB_20260801_025117\muhl_live_surface.py" --port 7880 --no-browser
echo  Waiting for surface to initialize...
timeout /t 3 /nobreak >nul
echo  Opening Demo Dashboard...
start "" "%~dp0index.html"
echo.
echo  Surface running in background.
echo  Close this window to stop the surface.
echo.
pause
