@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the HERETIK demand proxy (:8080).
REM
REM The proxy owns the canonical :8080 contract and lazily spawns the
REM multi-GB llama-server backend on :8081 only while it is in use.
REM
REM This file exists to get two things right:
REM
REM  1. The proxy must not inherit the CALLER's stdout. A process started
REM     with inheritable handles receives copies of every inheritable handle
REM     in its parent, so if the parent was started by a caller that captured
REM     stdout into a pipe (an agent tool, CI, a shell substitution), the
REM     proxy keeps that pipe open for its whole life and the caller blocks
REM     in read() until the PROXY exits instead of until this launcher does.
REM     `cmd start` creates the child that way (measured: it HELD the
REM     caller's pipe). spawn_detached.py uses Python's close_fds=True, which
REM     passes an explicit handle-inheritance list, so the child inherits
REM     nothing but its log file (measured: it RELEASED the pipe).
REM
REM  2. The wait must not be charged PowerShell startup. The probe is a
REM     stdlib urllib call - tens of milliseconds, identical on every host.
REM
REM Usage:  start_demand_proxy.cmd
REM ---------------------------------------------------------------------------
setlocal
set PYTHONPATH=
set PYTHONHOME=

set HERETIK_DIR=%LOCALAPPDATA%\hermes\heretik
set HERETIK_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set HERETIK_SCRIPT=%HERETIK_DIR%\heretik_demand.py
set HERETIK_PORT=8080
set HERETIK_HEALTH=http://127.0.0.1:%HERETIK_PORT%/health
set HERETIK_LOG=%LOCALAPPDATA%\hermes\logs\heretik_proxy_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py

echo [heretik] checking port %HERETIK_PORT%...
"%HERETIK_PY%" "%PROBE%" "%HERETIK_HEALTH%" 3
if not errorlevel 1 (
    echo [heretik] already up on :%HERETIK_PORT% - nothing to do.
    exit /b 0
)

if not exist "%HERETIK_PY%" (
    echo [heretik] FAILED: interpreter missing at %HERETIK_PY%
    exit /b 1
)
if not exist "%HERETIK_SCRIPT%" (
    echo [heretik] FAILED: proxy script missing at %HERETIK_SCRIPT%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [heretik] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [heretik] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [heretik] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

echo [heretik] starting (proxy log: %HERETIK_LOG%)...
cd /d "%HERETIK_DIR%"
"%HERETIK_PY%" "%SPAWNER%" --log "%HERETIK_LOG%" --err "%HERETIK_LOG%.err" --cwd "%HERETIK_DIR%" -- "%HERETIK_PY%" -u "%HERETIK_SCRIPT%"
if errorlevel 1 (
    echo [heretik] FAILED: spawner returned an error - see %HERETIK_LOG%.err
    exit /b 1
)

echo [heretik] waiting for :%HERETIK_PORT%...
"%HERETIK_PY%" "%WAITER%" "%HERETIK_HEALTH%" 180 2
if errorlevel 1 (
    echo [heretik] FAILED: the endpoint did not answer within 180s - see the log
    exit /b 1
)
echo [heretik] up on :%HERETIK_PORT%
exit /b 0
