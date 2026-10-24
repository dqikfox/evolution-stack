---
name: windows-process-audit
description: "Audit Windows processes and network listeners via WMI."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [windows, process, debugging, net/netstat, wmic]
---

# Windows Process & Network Auditing

## Overview
Windows handles networking and process management via several layers (Win32 API, WMI). When investigating why a port is busy or a process exists, blindly killing PIDs can lead to system instability or lost work in other projects.

## The Verification Pattern

### 1. Identify the Port/PID
Use `netstat` to find which PID owns the problematic port.
```powershell
netstat -ano | findstr "<PORT>"
```

### 2. Verify Identity (The Golden Rule)
**NEVER kill a PID without checking its command line first.** On Windows, multiple Python environments or even unrelated system services might share similar characteristics.
Run:
```powershell
wmic process where processid=<PID> get commandline
```
*This reveals exactly which executable and script arguments are being used.*

### 3. Safe Termination
Only once you have verified it is a "zombie" or redundant instance of your development server should you proceed:
```powershell
taskkill /F /PID <PID>
```

## When to Use
- Before clearing port conflicts for `uvicorn`, `flask`, or `fastapi`.
- During cleanup of broken build/test processes in the background.
- Investigating why a specific Python dependency (like an LLM runner) is still consuming RAM even after the terminal was closed.

## Pitfalls
| Mistake | Consequence | Fix |
|--------|-------------|-----|
| Killing PID without `wmic` check | May kill NEXUS, Ollama, or system services. | Always run the identity check first. |
| Relying on task manager name only | Task Manager might just show "python.exe", hiding which project it is. | Use `commandline` via WMI for truth. |
