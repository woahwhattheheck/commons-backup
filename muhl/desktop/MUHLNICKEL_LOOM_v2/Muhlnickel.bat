@echo off
REM Muhlnickel.bat - one click. Self test, then an example shot.
cd /d "%~dp0"
python run_muhlnickel.py --selftest
echo.
python run_muhlnickel.py 200 55
echo.
pause
