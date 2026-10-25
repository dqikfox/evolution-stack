@echo off
REM THRONE_Watchdog_5min - keeps the estate up.
REM
REM The task used to run a bare "python", and a Scheduled Task runs with a
REM minimal environment where "python" does not resolve - so this task had
REM been failing with 0x80070002 (file not found) while the script sat on
REM disk. The estate had no automatic recovery at all, and the only
REM symptom was a Last Result nobody read.
REM
REM The interpreter is ABSOLUTE for the same reason: no PATH, no guessing.
REM The watchdog itself is the house watchdog: it reads the canonical
REM registry and restarts anything healable that is down, through the
REM documented launcher.
setlocal
set "HERMES_PY=C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
set "WATCHDOG=C:\Users\KING\AppData\Local\hermes\scripts\estate_watchdog.py"
if not exist "%HERMES_PY%" (
    echo [watchdog] FAILED: interpreter missing at %HERMES_PY%
    exit /b 2
)
if not exist "%WATCHDOG%" (
    echo [watchdog] FAILED: watchdog missing at %WATCHDOG%
    exit /b 2
)
"%HERMES_PY%" "%WATCHDOG%"
exit /b %errorlevel%
