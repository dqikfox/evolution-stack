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
| `os.kill(pid, 0)` as a liveness test | **It KILLS the process.** CPython routes `os.kill` to `TerminateProcess` on Windows, so the "check" destroys its subject. | Use `ctypes`: `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess` and compare against `STILL_ACTIVE` (259). Then TEST that the subject is still alive after the check. |
| Inspecting processes through a shell-quoted PowerShell filter | The filter silently returns an empty list (quoting eaten by the outer shell), and every assertion built on it becomes vacuous. | Use `psutil.process_iter(["pid","ppid","name","cmdline"])` for process inspection, and assert the helper FOUND something before trusting what it says. |
| Counting a venv shim and its interpreter as two services | A service launched through a venv shim is TWO processes with the same script in the command line, so the count double-reports. | Count chain ROOTS: a process whose parent does not carry the same marker. |
| Reclaiming a port by killing whatever holds it | A marker-based reclaim that only looks for a matching SUPERVISOR kills any unrelated process on the port - and a single detached service has no supervisor by definition, so it is always "an orphan". | Match the MARKER against the holder's command line before killing it, and refuse when it does not match. A docstring promising "an unrelated process is never touched" is not an implementation: test it. |
| Reclaiming before probing in a launcher | Reclaiming is destructive. A launcher that reclaims first and probes second restarts a healthy service every time it is called. | Probe first. Probe the BODY, not just the status: "something answered 200" is not "my service answered". |

## Supervisors and the ports they own
Two supervisors for one port do not coexist, they fight. Each treats the other's child as an orphaned instance and kills it, each respawns its own, and the child that loses the bind exits 3 repeatedly with the backoff climbing. The loser is **invisible**: whoever waits for the PORT to answer is answered by the winner, so a restart script declares success while the supervisor it started is already dead.

A supervisor must therefore REFUSE to start when a live one already owns the port, and the contract has to start a second one to prove the refusal happens. See `tests/launcher_contract.py` in the Evolution stack.
