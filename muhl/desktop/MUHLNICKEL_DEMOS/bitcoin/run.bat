@echo off
title Muhlnickel Bitcoin Miner Demo
echo ================================================================
echo   MUHLNICKEL BITCOIN MINER DEMO
echo   The SHA-256d circuit lives inside titan.gguf (40 GB model file)
echo ================================================================
echo.
python "%~dp0run.py"
if errorlevel 1 pause
