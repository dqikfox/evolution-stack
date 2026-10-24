# Launching a long-lived service on THRONE

The canonical way to start a service that must outlive its launcher.
Full detail and the measured evidence behind each rule.

## The contract

A service launcher must:

1. **Return as soon as the service is healthy** — exit 0 when the port
   answers 200, so it is safe to call from a scheduler, the healer, the
   Startup folder, or by hand.
2. **Not leave the caller waiting on the service.** A launcher that captures
   output must release the caller's pipe when it exits.
3. **Not charge process-startup cost to the health budget.**
4. **Fail fast** when a helper is missing, instead of waiting out the whole
   budget.

## Rule 1: the child must not inherit the caller's stdout

A process created with inheritable handles receives copies of *every*
inheritable handle in its parent, not just the three std handles. If the
parent was started by a caller that captured stdout into a pipe — an agent
tool, CI, `$(...)` in a shell — the write end of that pipe is inheritable,
so the long-lived service keeps it open for its whole life. The caller then
blocks in `read()` until the **service** exits, not until the **launcher**
exits.

Measured on THRONE (probe: run the launcher with `stdout=PIPE`, wait for the
launcher to exit, then check whether the pipe reaches EOF):

| Mechanism | Result |
|---|---|
| `cmd start "T" /min prog` | **HELD** the pipe |
| `cmd start` + inner `cmd /c` | **HELD** the pipe |
| PowerShell `Start-Process -RedirectStandardOutput` | **HELD** the pipe |
| Python `Popen(..., close_fds=True)` | **RELEASED** the pipe |

`close_fds=True` is the difference: Python passes an explicit
handle-inheritance list, so the child inherits only the handles it was meant
to get.

Use `spawn_detached.py` in `%LOCALAPPDATA%/hermes/scripts/`:

```bat
"%TESS_PY%" "%SPAWNER%" --log "%TESS_LOG%" --err "%TESS_LOG%.err" --cwd "%TESS_PROJECT%" -- "%TESS_PY%" "%TESS_PROJECT%\start.py"
```

It spawns with `close_fds=True`, `stdin=DEVNULL`, stdout/stderr to files, and
`DETACHED | CREATE_NEW_GROUP | CREATE_NO_WINDOW`. It also strips
`PYTHONPATH`/`PYTHONHOME`/`PYTHONSTARTUP`/`VIRTUAL_ENV` from the child so a
service cannot inherit the agent runtime's import path.

## Rule 2: probe without paying for an interpreter start

`Invoke-WebRequest` costs 1–3 s of PowerShell process startup on a loaded
host, and that time is charged to the launcher's wait budget — a busy
machine can time out waiting for a server that is already up.

`curl` in a pipeline is no better: on Windows it can fail with
*"Input redirection is not supported"*.

Use `probe_http.py` (stdlib urllib, in the service's own interpreter):

```bat
"%TESS_PY%" "%PROBE%" "%TESS_HEALTH%" 3
if not errorlevel 1 ( echo up & exit /b 0 )
```

## Rule 3: use the absolute Windows `timeout.exe`

`timeout /t 2` inside a `.cmd` resolves to **GNU coreutils `timeout`** when
the PATH was touched by MSYS/Git-Bash, because `cmd.exe` inherits that PATH.
GNU timeout rejects `/t`:

```
timeout: invalid time interval '/t'
```

The wait then returns instantly, so a "60 second" budget is exhausted in
under a second and the launcher fails while the server is still starting.

Always use the absolute path:

```bat
"%SystemRoot%\System32\timeout.exe" /t 2 /nobreak >nul
```

## Rule 4: fail fast, and prove the launcher is what started it

- An undefined variable becomes an **empty argument**: `python ""` falls back
  to the current directory and dies with *"can't find '__main__' module"*.
  Guard every helper path with `if not exist` and exit 1.
- A **surviving supervisor masks a broken launcher**. NEXUS's supervisor
  respawns the service within a second, so a test that stops only the port
  owner makes the launcher look successful although it never ran. Stop the
  whole tree, confirm the port was free, then let the launcher be the only
  path back up.

## Canonical launchers

| Service | Launcher | Port |
|---|---|---|
| TESSERACT | `%LOCALAPPDATA%/hermes/scripts/start_tesseract.cmd` | 8705 |
| NEXUS | `%LOCALAPPDATA%/hermes/scripts/start_nexus.cmd` | 8650 |
| n8n | `%LOCALAPPDATA%/hermes/scripts/start_n8n.cmd` | 5678 |
| HERETIK | `%LOCALAPPDATA%/hermes/heretik/start_demand_proxy.cmd` | 8080 |
| KRYSYS | `C:/Users/KING/Projects/krysys-shop/start_krysys.cmd` | 8500 |

The Startup shortcut, the `SERVICES.json` registry, `evo services --heal` and
the operator's own flow all point at the same file. One path, one behaviour.

## Verification recipe

```bash
# launcher returns promptly, releases the pipe, and the service is up
python - <<'PY'
import subprocess, threading
p = subprocess.Popen(["cmd","/c", r"C:\...\start_tesseract.cmd"],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
eof = {"v": False}
def r():
    p.stdout.read(); eof["v"] = True
t = threading.Thread(target=r, daemon=True); t.start()
while p.poll() is None: t.join(0.5)
t.join(8)
print("launcher_exit", p.returncode, "pipe_eof", eof["v"])
PY
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8705/health
```

Expect: launcher exit 0, `pipe_eof True`, health 200.
