@echo off
cd /d "%~dp0.."

if not exist "venv" (
    echo Setting up virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
python main.py
