@echo off
REM Start n8n 1.94.0 at user logon.
REM Node 22.23.2 from C:\Users\KING\AppData\Local\hermes\node is required (n8n doesn't support Node 26).
REM N8N_ENCRYPTION_KEY is NOT in this file. It is resolved from 1Password by
REM n8n_launcher.py, with a DPAPI-encrypted local cache as the fallback, so a
REM vault outage degrades n8n instead of killing it - and the key can never be
REM copied into a launcher, a log, or a mirrored git repository.
REM N8N_USER_FOLDER, N8N_PORT and N8N_HOST are set in n8n_launcher.py.

setlocal
set "SCRIPTS=%LOCALAPPDATA%\hermes\scripts"
set N8N_LOG=%LOCALAPPDATA%\hermes\logs\n8n.log

REM If a port is already bound, n8n is up; exit.
powershell -NoProfile -Command "(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5678 } | Measure-Object).Count -gt 0" 2>nul | findstr /r "^True$" >nul
if not errorlevel 1 (
  echo [%DATE% %TIME%] n8n already up on :5678, skipping start >> "%N8N_LOG%"
  exit /b 0
)

echo [%DATE% %TIME%] Starting n8n 1.94.0 (key from 1Password)... >> "%N8N_LOG%"
python "%SCRIPTS%\n8n_launcher.py"
if errorlevel 1 (
  echo [%DATE% %TIME%] n8n_launcher FAILED - see log >> "%N8N_LOG%"
  exit /b 1
)
exit /b 0
