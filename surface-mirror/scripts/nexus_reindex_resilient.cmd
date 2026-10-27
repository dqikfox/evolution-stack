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
REM "resume" as the second argument means: do NOT start with a fresh
REM pass. The collection already holds work, and a fresh pass would
REM throw it away to rebuild it identically.
set FIRSTPASS=fresh
if "%2"=="resume" set FIRSTPASS=resume
set PASS=0
set LOCKFILE=E:\ultron-memory\nexus-core\data\REBUILD.lock
REM The rebuild runs in SLICES. Each slice indexes a bounded number of
REM notes, COMMITS them, and exits 0. A rebuild that is killed every
REM few minutes can never finish if every attempt tries to do the
REM whole corpus - on 2026-10-27 a rebuild ran twenty times and
REM completed none of them, because no single attempt was allowed to
REM finish. A slice changes the shape of the work: each attempt does a
REM bounded amount, the next resumes from what is left, and the
REM sequence converges no matter how often it is interrupted.
set SLICE=200
REM Records that the collection has already been dropped for this
REM cycle, so a run that follows a killed one resumes instead of
REM dropping the index all over again.
set FRESHMARK=E:\ultron-memory\nexus-core\data\REBUILD.freshcycle

cd /d "%NEXUS_PROJECT%"

REM THE WRAPPER HOLDS THE LOCK FOR THE WHOLE SEQUENCE.
REM
REM Each pass releases the lock when it ends, and a twenty-second gap
REM with no lock is a window in which the five-minute health job starts
REM NEXUS - onto a half-built index, while the brain is down for a
REM reason nothing reports. The next pass then finds the port taken.
REM
REM So the wrapper takes the lock once, before the first pass, and every
REM pass runs with --lock-held: the tool neither takes it nor releases
REM it. The lock comes off only when the whole sequence is done, which
REM is the one moment the server is genuinely allowed to come back.
if not exist "%LOCKFILE%" (
    echo vector index rebuild started %DATE% %TIME% (wrapper, pid %RANDOM%) > "%LOCKFILE%"
)

REM Control flow is goto-based on purpose: a parenthesised block ends at
REM the first unbalanced ")", and cmd reports that as "was unexpected at
REM this time".
REM THE FIRST PASS DROPS THE COLLECTION ONLY ONCE PER CYCLE.
REM
REM The first pass is fresh: it drops the collection and rebuilds it
REM from zero, because the chunking policy changed and an incremental
REM run would leave a mixture of two different chunking regimes in the
REM index.
REM
REM But a fresh pass DESTROYS the index, and the rebuild on this host
REM gets killed - so a night whose rebuild dies loses that night's
REM work to the next night's fresh pass, and the estate never finishes
REM a clean index. The marker file records that the drop has already
REM happened for this cycle, so a run that follows a killed one RESUMES
REM from what was indexed instead of dropping it all over again.
REM
REM The marker is cleared once the rebuild completes, so the next
REM scheduled cycle starts clean.
if exist "%FRESHMARK%" (
    echo ==== resuming: the collection was already dropped for this cycle ==== >> "%LOG%"
    set FIRSTPASS=resume
) else (
    set FIRSTPASS=fresh
)
if "%2"=="resume" set FIRSTPASS=resume

:loop
if %PASS% geq %MAXPASSES% goto :exhausted
set /a PASS+=1
echo ==== pass %PASS% of %MAXPASSES% started %DATE% %TIME% ==== >> "%LOG%"
set PASSLOG=%LOG%.pass%PASS%

if %PASS%==1 if "%FIRSTPASS%"=="fresh" goto :fresh
goto :resume

:fresh
echo ==== dropping the collection and rebuilding it from zero ==== >> "%LOG%"
echo vector index rebuild cycle started %DATE% %TIME% > "%FRESHMARK%"
"%NEXUS_VENV%" -u tools\reindex_vectors.py --fresh --yes-i-mean-it --lock-held --max-notes=%SLICE% > "%PASSLOG%" 2>> "%ERRLOG%"
goto :after

:resume
"%NEXUS_VENV%" -u tools\reindex_vectors.py --lock-held --max-notes=%SLICE% > "%PASSLOG%" 2>> "%ERRLOG%"
goto :after

:after
REM THE EXIT CODE IS NOT PROOF. A failed redirection leaves errorlevel
REM at 0 - the command never ran, so there is no error to report - and
REM a wrapper that trusts the exit code calls that a completed rebuild.
REM The tool prints "Vector search is now in sync" when it is actually
REM done, so the LOG is the authority and the exit code is a hint.
REM The completion marker is in the PASS log, not the wrapper log: the
REM tool's own output is written per pass, because a single shared file
REM written by two processes loses everything when one of them is
REM killed - and the output of a killed pass is exactly the output
REM that says why.
findstr /C:"Vector search is now in sync" "%PASSLOG%" >nul 2>&1
if not errorlevel 1 goto :complete
echo ==== pass %PASS% did not complete, resuming ==== >> "%LOG%"
REM SLEEP WITHOUT PATH AMBIGUITY.
REM
REM "timeout /t 20" is not portable on this host: Git for Windows ships a
REM GNU "timeout" in usr\bin, and that directory comes BEFORE
REM C:\Windows\System32 on the PATH. So "timeout /t 20 /nobreak" is
REM resolved to the GNU program, which rejects "/t" as an invalid
REM time interval and returns at once. The pause this line was
REM supposed to make never happened - and it failed loudly enough
REM that anyone reading the output would have had to work out what
REM it meant.
REM
REM "ping -n 21 127.0.0.1 > nul" is the portable sleep: it waits about
REM twenty seconds and resolves through the ordinary PATH with no
REM ambiguity.
ping -n 21 127.0.0.1 > nul
goto :loop

:complete
echo ==== rebuild COMPLETED on pass %PASS% at %DATE% %TIME% ==== >> "%LOG%"
del /q "%LOCKFILE%" >nul 2>&1
REM The cycle is done, so the NEXT scheduled run drops the collection
REM and starts a clean one again.
del /q "%FRESHMARK%" >nul 2>&1
exit /b 0

:exhausted
echo ==== rebuild did not complete within %MAXPASSES% passes ==== >> "%LOG%"
REM The lock STAYS on. The index is not finished, so the server must
REM not come back onto it.
REM
REM The fresh-cycle marker STAYS too. The next run resumes from what
REM was indexed instead of dropping it and starting from zero - which
REM is the difference between a rebuild that eventually finishes and
REM one that never does.
exit /b 1
