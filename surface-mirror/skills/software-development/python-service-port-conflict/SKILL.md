---
name: python-service-port-conflict
description: Use for resolving [Errno 10048] socket binding errors.
---

# Service Port Conflict Resolution Workflow

Use this workflow whenever a service refuses to bind with `[Errno 10048]` (Windows) / `EADDRINUSE` (Unix), OR when a port appears open but the wrong service is answering requests on it. Applies to Node.js, Python, and any framework launched as a child process.

## When to use

- `[Errno 10048]` (Windows) or `EADDRINUSE` (Unix) on bind
- Service "starts" per logs but clients get foreign error shapes (404 with `not_found_error`, 415, etc.)
- `localhost:PORT` returns one app, `127.0.0.1:PORT` returns a different one — IPv4/IPv6 dual-bind
- Two services both claim to own the same port
- `netstat` shows MULTIPLE PIDs LISTENING on the same port — SO_REUSEADDR multi-bind

If only one service is involved and it cleanly crashes, look at the framework's startup error stream first — not this skill.

## The Problem
A zombie or legacy process (often an unkillable PID) is holding the target port hostage, preventing new service instances from starting even if they appear dead in logs. **Or** two services both think they own the port because Windows lets them share it across IPv4 and IPv6.

## Diagnostic: which process actually owns the port

Windows (`powershell`):
```powershell
Get-NetTCPConnection -LocalPort <PORT> -State Listen | Select-Object OwningProcess, ProcessName
Get-Process -Id <pid> | Select-Object Id, ProcessName, Path
```

Unix / WSL:
```bash
ss -tlnp 'sport = :<PORT>'          # preferred
lsof -i :<PORT>                      # fallback
```

**Identify by PID — NOT by image name.** On Windows, framework binaries hide behind generic names. `uvicorn` runs as `python.exe`, `next dev` runs as `node.exe`, `fastapi` runs as `python.exe`. `taskkill /F /IM <framework>.exe` silently does nothing because no process with that image name exists. Always go through the PID.

## Verified Debugging Path

1.  **Identify the Culprit** using the diagnostic above (`Get-NetTCPConnection` on Windows, `ss -tlnp` / `lsof` on Unix).
2.  **Identify by PID — NOT by image name.** (See above.) Same trap applies to `node`, `npm`, `pnpm`, `pnpm.cmd` — vary, and to any framework launched via `python -m <framework>`.
3.  **Assess Killability**: Attempt a standard kill. If it fails with "Access Denied" (common for system/permission-restricted processes), **do not keep retrying**. Abandon the kill strategy and move to migration.
    *   Command: `taskkill /F /PID <pid>`
4.  **Verify Socket Status independently** (both addresses): Probe BOTH `127.0.0.1` AND `[::1]`/`localhost`. If they return different service responses (one returns your app's JSON, the other returns a foreign error shape), the IPv4/IPv6 dual-bind trap is in effect — kill the foreign PID, not yours.
5.  **The Migration Strategy (Preferred)**: Instead of fighting unkillable PIDs, update your project's configuration (`core/config.py`) to use a new default port. 
    *   Update `PORT = <NEW_PORT>` in config.
6.  **Verification via Probe**: After re-launching on the new port, run an independent probe from a pre-existing process context to confirm the service responds with its health endpoint (`/health`).

## Pitfalls & Lessons Learned
*   **Avoid "Patching Chaos"**: When updating critical files like `server.py` or `start.py`, avoid iterative, small `patch` calls if they risk broken syntax (e.g., half-written imports). Use **atomic `write_file`** to replace the entire file with a known-good template/version to ensure structural integrity and prevent `NameError: name 'app' is not defined`.
*   **Do Not Overly Rely on Logs**: Log output for failed starts can be misleading due to buffered writes or momentary successful initialization before an immediate crash. The network socket state (`Get-NetTCPConnection` on Windows / `netstat` / `lsof -i :PORT` on Linux) are the only sources of truth.
*   **The IPv4/IPv6 dual-bind trap on Windows**: `0.0.0.0:8080` and `[::]:8080` are *different* sockets. Two services can both "be on 8080" — one on IPv4, one on IPv6. When the new process crashes mid-startup after binding IPv6 but before binding IPv4, the old IPv4 holder keeps serving. `localhost` resolves IPv6 first (Windows default), so the new service appears live from a curl to `localhost` while external probes on the literal IPv4 address hit the old service. Symptom: `localhost/health` returns 200 but `127.0.0.1/health` returns a foreign error shape (415 from FastAPI, `not_found_error` JSON, etc.). Fix: bind explicitly to `127.0.0.1` in the new service (`HOST=127.0.0.1 node server.js`) to fail-fast on collision, or kill the IPv4 holder before starting. See `references/ipv4-ipv6-dual-bind.md` for the full reproduction recipe.
*   **Node.js silently exits on a port collision** — no stack trace, no exit code in some wrappers; the log just stops after the last successful line. Always follow a Node port-bind with a `sleep 2 && curl http://127.0.0.1:PORT/health` independent probe; never trust "server started" log lines alone.
*   **SO_REUSEADDR multi-bind: the new server starts with NO error while stale instances keep serving** — Python's `ThreadingHTTPServer` sets `allow_reuse_address`, and on Windows that lets several processes bind the same `127.0.0.1:PORT` at once; `EADDRINUSE` never fires, and connections round-robin between old and new code, so a just-deployed route can "not exist" intermittently. After ANY redeploy of a stdlib Python HTTP server, check `netstat -ano | grep ":PORT.*LISTENING"` and expect exactly ONE PID — kill every listener by PID before starting the new one, then re-probe the new route.

## References

* [references/ipv4-ipv6-dual-bind.md](references/ipv4-ipv6-dual-bind.md) — full reproduction + diagnostics for the dual-bind trap
