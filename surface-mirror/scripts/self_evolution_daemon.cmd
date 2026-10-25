@echo off
REM THRONE_Self_Evolution_Daemon - the host health audit.
REM
REM Same repair as watchdog_5min.cmd: the task ran a bare "python", which
REM a Scheduled Task cannot resolve, so this one had been failing with
REM 0x80070002 (file not found) as well.
REM
REM The interpreter is ABSOLUTE. The script checks the Windows services
REM (ollama, Tailscale) and disk pressure.
setlocal
set "HERMES_PY=C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
set "DAEMON=C:\Users\KING\AppData\Local\hermes\scripts\throne_watchdog.py"
if not exist "%HERMES_PY%" (
    echo [daemon] FAILED: interpreter missing at %HERMES_PY%
    exit /b 2
)
if not exist "%DAEMON%" (
    echo [daemon] FAILED: daemon missing at %DAEMON%
    exit /b 2
)
"%HERMES_PY%" "%DAEMON%"
exit /b %errorlevel%
