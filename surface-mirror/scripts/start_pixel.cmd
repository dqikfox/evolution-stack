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
set PIXEL_LOG=%LOCALAPPDATA%\hermes\logs\pixel_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
set PIXEL_HEALTH=http://127.0.0.1:%PIXEL_PORT%/api/state

REM Probe BEFORE reclaiming. Pixel is a single detached process with no
REM supervisor above it, so the reclaim helper cannot tell a leftover
REM Pixel from a stranger - it would kill whatever holds the port. Asking
REM first keeps the launcher idempotent: a healthy Pixel is left alone,
REM and the reclaim only ever runs against a port that is NOT answering.
REM The probe also checks the body, so "something answered 200 on :8520"
REM is not mistaken for "Pixel answered".
"%PIXEL_PY%" "%PROBE%" "%PIXEL_HEALTH%" 3 --contains "activeCharacter"
if not errorlevel 1 (
    echo [pixel] already up on :%PIXEL_PORT% - Pixel answered /api/state, nothing to do.
    exit /b 0
)

REM The port is not answering. Clear a leftover Pixel that is still holding
REM it, but never a stranger: the reclaim refuses a holder that does not
REM carry our marker.
"%PIXEL_PY%" "%RECLAIMER%" reclaim --port %PIXEL_PORT% --marker "pixel\server.py"
if errorlevel 1 (
    echo [pixel] FAILED: could not reclaim :%PIXEL_PORT%
    exit /b 1
)

if not exist "%PIXEL_PY%" (
    echo [pixel] FAILED: interpreter missing at %PIXEL_PY%
    exit /b 1
)
if not exist "%PIXEL_PROJECT%\server.py" (
    echo [pixel] FAILED: server missing at %PIXEL_PROJECT%\server.py
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

echo [pixel] starting (server log: %PIXEL_LOG%)...
cd /d "%PIXEL_PROJECT%"
"%PIXEL_PY%" "%SPAWNER%" --log "%PIXEL_LOG%" --err "%PIXEL_LOG%.err" --cwd "%PIXEL_PROJECT%" -- "%PIXEL_PY%" "%PIXEL_PROJECT%\server.py" --port %PIXEL_PORT%
if errorlevel 1 (
    echo [pixel] FAILED: spawner returned an error - see %PIXEL_LOG%.err
    exit /b 1
)

echo [pixel] waiting for :%PIXEL_PORT%...
"%PIXEL_PY%" "%WAITER%" "%PIXEL_HEALTH%" 120 2
if errorlevel 1 (
    echo [pixel] FAILED: the endpoint did not answer within 120s - see the log
    exit /b 1
)
echo [pixel] up on :%PIXEL_PORT%
exit /b 0
