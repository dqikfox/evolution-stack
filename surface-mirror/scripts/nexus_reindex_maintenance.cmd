@echo off
REM THRONE_Nexus_Reindex - nightly vector index rebuild for NEXUS CORE.
REM
REM This is MAINTENANCE, not a service start. It stops NEXUS, rebuilds
REM the vector index, and starts NEXUS again - in that order, and the
REM service is restored whether the rebuild succeeds or fails.
REM
REM The interpreter is ABSOLUTE: a Scheduled Task runs with a minimal
REM environment where "python" does not resolve, and a task that cannot
REM find its interpreter fails with 0x80070002 while its script sits on
REM disk looking perfectly fine.
REM
REM PYTHONPATH is cleared because the ambient environment points at a
REM different installation's packages, and the wrong packages under the
REM right interpreter is a confusing way to fail.
setlocal
set "PYTHONPATH="
set "PYTHONHOME="
set "HERMES_PY=C:\Users\KING\.cache\nexus-venv\Scripts\python.exe"
set "MAINT=C:\Users\KING\AppData\Local\hermes\scripts\nexus_reindex_maintenance.py"
if not exist "%HERMES_PY%" (
    echo [reindex] FAILED: interpreter missing at %HERMES_PY%
    exit /b 2
)
if not exist "%MAINT%" (
    echo [reindex] FAILED: maintenance script missing at %MAINT%
    exit /b 2
)
"%HERMES_PY%" "%MAINT%"
exit /b %errorlevel%
