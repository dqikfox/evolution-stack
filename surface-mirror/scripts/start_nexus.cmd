@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for NEXUS CORE (knowledge plane, :8650).
REM
REM Starts the supervisor (run_nexus.py), which owns the uvicorn child and
REM restarts it if it dies. The supervisor itself takes the port back from an
REM orphaned instance, so this script only has to make sure it is not already
REM running.
REM
REM Interpreter is the canonical uv venv - it is the only environment on this
REM host with numpy + chromadb installed, and without them the service starts
REM but reports "chroma: not_ready".
REM
REM Usage:  start_nexus.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own
REM venv's packages, not the site-packages of whatever launched it.
set PYTHONPATH=
set PYTHONHOME=

set NEXUS_VENV=C:\Users\KING\.cache\nexus-venv\Scripts\python.exe
set NEXUS_RUNNER=E:\ultron-memory\nexus-core\run_nexus.py
set NEXUS_PORT=8650

if not exist "%NEXUS_VENV%" (
    echo [nexus] FAILED: interpreter missing at %NEXUS_VENV%
    exit /b 1
)
if not exist "%NEXUS_RUNNER%" (
    echo [nexus] FAILED: runner missing at %NEXUS_RUNNER%
    exit /b 1
)

REM already serving? then nothing to do
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%NEXUS_PORT%/health -TimeoutSec 4 -UseBasicParsing).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [nexus] already up on :%NEXUS_PORT% - nothing to do.
    exit /b 0
)

echo [nexus] starting supervisor...
cd /d "E:\ultron-memory\nexus-core"
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul
REM redirect the supervisor's output so this console is released immediately
start "NEXUS CORE" /min "%NEXUS_VENV%" "%NEXUS_RUNNER%" >> "%LOCALAPPDATA%\hermes\logs\nexus_supervisor_stdout.log" 2>&1

echo [nexus] waiting for :%NEXUS_PORT%...
set /a tries=0
:wait
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%NEXUS_PORT%/health -TimeoutSec 3 -UseBasicParsing).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [nexus] up on :%NEXUS_PORT%
    exit /b 0
)
set /a tries+=1
if %tries% lss 30 goto wait

echo [nexus] FAILED: :%NEXUS_PORT% did not open within 60s
exit /b 1
