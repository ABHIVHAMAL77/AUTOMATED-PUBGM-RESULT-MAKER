@echo off
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

if exist ".env.discord" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.discord") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

if "%DISCORD_BOT_TOKEN%"=="" (
    echo.
    echo DISCORD_BOT_TOKEN is not set.
    echo Run setup_discord_env.bat first, or create .env.discord from .env.discord.example.
    echo.
    pause
    exit /b 1
)

"%PY%" -c "import discord" >nul 2>&1
if errorlevel 1 (
    echo Installing Discord bot dependency, please wait...
    "%PY%" -m pip install -r requirements.txt
)

echo.
echo ESPORTS COUNTY Discord Result Bot
echo Commands: /teamss, /overallss, /playerdetails, /results, /standings, /players, /autostart
echo.
"%PY%" discord_bot.py
if errorlevel 1 pause
