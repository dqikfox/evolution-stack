@echo off
REM ---------------------------------------------------------------------------
REM Resilient vector-index rebuild for NEXUS CORE.
REM
REM The first pass is FRESH: it drops the collection and rebuilds it from
REM zero, because the chunking policy changed and an incremental run would
REM leave a mixture of two different chunking regimes in the index.
REM
REM Every pass after that is RESUMABLE: the upsert is keyed on the note id,
REM so a pass that was killed halfway keeps the work it completed. A rebuild
REM that dies is an event on this host, not an exception - on 2026-10-27 it
REM died three times - and the only way through is to resume, not to start
REM over.
REM
REM The lock is taken inside the tool BEFORE the port is checked, so no
REM launcher in the estate can start the server while this runs.
REM
REM Usage:  nexus_reindex_resilient.cmd [max_passes]
REM ---------------------------------------------------------------------------
setlocal
set PYTHONPATH=
set PYTHONHOME=

set NEXUS_VENV=C:\Users\KING\.cache\nexus-venv\Scripts\python.exe
set NEXUS_PROJECT=E:\ultron-memory\nexus-core
REM A UNIQUE log per run. A fixed name collides with a previous run
REM that still holds the file open, and Windows then fails the
REM redirection - which silently turns the whole rebuild into a no-op.
set RUNID=%RANDOM%%RANDOM%
set LOG=%LOCALAPPDATA%\hermes\logs\nxr_%RUNID%.log
set ERRLOG=%LOG%.err

set MAXPASSES=%1
if "%MAXPASSES%"=="" set MAXPASSES=8
set PASS=0

cd /d "%NEXUS_PROJECT%"

REM Control flow is goto-based on purpose: a parenthesised block ends at
REM the first unbalanced ")", and cmd reports that as "was unexpected at
REM this time".
:loop
if %PASS% geq %MAXPASSES% goto :exhausted
set /a PASS+=1
echo ==== pass %PASS% of %MAXPASSES% started %DATE% %TIME% ==== >> "%LOG%"

if %PASS%==1 goto :fresh
goto :resume

:fresh
"%NEXUS_VENV%" -u tools\reindex_vectors.py --fresh >> "%LOG%" 2>> "%ERRLOG%"
goto :after

:resume
"%NEXUS_VENV%" -u tools\reindex_vectors.py >> "%LOG%" 2>> "%ERRLOG%"
goto :after

:after
REM THE EXIT CODE IS NOT PROOF. A failed redirection leaves errorlevel
REM at 0 - the command never ran, so there is no error to report - and
REM a wrapper that trusts the exit code calls that a completed rebuild.
REM The tool prints "Vector search is now in sync" when it is actually
REM done, so the LOG is the authority and the exit code is a hint.
findstr /C:"Vector search is now in sync" "%LOG%" >nul 2>&1
if not errorlevel 1 goto :complete
echo ==== pass %PASS% did not complete, resuming ==== >> "%LOG%"
timeout /t 20 /nobreak >nul
goto :loop

:complete
echo ==== rebuild COMPLETED on pass %PASS% at %DATE% %TIME% ==== >> "%LOG%"
exit /b 0

:exhausted
echo ==== rebuild did not complete within %MAXPASSES% passes ==== >> "%LOG%"
exit /b 1
