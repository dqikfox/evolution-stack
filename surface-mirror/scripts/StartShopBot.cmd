@echo off
REM StartShopBot.cmd - Permanent launcher for the Telegram shop bot.
REM Loads token from 1Password and starts polling in background.

setlocal
set "SCRIPTS_DIR=%LOCALAPPDATA%\hermes\scripts"
if not exist "%SCRIPTS_DIR%\shop-launcher.py" (
    echo ERROR: shop-launcher.py not found at %SCRIPTS_DIR%
    exit /b 1
)

REM Launch via pythonw (no console window) so it survives disconnects
cd /d "%SCRIPTS_DIR%"
start "ShopBot" /B pythonw.exe shop-launcher.py

REM Give it a moment to start
timeout /t 2 /nobreak > nul

REM Check it's running
tasklist /FI "IMAGENAME eq pythonw.exe" /NH | findstr /R "pythonw"
if %ERRORLEVEL% == 0 (
    echo ShopBot started successfully.
) else (
    echo WARNING: shop-launcher may have failed to start. Check log:
    echo   %LOCALAPPDATA%\hermes\audit\shop-bot.log
)

endlocal