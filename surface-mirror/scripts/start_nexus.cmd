@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for NEXUS CORE (:8650).
REM
REM Exits 0 as soon as :8650 answers 200, so it is safe to call from a
REM scheduler, the service healer, the Startup folder, or by hand.
REM
REM The order in this file is the whole point:
REM
REM  1. DEPENDENCIES FIRST. Every tool is checked before the port is
REM     touched, so a launcher with a missing probe cannot destroy a
REM     working service and only then report the missing file.
REM
REM  2. THE DECISION BEFORE THE DESTRUCTION. An ORPHAN - a killed
REM     supervisor's surviving child - answers the port with no supervisor
REM     above it: unsupervised, possibly running stale code, and nothing
REM     restarts it when it dies. service_control.prepare tells the two
REM     cases apart, replaces an orphan, and refuses to touch a stranger.
REM     A healthy supervised chain is left completely alone.
REM
REM  3. THE SUPERVISOR IS SPAWNED WITH spawn_detached.py, not `cmd start`
REM     and not PowerShell `Start-Process`: both of those create the child
REM     with inheritable handles, so the supervisor inherits the CALLER's
REM     stdout pipe and the caller blocks in read() until the supervisor
REM     exits rather than until this launcher does. close_fds=True passes
REM     an explicit handle-inheritance list, so the child inherits nothing
REM     but its log file.
REM
REM  4. THE HEALTH PROBE IS A STDLIB urllib CALL in the NEXUS interpreter,
REM     not Invoke-WebRequest: PowerShell startup costs 1-3s on a loaded
REM     host and that time is charged to the wait budget.
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
REM The marker is the supervisor's script name. The house tooling
REM recognises a supervisor by a command line that ENDS with it, and a
REM leftover child by the marker appearing anywhere in the command line.
set NEXUS_MARKER=run_nexus.py

REM --- 1. DEPENDENCIES FIRST. Nothing is destroyed before this block passes.
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

REM --- 2. THE DECISION. The service is probed before anything is destroyed.
echo [nexus] checking port %NEXUS_PORT%...
"%NEXUS_VENV%" "%RECLAIMER%" prepare --port %NEXUS_PORT% --marker "%NEXUS_MARKER%" --health "%NEXUS_HEALTH%"
set RC=%ERRORLEVEL%
if "%RC%"=="2" (
    echo [nexus] already up on :%NEXUS_PORT% - healthy and supervised, nothing to do.
    exit /b 0
)
if "%RC%"=="1" (
    echo [nexus] FAILED: :%NEXUS_PORT% is held by a process that is not ours
    exit /b 1
)
REM RC=0: the port is free, or an orphan of ours was reclaimed.

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
