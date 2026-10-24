@echo off
REM check-shop-status.cmd - Quick health check for KRYSYS shop + Telegram bot
setlocal

echo === KRYSYS Shop :8080 ===
curl -s --max-time 5 -o nul -w "  HTTP %%{http_code} - API config" http://127.0.0.1:8080/api/config
echo.
curl -s --max-time 5 -o nul -w "  HTTP %%{http_code} - Catalog page" http://127.0.0.1:8080/catalog.html
echo.
curl -s --max-time 5 -o nul -w "  HTTP %%{http_code} - Catalog API" http://127.0.0.1:8080/api/catalog
echo.
echo.

echo === Public URLs ===
curl -s --max-time 10 -o nul -w "  HTTP %%{http_code} - GitHub Pages catalog" https://dqikfox.github.io/krysys-catalog/
echo.
curl -s --max-time 10 -o nul -w "  HTTP %%{http_code} - Vercel storefront" https://krysys-shop.vercel.app/
echo.
echo.

echo === Telegram Bot ===
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'shop-launcher' } | Select-Object @{N='PID';E={$_.ProcessId}}, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize | Out-String"
powershell -Command "Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -eq 443 -and $_.RemoteAddress -match 'telegram|2001:67c' } | Select-Object OwningProcess, State | Format-Table -AutoSize | Out-String"
echo.

echo === Recent bot log (last 10) ===
if exist "%LOCALAPPDATA%\hermes\scripts\bot-restart.log" (
    powershell -Command "Get-Content '%LOCALAPPDATA%\hermes\scripts\bot-restart.log' -Tail 10"
) else (
    echo   (no log)
)

endlocal