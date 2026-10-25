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

## A service's identity is not always on the port holder

The reclaim decides whether the process holding a port is "ours" by looking for a marker. That check used to look ONLY at the holder, and it refused our own orphan: TESSERACT's supervisor had died, leaving its uvicorn child on :8705 - a bare uv python whose command line carries no project token at all. Every restart then failed with "could not reclaim".

The identity lives in the **ancestry**: the venv shim (`TESSERACT\.venv\Scripts\python.exe`) is the parent and carries the project.

Rules:

- Match the marker against the whole chain, but count only its **interpreter** members. A shell whose command line merely mentions the project (a transcript command, a grep) must never make a stranger look like ours.
- A marker with a backslash also matches its project token, so the marker's directory is a service-specific identity of its own.
- A supervisor's command line must END with the script; an orphan's contains it. Two different tests, two different shapes.

## Spawning something that must outlive you

- `DETACHED_PROCESS` is `0x00000008`. `0x08000000` is `CREATE_NO_WINDOW` - it hides the console and does nothing else. A constant passed under a comment that says DETACHED_PROCESS is a bug's cover story: the child stays in the caller's process group and dies when the caller's session is reaped.
- The house `spawn_detached.py` is the right way: its own process group, closed handles, file-backed stdio, and it **exits immediately** - which breaks the ancestry chain.
- A heal that leaves the service inside a short-lived session is a heal that works exactly once.

## The console code page will kill your launcher

This host's console code page is cp1252. A launcher that prints a box-drawing character - or that lets a child tool's UTF-8 error text reach its stdout - dies with `UnicodeEncodeError`, and **a launcher that dies is a dead service**, whatever the cause. It happened here: the 1Password CLI's rate-limit notice took the dashboard down.

- Reconfigure `sys.stdout`/`sys.stderr` to UTF-8 with `errors="replace"` before anything can print.
- Decode subprocess output with an explicit `encoding="utf-8", errors="replace"`.
- Set `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` for spawned children.
- A vault problem must cost the SECRETS, never the service.

## A scheduled task runs with a minimal environment

A bare `python` does not resolve inside a Scheduled Task. Both estate watchdogs had been failing with `0x80070002` (file not found) while their scripts sat on disk - the estate had no automatic recovery, and the only symptom was a `Last Result` nobody read.

- Name an ABSOLUTE interpreter, and put the work in a `.cmd` wrapper so the task's action has no quoting problem.
- The wrapper must refuse to run (non-zero) when the interpreter or script is missing, instead of exiting 0 and looking healthy.
- Read `schtasks /query /tn <name> /fo LIST /v` -> `Last Result` after every change. A task that cannot start is invisible from the filesystem.
- The watcher's budget must EXCEED the launcher's own wait, or the watcher kills the launcher mid-wait and the service never comes up.

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
