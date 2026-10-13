@echo off
cd /d "%~dp0"
if "%~1"=="" ( start "" "%~dp0titan.html" )
python "%~dp0titan.py" %*
