@echo off
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

rem First run on a new PC: install required packages automatically
"%PY%" -c "import PySide6, PIL, requests, openpyxl, rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages, please wait...
    "%PY%" -m pip install -r requirements.txt
)

"%PY%" app.py
if errorlevel 1 pause
