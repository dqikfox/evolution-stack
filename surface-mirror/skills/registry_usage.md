# Registry Usage Guidelines

To ensure services are correctly identified and remain 'healable' by the watchdog, strictly adhere to the separation of command components in `SERVICES.json`:

### 1. The Path Field (`start.path`)
- **Requirement**: Must contain only the absolute filesystem path to the executable or batch script.
- **Constraint**: Do **not** include any arguments or flags within this string (e.g., use `C:\bin\svc.bat`, NOT `C:\bin\svc.bat --port 80`).
- **Failure Mode**: If arguments are appended to the path, the launcher's existence check will fail because it searches for a single filename containing spaces and dashes, rendering the service unhealable.

### 2. The Arguments Field (`start.args`)
- **Requirement**: Contains all parameters, switches, and configuration flags passed to the command.
- **Example**: `--port 8660 --log debug` 

### 3. Impact on Recovery
An invalid `.path` prevents the watchdog from ever initiating a recovery attempt. Even if a process is clearly down (detected via TCP/HTTP probes), the system cannot restart it if the path itself fails the initial existence validation.