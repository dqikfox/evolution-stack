@echo off
REM THRONE_Hermes_Gateway - the ONE start path for the Hermes gateway.
REM
REM The gateway owns the cron tick on this host: it is the process that fires
REM the THRONE_Evolution_Loop job, the watchdogs and the sync jobs. When it
REM dies, every scheduled automation on THRONE stops with it - silently,
REM because the old task ran a DETACHING VBS and so always reported success.
REM
REM The interpreter is ABSOLUTE, for the same reason as every other task
REM wrapper here: a Scheduled Task runs with a minimal environment where a
REM bare "python" does not resolve, and the task then dies with 0x80070002
REM (file not found) while the script sits right there on disk.
REM
REM The script is IDEMPOTENT: if the gateway is already serving, it starts
REM nothing and exits 0. That is what lets the Scheduled Task, the estate
REM watchdog and a human all use this one file.
setlocal
set "HERMES_PY=C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
set "SUPERVISOR=C:\Users\KING\AppData\Local\hermes\scripts\gateway_supervisor.py"
if not exist "%HERMES_PY%" (
    echo [gateway] FAILED: interpreter missing at %HERMES_PY%
    exit /b 2
)
if not exist "%SUPERVISOR%" (
    echo [gateway] FAILED: supervisor missing at %SUPERVISOR%
    exit /b 2
)
"%HERMES_PY%" "%SUPERVISOR%"
exit /b %errorlevel%
