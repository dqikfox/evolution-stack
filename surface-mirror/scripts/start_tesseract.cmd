@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the TESSERACT dashboard (:8705).
REM
REM Why this exists instead of calling start.py directly: the server's stdout
REM has to land in a file, not in whatever console happened to launch it. A
REM Hermes background session that dies leaves its pipe open, and a server
REM still attached to that pipe keeps feeding a dead buffer - endless
REM heartbeats, and no readable log. Redirecting here, at the batch level,
REM covers the whole process tree (start.py -> op run -> uvicorn), because
REM every child inherits these handles.
REM
REM Exits 0 immediately when :8705 already answers, so it is safe to call
REM from a scheduler, the service healer, the Startup folder, or by hand.
REM
REM Usage:  start_tesseract.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own
REM venv's packages, not the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=

set TESS_PROJECT=C:\Users\KING\Projects\TESSERACT
set TESS_PY=%TESS_PROJECT%\.venv\Scripts\python.exe
set TESS_PORT=8705
set TESS_LOG=%LOCALAPPDATA%\hermes\logs\tesseract_stdout.log

echo [tesseract] checking port %TESS_PORT%...
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%TESS_PORT%/health -TimeoutSec 4 -UseBasicParsing).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [tesseract] already up on :%TESS_PORT% - nothing to do.
    exit /b 0
)

if not exist "%TESS_PY%" (
    echo [tesseract] FAILED: interpreter missing at %TESS_PY%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul

echo [tesseract] starting (server log: %TESS_LOG%)...
cd /d "%TESS_PROJECT%"
REM `start` (not `start /b`) so the server gets its own console and survives
REM the launcher exiting - a /b child dies with the console it shares.
REM `start` ignores a redirect applied to it, which is fine: start.py owns the
REM log file handle itself and hands it straight to the server process.
start "TESSERACT" /min "%TESS_PY%" "%TESS_PROJECT%\start.py"

echo [tesseract] waiting for :%TESS_PORT%...
set /a tries=0
:wait
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%TESS_PORT%/health -TimeoutSec 3 -UseBasicParsing).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [tesseract] up on :%TESS_PORT%
    exit /b 0
)
set /a tries+=1
if %tries% lss 30 goto wait

echo [tesseract] FAILED: :%TESS_PORT% did not open within 60s - see %TESS_LOG%
exit /b 1
