@echo off
REM restart-shop-bot.cmd - Restart shop-bot with 90s delay between attempts.
REM Usage: cmd /c restart-shop-bot.cmd
REM This kills any running pythonw, waits 90 seconds for Telegram lock to clear,
REM then starts the bot fresh.

setlocal

set SCRIPTS=%LOCALAPPDATA%\hermes\scripts

echo Killing any existing shop-bot...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name=\"pythonw.exe\"' | Where-Object { $_.CommandLine -match 'shop-launcher|shop_bot' } | Stop-Process -Force -ErrorAction SilentlyContinue"

echo Waiting 90 seconds for Telegram long-poll slot to clear...
timeout /t 90 /nobreak > nul

echo Clearing bot log...
del /q "%SCRIPTS%\bot-restart.log" 2>nul

echo Starting shop-bot via pythonw...
start "ShopBot" /B pythonw.exe -u shop-launcher.py

timeout /t 3 /nobreak > nul

echo ShopBot started. Monitoring with:
echo   type %SCRIPTS%\bot-restart.log
echo.
echo Watch for 'HTTP Error 409' in the log. If 3+ appear in 5 minutes,
echo re-run this script.

endlocal