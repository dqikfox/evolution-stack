@echo off
REM Start n8n 1.94.0 at user logon.
REM Node 22.23.2 from C:\Users\KING\AppData\Local\hermes\node is required (n8n doesn't support Node 26).
REM N8N_ENCRYPTION_KEY, N8N_USER_FOLDER, N8N_PORT, N8N_HOST are persisted in C:\Users\KING\.n8n\config.

set NODE_EXE=C:\Users\KING\AppData\Local\hermes\node\node.exe
set N8N_BIN=C:\Users\KING\AppData\Local\npm-cache\_npx\ce64108ad803af1c\node_modules\n8n\bin\n8n
set N8N_USER_FOLDER=C:\Users\KING\.n8n
set N8N_PORT=5678
set N8N_HOST=127.0.0.1
set N8N_ENCRYPTION_KEY=***REMOVED-BY-SECRET-ROTATION***
set N8N_LOG=%LOCALAPPDATA%\hermes\logs\n8n.log

REM If a port is already bound, n8n is up; exit.
powershell -NoProfile -Command "(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5678 } | Measure-Object).Count -gt 0" 2>nul | findstr /r "^True$" >nul
if not errorlevel 1 (
  echo [%DATE% %TIME%] n8n already up on :5678, skipping start >> "%N8N_LOG%"
  exit /b 0
)

echo [%DATE% %TIME%] Starting n8n 1.94.0... >> "%N8N_LOG%"
start "n8n" /B "%NODE_EXE%" "%N8N_BIN%" start
exit /b 0
