@echo off
REM ---------------------------------------------------------------------------
REM Launcher for the THRONE discovery service (:8660).
REM
REM Three things this file exists to get right:
REM
REM  1. THE SERVICE IS DETACHED. The discovery service in --http mode
REM     SERVES FOREVER, so a launcher that runs it in the foreground never
REM     returns: the watchdog calls it, waits for the launcher to exit,
REM     and the heal burns its whole budget on a process that was working
REM     the entire time. The service is spawned with spawn_detached.py,
REM     which passes an explicit handle-inheritance list, so the child
REM     inherits nothing but its log file and the caller is released.
REM
REM  2. THE ARGUMENTS ARE PASSED THROUGH. The service runs in different
REM     modes - a scan, a watch loop, an HTTP server on :8660 that
REM     TESSERACT reads - and the mode is chosen by the argument. A
REM     launcher that drops its arguments starts the service in the WRONG
REM     MODE, and then the port never opens and the heal looks like it
REM     worked.
REM
REM  3. THE INTERPRETER IS ABSOLUTE. A bare `python` resolves differently
REM     under a scheduler than in an interactive shell - under Task
REM     Scheduler's minimal environment it does not resolve at all, and
REM     the task fails with 0x80070002. The venv's own interpreter is
REM     named outright, and it is the one with the packages.
REM
REM Usage:  launcher_discovery.bat [--http] [--watch] [--interval N]
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own packages,
REM not the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=
set VIRTUAL_ENV=

set DISC_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set DISC_SCRIPT=%LOCALAPPDATA%\hermes\scripts\throne_discovery.py
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set DISC_LOG=%LOCALAPPDATA%\hermes\logs\discovery_stdout.log
set DISC_HEALTH=http://127.0.0.1:8660/

if not exist "%DISC_PY%" (
    echo [discovery] FAILED: interpreter missing at %DISC_PY%
    exit /b 1
)
if not exist "%DISC_SCRIPT%" (
    echo [discovery] FAILED: script missing at %DISC_SCRIPT%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [discovery] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

echo [discovery] starting (server log: %DISC_LOG%)...
"%DISC_PY%" "%SPAWNER%" --log "%DISC_LOG%" --err "%DISC_LOG%.err" --cwd "%LOCALAPPDATA%\hermes\scripts" -- "%DISC_PY%" "%DISC_SCRIPT%" %*
if errorlevel 1 (
    echo [discovery] FAILED: spawner returned an error - see %DISC_LOG%.err
    exit /b 1
)

if exist "%WAITER%" (
    "%DISC_PY%" "%WAITER%" "%DISC_HEALTH%" 60 2
    if errorlevel 1 (
        echo [discovery] FAILED: the endpoint did not answer within 60s - see the log
        exit /b 1
    )
)
echo [discovery] up on :8660
exit /b 0