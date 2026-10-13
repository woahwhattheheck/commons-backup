@echo off
title Muhlnickel 32-bit CPU Demo
echo ================================================================
echo   MUHLNICKEL 32-BIT CPU DEMO
echo   7,403 gates, 15-op ISA, running from titan.gguf
echo ================================================================
echo.
python "%~dp0run.py"
if errorlevel 1 pause
