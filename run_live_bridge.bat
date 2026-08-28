@echo off
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" local_live_bridge.py
if errorlevel 1 pause
