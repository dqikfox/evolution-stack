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
set NEXUS_ONNX_CACHE=E:\ultron-memory\.cache\chroma-models\all-MiniLM-L6-v2
set NEXUS_RUNNER=E:\ultron-memory\nexus-core\run_nexus.py
set NEXUS_PROJECT=E:\ultron-memory\nexus-core
set NEXUS_REBUILD_LOCK=%NEXUS_PROJECT%\data\REBUILD.lock
set NEXUS_PORT=8650
set NEXUS_HEALTH=http://127.0.0.1:8650/health
set HERMES_SCRIPTS=C:\Users\KING\AppData\Local\hermes\scripts
set NEXUS_LOG=%LOCALAPPDATA%\hermes\logs\nexus_supervisor_stdout.log
set NEXUS_ERRLOG=%NEXUS_LOG%.err
set NEXUS_BUDGET=180

REM --- 0. A REBUILD IN PROGRESS WINS. Checked before anything else.
REM
REM The decision is made by tools\rebuild_lock_guard.py rather than a
REM bare "if exist", because a rebuild that WEDGES must not be able to
REM hold the service down forever. The rebuild touches its lock file
REM after every batch, so the lock's age says whether the rebuild is
REM still making progress; a lock that has gone quiet is a stuck
REM rebuild, and the guard ends it and clears the lock so the service
REM can come back.
REM
REM The guard runs in its own process on purpose. A watchdog INSIDE the
REM rebuild cannot detect a stall: chroma's Rust call holds the GIL, so
REM the rebuild's own watchdog thread never runs again.
if not exist "%NEXUS_VENV%" goto :nexus_no_rebuild
"%NEXUS_VENV%" "%NEXUS_PROJECT%\tools\rebuild_lock_guard.py" "%NEXUS_REBUILD_LOCK%"
if errorlevel 1 goto :nexus_rebuild_blocks_start
goto :nexus_no_rebuild
:nexus_rebuild_blocks_start
exit /b 3
:nexus_no_rebuild

REM --- 1. DEPENDENCIES FIRST.
if not exist "%NEXUS_VENV%" (
  echo [nexus] FATAL: the NEXUS interpreter is missing: %NEXUS_VENV%
  exit /b 1
)
if not exist "%NEXUS_RUNNER%" (
  echo [nexus] FATAL: the supervisor is missing: %NEXUS_RUNNER%
  exit /b 1
)
if not exist "%HERMES_SCRIPTS%\service_control.py" (
  echo [nexus] FATAL: service_control.py is missing
  exit /b 1
)
if not exist "%HERMES_SCRIPTS%\spawn_detached.py" (
  echo [nexus] FATAL: spawn_detached.py is missing
  exit /b 1
)
if not exist "%HERMES_SCRIPTS%\nexus_health_wait.py" (
  echo [nexus] FATAL: nexus_health_wait.py is missing
  exit /b 1
)
if not exist "%NEXUS_PROJECT%\tools\rebuild_lock_guard.py" (
  echo [nexus] FATAL: rebuild_lock_guard.py is missing
  exit /b 1
)

REM --- 2. THE DECISION BEFORE THE DESTRUCTION.
REM prepare returns 0 = start it, 1 = refuse, 2 = leave it alone.
"%NEXUS_VENV%" "%HERMES_SCRIPTS%\service_control.py" prepare --port %NEXUS_PORT% --marker "run_nexus.py" --health "%NEXUS_HEALTH%"
if errorlevel 2 goto :nexus_already_healthy
if errorlevel 1 goto :nexus_refuse

REM --- 3. SPAWN THE SUPERVISOR, DETACHED.
"%NEXUS_VENV%" "%HERMES_SCRIPTS%\spawn_detached.py" --log "%NEXUS_LOG%" --err "%NEXUS_ERRLOG%" --cwd "%NEXUS_PROJECT%" -- "%NEXUS_VENV%" "%NEXUS_RUNNER%"
if errorlevel 1 (
  echo [nexus] FATAL: the supervisor could not be spawned
  exit /b 1
)

REM --- 4. PROBE WITH STDLIB urllib IN THE NEXUS INTERPRETER.
"%NEXUS_VENV%" "%HERMES_SCRIPTS%\nexus_health_wait.py" "%NEXUS_HEALTH%" %NEXUS_BUDGET%
if errorlevel 1 (
  echo [nexus] the service did not answer within the start budget
  exit /b 1
)

echo [nexus] :%NEXUS_PORT% is up
exit /b 0

:nexus_already_healthy
echo [nexus] :%NEXUS_PORT% is already healthy and supervised - nothing to do
exit /b 0

:nexus_refuse
echo [nexus] refusing to touch :%NEXUS_PORT% - the holder is not ours
exit /b 1
