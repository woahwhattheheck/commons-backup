@echo off
title DOOM -- Muhlnickel Demo
echo.
echo  DOOM on the Muhlnickel
echo  ----------------------
echo  Loading circuits from titan.gguf ...
echo.
python "%~dp0run.py"
if errorlevel 1 (
    echo.
    echo  ERROR: Python failed. Make sure Python is installed and titan.gguf exists at C:\llm\models\titan.gguf
    pause
)
