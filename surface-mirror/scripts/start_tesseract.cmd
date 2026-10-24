@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the TESSERACT dashboard (:8705).
REM
REM Exits 0 as soon as :8705 answers 200, so it is safe to call from a
REM scheduler, the service healer, the Startup folder, or by hand.
REM
REM Two things this file exists to get right:
REM
REM  1. The server must not inherit the CALLER's stdout. A process started
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
REM  2. The wait must not be charged PowerShell startup. The probe is a
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

set TESS_PROJECT=C:\Users\KING\Projects\TESSERACT
set TESS_PY=%TESS_PROJECT%\.venv\Scripts\python.exe
set TESS_PORT=8705
set TESS_LOG=%LOCALAPPDATA%\hermes\logs\tesseract_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set TESS_HEALTH=http://127.0.0.1:%TESS_PORT%/health

echo [tesseract] checking port %TESS_PORT%...
"%TESS_PY%" "%PROBE%" "%TESS_HEALTH%" 3
if not errorlevel 1 (
    echo [tesseract] already up on :%TESS_PORT% - nothing to do.
    exit /b 0
)

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
if not exist "%PROBE%" (
    echo [tesseract] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

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
