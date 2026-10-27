@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the TESSERACT dashboard (:8705).
REM
REM Exits 0 as soon as :8705 answers 200, so it is safe to call from a
REM scheduler, the service healer, the Startup folder, or by hand.
REM
REM The order in this file is the whole point:
REM
REM  1. DEPENDENCIES FIRST. Every tool this launcher needs is checked
REM     before it touches anything. A launcher that reclaims the port and
REM     THEN discovers its probe is missing has already destroyed a
REM     working service in order to report a missing file.
REM
REM  2. THE DECISION BEFORE THE DESTRUCTION. service_control.prepare
REM     probes the service first, then answers one question - is the port
REM     free, held by an orphan of ours, held by a stranger, or owned by a
REM     healthy supervised chain - and it only ever destroys something when
REM     that is the only correct action. A healthy service is never torn
REM     down to be rebuilt.
REM
REM  3. THE SERVER MUST NOT INHERIT THE CALLER'S STDOUT. A process started
REM     with inheritable handles receives copies of every inheritable handle
REM     in its parent, so if the parent was started by a caller that captured
REM     stdout into a pipe (an agent tool, CI, a shell substitution), the
REM     server keeps that pipe open for its whole life and the caller blocks
REM     in read() until the SERVER exits instead of until this launcher does.
REM     `cmd start` and PowerShell `Start-Process` both create the child that
REM     way (measured: both HELD the caller's pipe). spawn_detached.py uses
REM     Python's close_fds=True, which passes an explicit handle-inheritance
REM     list, so the child inherits nothing but its log file (measured:
REM     RELEASED the pipe).
REM
REM  4. THE WAIT MUST NOT BE CHARGED POWERSHELL STARTUP. The probe is a
REM     stdlib urllib call in the project's own interpreter - tens of
REM     milliseconds, and identical on every host.
REM
REM Usage:  start_tesseract.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own venv's
REM packages, not the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=

REM The application root is RESOLVED, not hardcoded.
REM
REM TESSERACT has two branches: master is the Python FastAPI app, main is
REM the TypeScript lattice rewrite. They share one directory, and the other
REM agent checks out main there - which removes the Python app's files from
REM disk and leaves a tree that cannot start this service. A launcher that
REM hardcodes one path breaks the moment the tree is switched underneath
REM it, and a service that cannot be restarted is not a service.
REM
REM So the first candidate that actually contains server.py wins:
REM   1. TESSERACT_ROOT, if the operator set it
REM   2. the canonical worktree, pinned to master - it keeps the Python
REM      app and the live data\ directory
REM   3. the shared checkout, for when the tree is on master
set TESS_PROJECT=
for %%D in (
    "%TESSERACT_ROOT%"
    "C:\Users\KING\Projects\TESSERACT-py"
    "C:\Users\KING\Projects\TESSERACT"
) do (
    if not defined TESS_PROJECT (
        if exist "%%~D\server.py" set TESS_PROJECT=%%~D
    )
)
if not defined TESS_PROJECT (
    echo [tesseract] FAILED: no server.py found in any known root
    echo [tesseract]   TESSERACT_ROOT=%TESSERACT_ROOT%
    echo [tesseract]   tried: C:\Users\KING\Projects\TESSERACT-py, C:\Users\KING\Projects\TESSERACT
    exit /b 1
)
echo [tesseract] app root: %TESS_PROJECT%
set TESS_PY=%TESS_PROJECT%\.venv\Scripts\python.exe
set TESS_PORT=8705
set TESS_LOG=%LOCALAPPDATA%\hermes\logs\tesseract_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
set TESS_HEALTH=http://127.0.0.1:%TESS_PORT%/health
REM The marker names our own process. The house tooling identifies a
REM supervisor by a command line that ENDS with the script name, and a
REM leftover by the marker appearing anywhere in the command line.
set TESS_MARKER=TESSERACT\start.py

REM --- 1. DEPENDENCIES FIRST. Nothing is destroyed before this block passes.
if not exist "%TESS_PY%" (
    echo [tesseract] FAILED: interpreter missing at %TESS_PY%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [tesseract] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [tesseract] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%RECLAIMER%" (
    echo [tesseract] FAILED: reclaimer missing at %RECLAIMER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [tesseract] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

REM --- 2. THE DECISION. The service is probed before anything is destroyed.
echo [tesseract] checking port %TESS_PORT%...
"%TESS_PY%" "%RECLAIMER%" prepare --port %TESS_PORT% --marker "%TESS_MARKER%" --health "%TESS_HEALTH%"
set RC=%ERRORLEVEL%
if "%RC%"=="2" (
    echo [tesseract] already up on :%TESS_PORT% - healthy and supervised, nothing to do.
    exit /b 0
)
if "%RC%"=="1" (
    echo [tesseract] FAILED: :%TESS_PORT% is held by a process that is not ours
    exit /b 1
)
REM RC=0: the port is free, or an orphan of ours was reclaimed.

echo [tesseract] starting (server log: %TESS_LOG%)...
cd /d "%TESS_PROJECT%"
"%TESS_PY%" "%SPAWNER%" --log "%TESS_LOG%" --err "%TESS_LOG%.err" --cwd "%TESS_PROJECT%" -- "%TESS_PY%" "%TESS_PROJECT%\start.py"
if errorlevel 1 (
    echo [tesseract] FAILED: spawner returned an error - see %TESS_LOG%.err
    exit /b 1
)

echo [tesseract] waiting for :%TESS_PORT%...
"%TESS_PY%" "%WAITER%" "%TESS_HEALTH%" 180 2
if errorlevel 1 (
    echo [tesseract] FAILED: the endpoint did not answer within 180s - see the log
    exit /b 1
)
echo [tesseract] up on :%TESS_PORT%
exit /b 0
