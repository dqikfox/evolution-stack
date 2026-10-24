@echo off
REM Start Hermes gateway outside Job Objects via Scheduled Task
schtasks /Run /TN Hermes_Gateway
exit /b %ERRORLEVEL%
