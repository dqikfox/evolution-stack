@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for DEV DIARY (:8530).
REM
REM Exits 0 as soon as :8530 answers with the devdiary marker, so it is safe
REM to call from a scheduler, the service healer, the Startup folder, or by
REM hand.
REM
REM The order in this file is the whole point:
REM
REM  1. DEPENDENCIES FIRST. Every tool this launcher needs is checked before
REM     it touches anything. A launcher that reclaims the port and THEN
REM     discovers its probe is missing has already destroyed a working
REM     service in order to report a missing file.
REM
REM  2. THE DECISION BEFORE THE DESTRUCTION. service_control.prepare probes
REM     the service first, then answers one question - is the port free,
REM     held by an orphan of ours, held by a stranger, or owned by a healthy
REM     chain - and it only ever destroys something when that is the only
REM     correct action. A healthy service is never torn down to be rebuilt.
REM
REM  3. THE SERVER MUST NOT INHERIT THE CALLER'S STDOUT. A process started
REM     with inheritable handles receives copies of every inheritable handle
REM     in its parent, so if the parent was started by a caller that captured
REM     stdout into a pipe (an agent tool, CI, a shell substitution), the
REM     server keeps that pipe open for its whole life and the caller blocks
REM     in read() until the SERVER exits instead of until this launcher does.
REM     spawn_detached.py uses Python's close_fds=True, so the child inherits
REM     nothing but its log file.
REM
REM  4. THE WAIT MUST NOT BE CHARGED POWERSHELL STARTUP. The probe is a
REM     stdlib urllib call in the project's own interpreter - tens of
REM     milliseconds, and identical on every host.
REM
REM Usage:  start_devdiary.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own packages, not
REM the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=
set PYTHONSTARTUP=
set VIRTUAL_ENV=

set DD_PROJECT=C:\Users\KING\Projects\dev diary
set DD_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set DD_PORT=8530
set DD_LOG=%LOCALAPPDATA%\hermes\logs\devdiary_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
set DD_HEALTH=http://127.0.0.1:%DD_PORT%/api/health
REM The marker names our own process. The house tooling identifies a service
REM by a command line that ENDS with the script name, and a leftover by the
REM marker appearing anywhere in the command line.
set DD_MARKER=dev_diary_server.py

REM --- 1. DEPENDENCIES FIRST. Nothing is destroyed before this block passes.
if not exist "%DD_PY%" (
    echo [devdiary] FAILED: interpreter missing at %DD_PY%
    exit /b 1
)
if not exist "%DD_PROJECT%\dev_diary_server.py" (
    echo [devdiary] FAILED: server missing at %DD_PROJECT%\dev_diary_server.py
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [devdiary] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [devdiary] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%RECLAIMER%" (
    echo [devdiary] FAILED: reclaimer missing at %RECLAIMER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [devdiary] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

REM --- 2. THE DECISION. The service is probed before anything is destroyed.
echo [devdiary] checking port %DD_PORT%...
"%DD_PY%" "%RECLAIMER%" prepare --port %DD_PORT% --marker "%DD_MARKER%" --health "%DD_HEALTH%" --contains "devdiary"
set RC=%ERRORLEVEL%
if "%RC%"=="2" (
    echo [devdiary] already up on :%DD_PORT% - healthy, nothing to do.
    exit /b 0
)
if "%RC%"=="1" (
    echo [devdiary] FAILED: :%DD_PORT% is held by a process that is not ours
    exit /b 1
)
REM RC=0: the port is free, or an orphan of ours was reclaimed.

echo [devdiary] starting (server log: %DD_LOG%)...
cd /d "%DD_PROJECT%"
"%DD_PY%" "%SPAWNER%" --log "%DD_LOG%" --err "%DD_LOG%.err" --cwd "%DD_PROJECT%" -- "%DD_PY%" "%DD_PROJECT%\dev_diary_server.py"
if errorlevel 1 (
    echo [devdiary] FAILED: spawner returned an error - see %DD_LOG%.err
    exit /b 1
)

echo [devdiary] waiting for :%DD_PORT%...
"%DD_PY%" "%WAITER%" "%DD_HEALTH%" 120 2
if errorlevel 1 (
    echo [devdiary] FAILED: the endpoint did not answer within 120s - see %DD_LOG%
    exit /b 1
)
echo [devdiary] up on :%DD_PORT%
exit /b 0
