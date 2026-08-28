@echo off
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

rem First web run: install desktop + web requirements automatically
"%PY%" -c "import fastapi, uvicorn, multipart, PySide6, PIL, requests, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages, please wait...
    "%PY%" -m pip install -r requirements.txt
)

rem The interface is a Vite build. Built once here; rebuild after editing web\src.
if not exist "web\dist\index.html" (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo.
        echo Node.js is required to build the web interface.
        echo Install it from https://nodejs.org then run this file again.
        echo.
        pause
        exit /b 1
    )
    echo Building the web interface, please wait...
    pushd web
    if not exist "node_modules" call npm install
    call npm run build
    popd
)

echo.
echo ESPORTS COUNTY PUBGM RESULT MAKER
echo Open this in your browser:
echo http://127.0.0.1:8080
echo.
"%PY%" -m uvicorn web_app:app --host 127.0.0.1 --port 8080
if errorlevel 1 pause
