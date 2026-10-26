# Discovery Service Recovery Manual

If the discovery service on port 8660 becomes unresponsive or reports a degraded state (L09),
follow these steps to ensure a clean restart without environment drift (L15).

## Step 1: Terminate Orphaned Processes
Identify if an orphaned process is still holding the socket:
`powershell -Command "$p = Get-NetTCPConnection -LocalPort 8660 -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id $p.OwningProcess -Force }"` 

This prevents `OSError: [WinError 64]` by clearing previous instances before attempting a new bind.

## Step 2: Clean Up Stale State
Remove any stale PID or lock files that might prevent the supervisor from restarting correctly (L13):
`del %LOCALAPPDATA%\hermes\run\discovery.pid 2>nul`

## Step 3: Execute Verified Launcher
Always use the official batch launcher to ensure the correct virtual environment is loaded and PYTHONPATH/PYTHONHOME are stripped of agent-level interference (L15):
`cmd /c %LOCALAPPDATA%\hermes\scripts\start_discovery.bat`

## Step 4: Verify Health Payload
Do not just check if the port responds; inspect the component status within the JSON payload (L09).
A successful recovery must return `"status": "ready"`. If it returns `"not_ready"`, investigate `%LOCALAPPDATA%\hermes\logs\discovery.log`.