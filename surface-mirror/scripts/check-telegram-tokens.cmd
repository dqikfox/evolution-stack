@echo off
REM check-telegram-tokens.cmd - Audit all Telegram bot tokens in 1Password.
REM
REM Outputs:
REM   - All TELEGRAM_* items in credentials vault, with the bot username/id
REM   - Duplicate secret detection (multiple 1Password items for same bot)
REM   - Admin chat ID status
REM   - Current shop-bot health

setlocal

echo === Telegram bot tokens in credentials vault ===
echo.

powershell -NoProfile -Command "$items = op item list --vault credentials --format json 2>$null | ConvertFrom-Json; foreach ($item in $items) { if ($item.title -like 'TELEGRAM*TOKEN*') { $token = op read ('op://credentials/' + $item.title + '/credential') 2>$null; if ($token) { $info = curl.exe -s --max-time 5 ('https://api.telegram.org/bot' + $token + '/getMe') 2>$null; $parsed = $info | ConvertFrom-Json; if ($parsed.ok) { $r = $parsed.result; Write-Host ('  ' + $item.title.PadRight(30) + '  @' + $r.username.PadRight(20) + ' id=' + $r.id) } else { Write-Host ('  ' + $item.title + '  ERROR: ' + $parsed.description) } } else { Write-Host ('  {0,-30s}  <read failed>' -f $item.title) } } }"

echo.
echo === Admin chat ID check ===
for /f "tokens=*" %%L in ('findstr /B "TELEGRAM_ADMIN_CHAT_ID" "%LOCALAPPDATA%\hermes\.env" 2^>nul') do set ADMIN_LINE=%%L
if defined ADMIN_LINE (
    echo Found in .env: !ADMIN_LINE!
    set "ADMIN_REF=!ADMIN_LINE:*op://=op://!"
    if "!ADMIN_LINE!" == "!ADMIN_LINE:op://=!" (
        echo No op:// reference - admin chat ID is a literal value or comment
    ) else (
        set "REF_ITEM=!ADMIN_LINE:op://credentials/=!"
        set "REF_ITEM=!REF_ITEM:/credential=!"
        op item get "!REF_ITEM!" --vault credentials --format json >nul 2>&1
        if !ERRORLEVEL! == 0 (
            echo   Item '!REF_ITEM!' EXISTS in vault
        ) else (
            echo   Item '!REF_ITEM!' NOT in vault - admin notifications disabled
        )
    )
) else (
    echo No TELEGRAM_ADMIN_CHAT_ID in .env (notifications disabled)
)

echo.
echo === Shop-bot health ===
if exist "%LOCALAPPDATA%\hermes\scripts\bot-restart.log" (
    powershell -NoProfile -Command "Get-Content '%LOCALAPPDATA%\hermes\scripts\bot-restart.log' -Tail 5"
) else (
    echo   (no log file)
)

echo.
echo === Shop-bot process ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name=\"pythonw.exe\"' | Where-Object { $_.CommandLine -match 'shop-launcher' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize | Out-String"

endlocal