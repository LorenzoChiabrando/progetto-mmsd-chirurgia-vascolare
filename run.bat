@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SOURCE=%SCRIPT_DIR%source"
set "VENV=%SOURCE%\venv"

if not exist "%VENV%" (
    echo [setup] Creating virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [error] Python not found. Install Python 3.10+ from https://www.python.org
        pause
        exit /b 1
    )
    echo [setup] Installing dependencies...
    "%VENV%\Scripts\pip" install -q -r "%SOURCE%\requirements.txt"
    echo [setup] Ready.
)

cd /d "%SOURCE%"
start "" "%VENV%\Scripts\pythonw.exe" main.py
