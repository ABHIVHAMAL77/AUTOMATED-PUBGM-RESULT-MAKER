@echo off
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" setup_discord_env.py
if errorlevel 1 pause
