@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the Pixel character studio (:8520).
REM
REM Exits 0 as soon as :8520 answers, so it is safe to call from a scheduler,
REM the service healer, the Startup folder, or by hand.
REM
REM Two things this file exists to get right:
REM
REM  1. The server must not inherit the CALLER's stdout. A process started
REM     with inheritable handles receives copies of every inheritable handle
REM     in its parent, so if the parent was started by a caller that captured
REM     a pipe, the child holds a duplicate of that pipe. When the parent
REM     exits, the child's writes hit a CLOSED pipe. The spawner is called
REM     with explicit log files and no inherited handles for exactly this
REM     reason.
REM
REM  2. The wait must not be charged PowerShell startup. The probe is a
REM     stdlib urllib call in the project's own interpreter - tens of
REM     milliseconds, and identical on every host.
REM
REM  3. The studio is started UNDER A SUPERVISOR. Pixel used to be a single
REM     detached process, so a crash left the studio down until somebody
REM     noticed. pixel_supervisor.py restarts it, replaces it if it wedges,
REM     and refuses to run a second copy (exit code 3).
REM
REM Usage:  start_pixel.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own packages, not
REM the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=
set VIRTUAL_ENV=

REM Pixel is a stdlib-only application (Pillow is optional and guarded), so it
REM runs on the house interpreter rather than carrying a second venv.
set PIXEL_PROJECT=C:\Users\KING\projects\pixel
set PIXEL_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set PIXEL_PORT=8520
REM Two files on purpose: the supervisor's own log lines, and its raw stdout.
REM Pointing both at one file writes every line twice.
set PIXEL_LOG=%LOCALAPPDATA%\hermes\logs\pixel_supervisor.log
set PIXEL_STDOUT=%LOCALAPPDATA%\hermes\logs\pixel_supervisor.stdout.log
set PIXEL_STUDIO_LOG=%LOCALAPPDATA%\hermes\logs\pixel_stdout.log
set PIXEL_LOCK=%PIXEL_PROJECT%\logs\supervisor.lock
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
set PIXEL_HEALTH=http://127.0.0.1:%PIXEL_PORT%/api/state
REM The marker is the SUPERVISOR's script. The house tooling identifies a
REM supervisor by a command line that ends with the script name, and it
REM identifies a leftover studio by the marker appearing anywhere in the
REM command line - which is why the studio is started with
REM "--supervised-by pixel_supervisor.py".
set PIXEL_MARKER=pixel_supervisor.py

REM Probe BEFORE reclaiming. Reclaiming is destructive, so a launcher that
REM reclaims first restarts a healthy service every time it is called.
REM The probe checks the BODY, so "something answered 200 on :8520" is not
REM mistaken for "Pixel answered".
"%PIXEL_PY%" "%PROBE%" "%PIXEL_HEALTH%" 3 --contains "activeCharacter"
if not errorlevel 1 (
    echo [pixel] already up on :%PIXEL_PORT% - Pixel answered /api/state, nothing to do.
    exit /b 0
)

REM The port is not answering. Clear a leftover Pixel that is still holding
REM it, but never a stranger: the reclaim refuses a holder that does not
REM carry our marker.
"%PIXEL_PY%" "%RECLAIMER%" reclaim --port %PIXEL_PORT% --marker "%PIXEL_MARKER%"
if errorlevel 1 (
    echo [pixel] FAILED: could not reclaim :%PIXEL_PORT%
    exit /b 1
)

if not exist "%PIXEL_PY%" (
    echo [pixel] FAILED: interpreter missing at %PIXEL_PY%
    exit /b 1
)
if not exist "%PIXEL_PROJECT%\pixel_supervisor.py" (
    echo [pixel] FAILED: supervisor missing at %PIXEL_PROJECT%\pixel_supervisor.py
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [pixel] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [pixel] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%RECLAIMER%" (
    echo [pixel] FAILED: reclaimer missing at %RECLAIMER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [pixel] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul
if not exist "%PIXEL_PROJECT%\logs" mkdir "%PIXEL_PROJECT%\logs" 2>nul

REM The supervisor takes its configuration from the environment, not from
REM command-line arguments: the house tooling recognises a supervisor by a
REM command line that ENDS with the script name, so trailing arguments would
REM make the studio look unsupervised to the estate.
echo [pixel] starting the supervisor (log: %PIXEL_LOG%)...
cd /d "%PIXEL_PROJECT%"
"%PIXEL_PY%" "%SPAWNER%" --log "%PIXEL_STDOUT%" --err "%PIXEL_STDOUT%.err" --cwd "%PIXEL_PROJECT%" -- "%PIXEL_PY%" "%PIXEL_PROJECT%\pixel_supervisor.py"
if errorlevel 1 (
    echo [pixel] FAILED: spawner returned an error - see %PIXEL_STDOUT%.err
    exit /b 1
)

echo [pixel] waiting for :%PIXEL_PORT%...
"%PIXEL_PY%" "%WAITER%" "%PIXEL_HEALTH%" 120 2
if errorlevel 1 (
    echo [pixel] FAILED: the endpoint did not answer within 120s
    echo [pixel] --- last lines of %PIXEL_LOG% ---
    if exist "%PIXEL_LOG%" powershell -NoProfile -Command "Get-Content -Tail 12 '%PIXEL_LOG%'" 2>nul
    exit /b 1
)
echo [pixel] up on :%PIXEL_PORT%
exit /b 0
