# Service Recovery Procedures

## discovery (Port 8660)
**Status:** Optional / Healable
**Recovery Command:** Refer to `%LOCALAPPDATA%/hermes/registry/services.json` for the registered startup command.
**Logs:** `%LOCALAPPDATA%/hermes/logs/discovery.log` 
**PID File:** `%LOCALAPPDATA%/hermes/pids/discovery.pid` 

*Note: If port 8660 is occupied by an orphaned process, terminate it using `taskkill /F /PID <pid>` before restarting.*