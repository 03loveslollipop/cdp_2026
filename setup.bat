@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PYTHON=py -3") || set "PYTHON=python"
if not exist ".venv\Scripts\python.exe" %PYTHON% -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt -r mlops_pipeline\requirements-training.txt
