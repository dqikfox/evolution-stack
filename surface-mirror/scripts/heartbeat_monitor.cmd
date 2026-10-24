@echo off
REM Heartbeat monitor - pings shop server and alerts if down
REM Called every 5 minutes via Windows Task Scheduler
setlocal

set SHOP_URL=http://127.0.0.1:8522/health
set BOT_URL=http://127.0.0.1:8522/stats
set GH_PAGES_URL=https://dqikfox.github.io/lummings/shop/
set LOG=C:\Users\KING\AppData\Local\hermes\audit\heartbeat.log
set FAIL_COUNT_FILE=C:\Users\KING\AppData\Local\hermes\audit\heartbeat-fail-count.txt

REM Get fail count (0 if file missing)
set /a FAIL_COUNT=0
if exist "%FAIL_COUNT_FILE%" (
  set /p FAIL_COUNT=<%FAIL_COUNT_FILE%
)

REM Check shop server
curl -s --max-time 5 "%SHOP_URL%" >nul 2>&1
set SHOP_OK=%ERRORLEVEL%

REM Check gh-pages
curl -s --max-time 10 -o nul -w "%%{http_code}" "%GH_PAGES_URL%" >nul 2>&1
set GH_OK=%ERRORLEVEL%

REM Log result
echo %date% %time% shop=%SHOP_OK% gh=%GH_OK% fails=%FAIL_COUNT%>>"%LOG%"

REM If shop is down, increment fail count; if up, reset to 0
if %SHOP_OK% NEQ 0 (
  set /a FAIL_COUNT+=1
  echo %FAIL_COUNT%>"%FAIL_COUNT_FILE%"
  if %FAIL_COUNT% GEQ 3 (
    REM 3 consecutive failures - alert via Telegram
    python C:\Users\KING\AppData\Local\hermes\scripts\telegram_alert.py "Shop server DOWN. Fail count: %FAIL_COUNT%. Restart needed."
  )
) else (
  set /a FAIL_COUNT=0
  echo 0>"%FAIL_COUNT_FILE%"
)

endlocal