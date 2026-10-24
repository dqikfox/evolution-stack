@echo off
REM Persist Q: -> E:\ alias across logons (subst is per-user, non-persistent).
REM Registered to run at user logon via Scheduled Task 'SubstQ2E'.
subst Q: E:\ 2>> "%LOCALAPPDATA%\hermes\logs\subst_failure.log"
if %errorlevel% neq 0 (
    echo [%DATE% %TIME%] Subst failed with error code %errorlevel% >> "%LOCALAPPDATA%\hermes\logs\subst_failure.log"
)
