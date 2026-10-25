@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for NEXUS CORE (:8650).
REM
REM Exits 0 as soon as :8650 answers 200, so it is safe to call from a
REM scheduler, the service healer, the Startup folder, or by hand.
REM
REM The supervisor is spawned with spawn_detached.py, not `cmd start` and not
REM PowerShell `Start-Process`: both of those create the child with
REM inheritable handles, so the supervisor inherits the CALLER's stdout pipe
REM and the caller blocks in read() until the supervisor exits rather than
REM until this launcher does. close_fds=True passes an explicit
REM handle-inheritance list, so the child inherits nothing but its log file.
REM
REM The health probe is a stdlib urllib call in the NEXUS interpreter, not
REM Invoke-WebRequest: PowerShell startup costs 1-3s on a loaded host and
REM that time is charged to the wait budget.
REM
REM Usage:  start_nexus.cmd
REM ---------------------------------------------------------------------------
setlocal
set PYTHONPATH=
set PYTHONHOME=

set NEXUS_VENV=C:\Users\KING\.cache\nexus-venv\Scripts\python.exe
set NEXUS_RUNNER=E:\ultron-memory\nexus-core\run_nexus.py
set NEXUS_PROJECT=E:\ultron-memory\nexus-core
set NEXUS_PORT=8650
set NEXUS_SUP_LOG=%LOCALAPPDATA%\hermes\logs\nexus_supervisor_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
set NEXUS_HEALTH=http://127.0.0.1:%NEXUS_PORT%/health

echo [nexus] checking port %NEXUS_PORT%...
REM An ORPHAN - a killed supervisor's surviving child - answers the
REM port with no supervisor above it. It is unsupervised, it may be
REM running stale code, and nothing restarts it if it dies. The
REM launcher used to accept that as "already up" and never start a
REM supervisor, so the service only came back when someone cleared
REM the orphan by hand. Reclaim it first, then decide.
"%NEXUS_VENV%" "%RECLAIMER%" reclaim --port %NEXUS_PORT% --marker "run_nexus.py"
if errorlevel 1 (
    echo [nexus] FAILED: could not reclaim :%NEXUS_PORT%
    exit /b 1
)
"%NEXUS_VENV%" "%PROBE%" "%NEXUS_HEALTH%" 3
if not errorlevel 1 (
    echo [nexus] already up on :%NEXUS_PORT% - supervised, nothing to do.
    exit /b 0
)

if not exist "%NEXUS_VENV%" (
    echo [nexus] FAILED: interpreter missing at %NEXUS_VENV%
    exit /b 1
)
if not exist "%NEXUS_RUNNER%" (
    echo [nexus] FAILED: runner missing at %NEXUS_RUNNER%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [nexus] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [nexus] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%RECLAIMER%" (
    echo [nexus] FAILED: reclaimer missing at %RECLAIMER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [nexus] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

echo [nexus] starting supervisor (log: %NEXUS_SUP_LOG%)...
cd /d "%NEXUS_PROJECT%"
"%NEXUS_VENV%" "%SPAWNER%" --log "%NEXUS_SUP_LOG%" --err "%NEXUS_SUP_LOG%.err" --cwd "%NEXUS_PROJECT%" -- "%NEXUS_VENV%" "%NEXUS_RUNNER%"
if errorlevel 1 (
    echo [nexus] FAILED: spawner returned an error - see %NEXUS_SUP_LOG%.err
    exit /b 1
)

echo [nexus] waiting for :%NEXUS_PORT%...
"%NEXUS_VENV%" "%WAITER%" "%NEXUS_HEALTH%" 180 2
if errorlevel 1 (
    echo [nexus] FAILED: the endpoint did not answer within 180s - see %NEXUS_SUP_LOG%
    exit /b 1
)
echo [nexus] up on :%NEXUS_PORT%
exit /b 0
