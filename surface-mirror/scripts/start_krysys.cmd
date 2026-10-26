@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the KRYSYS crystal shop (:8500).
REM
REM Exits 0 as soon as :8500 answers, so it is safe to call from a scheduler,
REM the service healer, the Startup folder, or by hand.
REM
REM The order in this file is the whole point:
REM
REM  1. DEPENDENCIES FIRST. Every tool is checked before the port is
REM     touched, so a launcher with a missing probe cannot destroy a
REM     working service and only then report the missing file.
REM
REM  2. THE DECISION BEFORE THE DESTRUCTION. The probe checks the BODY of
REM     /api/health, so "something answered 200 on :8500" is not mistaken
REM     for "the shop answered". A healthy shop is left completely alone.
REM
REM  3. THE SERVER MUST NOT INHERIT THE CALLER'S STDOUT. A process started
REM     with inheritable handles receives copies of every inheritable handle
REM     in the parent, so if the parent was started by a caller that captured
REM     a pipe, the child holds a duplicate of that pipe and dies with the
REM     caller's job object. The supervisor is spawned with explicit log files
REM     and no inherited handles for exactly this reason.
REM
REM  4. THE WAIT MUST NOT BE CHARGED POWERSHELL STARTUP. The probe is a
REM     stdlib urllib call - tens of milliseconds, identical on every host.
REM
REM  5. THE SHOP IS STARTED UNDER A SUPERVISOR. It used to be started with
REM     "cmd start /B", which left it holding the caller's pipe and it died
REM     with whatever launched it. krysys_supervisor.py owns the shop
REM     process for its whole life: it restarts a crash, replaces a wedge,
REM     and refuses to run a second copy (exit code 3).
REM
REM Usage:  start_krysys.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own packages, not
REM the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=
set VIRTUAL_ENV=

set KRYSYS_PROJECT=C:\Users\KING\projects\krysys-shop
set KRYSYS_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set KRYSYS_PORT=8500
set KRYSYS_LOG=%LOCALAPPDATA%\hermes\logs\krysys_supervisor.log
set KRYSYS_STDOUT=%LOCALAPPDATA%\hermes\logs\krysys_supervisor.stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set SUPERVISOR=%LOCALAPPDATA%\hermes\scripts\krysys_supervisor.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set KRYSYS_HEALTH=http://127.0.0.1:%KRYSYS_PORT%/api/health
REM The marker is the SUPERVISOR's script. The house tooling identifies a
REM supervisor by a command line that ends with the script name, and it
REM identifies a leftover shop by the marker appearing anywhere in the
REM command line.
set KRYSYS_MARKER=krysys_supervisor.py

REM --- 1. DEPENDENCIES FIRST. Nothing is destroyed before this block passes.
if not exist "%KRYSYS_PY%" (
    echo [krysys] FAILED: interpreter missing at %KRYSYS_PY%
    exit /b 1
)
if not exist "%SUPERVISOR%" (
    echo [krysys] FAILED: supervisor missing at %SUPERVISOR%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [krysys] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [krysys] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [krysys] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%KRYSYS_PROJECT%\server.js" (
    echo [krysys] FAILED: server.js missing at %KRYSYS_PROJECT%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" >nul 2>&1

REM --- 2. IS THE SHOP ALREADY HEALTHY? The body must say krysys, not just 200.
REM The marker is a bare word with no quotes: cmd strips quotes from an
REM argument like "ok":true, so the token that reaches the probe would not be
REM the token that was written. A bare word survives cmd's parsing intact.
"%KRYSYS_PY%" "%PROBE%" "%KRYSYS_HEALTH%" 5 --contains krysys >nul 2>&1
if not errorlevel 1 (
    echo [krysys] already healthy on :%KRYSYS_PORT% - nothing to do.
    exit /b 0
)

REM --- 3. START IT UNDER THE SUPERVISOR, DETACHED, WITH NO INHERITED HANDLES.
echo [%DATE% %TIME%] starting the KRYSYS shop on :%KRYSYS_PORT%... >> "%KRYSYS_LOG%"
"%KRYSYS_PY%" "%SPAWNER%" --log "%KRYSYS_STDOUT%" --err "%KRYSYS_LOG%.err" --cwd "%KRYSYS_PROJECT%" -- "%KRYSYS_PY%" "%SUPERVISOR%" >> "%KRYSYS_LOG%" 2>&1
if errorlevel 1 (
    echo [krysys] FAILED: the supervisor could not be started - see %KRYSYS_LOG%
    exit /b 1
)

REM --- 4. WAIT FOR THE SHOP TO ANSWER, THEN REPORT THE TRUTH.
REM wait_for_http.py takes: <url> [timeout] [interval]
"%KRYSYS_PY%" "%WAITER%" "%KRYSYS_HEALTH%" 60 1 >nul 2>&1
"%KRYSYS_PY%" "%PROBE%" "%KRYSYS_HEALTH%" 5 --contains krysys >nul 2>&1
if errorlevel 1 (
    echo [krysys] FAILED: the shop did not come up healthy - see %KRYSYS_LOG%
    exit /b 1
)
echo [%DATE% %TIME%] KRYSYS is healthy on :%KRYSYS_PORT%. >> "%KRYSYS_LOG%"
echo [krysys] healthy on :%KRYSYS_PORT%.
exit /b 0
