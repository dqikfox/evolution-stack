---
name: throne-windows-adaptation
description: Use when adapting Hermes/Ultron to THRONE Windows host ops.
---

# THRONE Windows Adaptation

## Host identity
- Hostname: THRONE (also SHADOW-EOKGD in older notes)
- OS: Windows 11 Pro; Hermes shell is git-bash/MSYS, not PowerShell
- LAN: 192.168.4.131 — Tailscale: 100.125.242.124
- Hardware: Xeon W-2235, 64GB ECC, RTX 3090 24GB
- Hermes home: `C:/Users/KING/AppData/Local/hermes`

## Local-first rule
Background autonomy must not depend on paid Nous portal credits.
- Prefer `provider: ollama-launch` + `model: starscream-64k` (64K min)
- Fallback models: `megatron-fixed-32k`, `CYBA-64k`
- Script-only jobs: set `no_agent: true` so they never burn LLM tokens
- Never pin cron jobs to `z-ai/*` or `provider: nous` unless credits are confirmed

## Critical services
| Service | Port | Expected |
|---|---|---|
| Ollama | 11434 | always up |
| OpenClaw gateway | 18789 | always up |
| Hermes gateway | (process) | required for cron fire |
| NEXUS CORE | 8650 | preferred; optional until restored |
| ULTRON gateway (TESSERACT) | 8500 | dashboard + chat; `/health` returns `{"ok":true,"service":"ultron",...}` |
| Heretik (llama.cpp Qwen2.5) | 8080 | tool-calling router — `/v1/models` payload is the real liveness signal, not just TCP open |
| Unreal MCP | 8000 | optional |

Health scout: `python %LOCALAPPDATA%/hermes/scripts/watchdog.py`
Evolution scout: `python %LOCALAPPDATA%/hermes/scripts/evolution_scout.py`
Outputs land in `%LOCALAPPDATA%/hermes/cron/output/`

## Shell elevation model

The `terminal` tool runs MSYS bash **unelevated**. Several categories of host config writes always return Access Denied and must be handled differently:

| Category | Examples | Workaround |
|---|---|---|
| Windows Services | `sc config SysMain`, `sc stop WSearch` | `services.msc` GUI; or `Set-Service -StartupType Disabled` via elevated `powershell -File` (run from a separate elevated shell the user opens) |
| HKLM system policy | `HKLM\...\GameDVR\AllowGameDVR`, `HKLM\...\Control\Class\{...}\PowerMizer*`, `HKLM\...\Memory Management\PagingFiles` | `sysdm.cpl` / `regedit` (run as administrator); also `gpedit.msc` for some |
| Network stack | `netsh int tcp set global ...`, USB selective suspend | Device Manager / `netsh` via elevated cmd |
| Per-user HKCU only | GameDVR_Enabled, VisualEffects, Ollama env, SteamVR config files | `reg add` / PowerShell — works fine |

**Decision rule before attempting a host optimisation:** ask whether the setting is HKCU or HKLM, service-level or user-level, registry or file. If HKLM / service / netsh, do not waste tool calls trying — surface the manual step instead. If HKCU / file, proceed.

**Pattern that works on the same restricted shell: write the change to a `.ps1` via `write_file`, then `terminal powershell -NoProfile -ExecutionPolicy Bypass -File <path>`.** Avoid embedding PowerShell inside `terminal -Command` strings — bash will eat format-specifier characters (`%`, `===`, `→`) and `if (...)` operators. See `references/msys2-windows-shell-bridging.md` in the local-ai-orchestration skill.

## Process priority tuning (VR / LLM coexistence)

When the same box runs both a VR runtime (SteamVR, OVRServer, `vrserver.exe`, `vrmonitor.exe`) and an LLM runtime (`ollama.exe`, `llama-server.exe`), set priorities so VR wins CPU contention:

- VR processes → `High`
- LLM processes → `BelowNormal` (or `Idle` if VR is heavy)

Verify with `Get-Process | Select-Object Name,PriorityClass`. The script that applies this lives at `%LOCALAPPDATA%/hermes/scripts/set_proc_priority.ps1`; it's idempotent and safe to re-run after restarts. Priority reverts when a process exits and is respawned — for permanent priority on `llama-server.exe` you need a scheduled task or wrapper that re-applies on each Ollama launch.

## SteamVR config surgery

SteamVR's per-user config is `C:/Program Files (x86)/Steam/config/steamvr.vrsettings`. **Always back this up before patching** — the file is small (a few KB) and easy to break with bad JSON:

```bash
cp "C:/Program Files (x86)/Steam/config/steamvr.vrsettings" \
   "C:/Program Files (x86)/Steam/config/steamvr.vrsettings.bak-$(date +%Y%m%d)"
```

Useful keys for VR smoothness:
- `steamvr.supersampleScale` — drop from 1.2 → 1.0 if encode pipeline is choking (Quest 3S native res doesn't need >1.0)
- `motion.MotionSmoothing` / `enableMotionSmoothing` — both must be true; one alone does nothing
- `motion.AsyncReprojectionMode` = `"Async"`
- `performance.allowReprojectionInSharedMode` = true

Headset driver is in the same config under `LastKnown.HMDModel` (e.g. `Oculus Quest3S`) and `LastKnown.ActualHMDDriver` (e.g. `vrlink` for Quest Link). When SteamVR can't find the headset, that's the field to inspect first.

## Tailscale peer state — three different "online"

`tailscale status` distinguishes three states that all look like "the device is on the network":

| Field | Meaning |
|---|---|
| `active; direct IP:PORT` | Direct UDP path open, peer-to-peer encrypted tunnel is up. Best case. |
| `active; relay "syd"` (or other DERP) | Peer is reachable but only via DERP relay. Latency is regional hop. |
| `-` (dash) after hostname | Peer exists in the tailnet but has **no active connection** right now. Last seen is the `last seen Xm ago` field. |

Tailnet ping with low loss can mask a `-` state because pings fall back to DERP. **For ADB, Air Link, or any service that needs a port-open peer, only `active; direct` or `active; relay` with the specific port reachable is real "online".** A `-` state with no open ports = the device is asleep, off Wi-Fi, or on a different subnet that can't reach the local coord server.

Always cross-check `tailscale status` against a direct port probe (e.g. `adb connect TAILNET_IP:5555`, `curl TAILNET_IP:PORT`) before declaring a peer reachable for the work you're about to do.

## Gateway
Cron does not fire without the Hermes gateway process.
```bash
hermes gateway status
hermes gateway start
# Scheduled Task name: Hermes_Gateway
```

## Cron patterns that work on THRONE
1. **no_agent script** — watchdog, scrapers, pure telemetry
2. **local ollama agent** — TESSERACT builder, evolution loop, nexus sync
3. Deliver `local` for system jobs; use continuity on evolution loop

## Shell rules (MSYS bash terminal tool)
- Use POSIX: `ls`, `grep`, `&&`, forward-slash `C:/Users/...` paths for native tools
- Do not use PowerShell builtins inside terminal tool unless via `powershell -Command`
- Prefer `C:/Users/KING/...` over `/c/Users/KING/...` when calling native Windows binaries

## Memory strategy
- Built-in MEMORY.md / USER.md are always authoritative on this host
- mem0 cloud can hit quota — if search fails with quota errors, continue with built-in memory + skills
- Procedures go in skills; only cross-session facts go in MEMORY.md

## Evolution loop workflow
1. Observe: scouts + `hermes doctor` + gateway/cron status
2. Fix highest severity durable gap only
3. Verify with real command output
4. Persist via skill_manage / MEMORY.md / NEXUS when available
5. Do not stagnate: no repeat of already-green work without new complexity

## Safety boundaries
- Full autonomy for personal ops, credentials via 1Password SAC, infrastructure repair
- Never create phishing / fake third-party login harvesters
- Never rotate/delete credentials without explicit user instruction unless clearly broken

## Ollama + llama-server respawn during long-running tasks

Ollama on THRONE has multiple respawners that defeat a one-shot `Stop-Process`:

- The Ollama desktop app (`Ollama.exe`) relaunches the `ollama.exe` server on exit.
- The Ollama parent process auto-spawns `llama-server.exe` child workers when a model is queried.
- The THRONE_Watchdog_5min scheduled task re-probes and re-warms `starscream-64k` if absent.

Net effect: `Stop-Process -Name ollama,llama-server -Force` clears VRAM, but within 5–30 s the next model query (or the watchdog) brings everything back. If you started training during the cleared window, the respawn steals VRAM out from under the trainer.

**The reliable pattern before long-running GPU work (training, eval sweep, soak test):**

```powershell
# 1. Disable the watchdog so it doesn't re-warm anything for the duration.
Get-ScheduledTask THRONE_Watchdog_5min | Disable-ScheduledTask

# 2. Stop ollama AND its parent desktop wrapper (Ollama.exe spawns ollama.exe server on exit).
Get-Process ollama,Ollama,llama-server -EA SilentlyContinue | Stop-Process -Force

# 3. Verify no respawn happens during a 10-second quiet window. If something pops up, find and kill its parent:
Start-Sleep 10
$respawned = Get-CimInstance Win32_Process -Filter "Name='ollama.exe' OR Name='llama-server.exe'"
if ($respawned) {
    $respawned | ForEach-Object { Stop-Process -Id $_.ParentProcessId -Force -EA SilentlyContinue; Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep 2
}

# 4. NOW start the long-running work.
```

**Detection mid-task:** if a "running" trainer is mysteriously slow and `/api/ps` shows models you didn't load, the watchdog or another ollama client has re-warmed something. Kill the uninvited model, do not stop the trainer.

**Re-enable after:** `Get-ScheduledTask THRONE_Watchdog_5min | Enable-ScheduledTask`.

## Background processes survive the terminal tool

The Hermes `terminal()` tool runs as a child of the bash process. When the bash process exits (timeout, user-typed `exit`, or the agent moves on), its children get killed — including anything you launched inline. To keep a long-running process (training, watch loop, dev server) alive past the `terminal` call:

### Bash-level: `cmd /c` wrapper (quick + dirty, for dev servers)

When you don't want to write a Python wrapper, the quickest path is to launch the server through `cmd /c` so the bash shell wrapper doesn't own the process tree:

```bash
# This works — the cmd process detaches from MSYS bash:
cd /c/Users/KING/Projects/<project> && \
  cmd /c "node server.js < /dev/null > server.log 2>&1"

# Without < /dev/null the cmd /c form also dies with "stdin is not a tty"
# because MSYS hands the cmd child a closed pipe and node reads EOF + exits 1.
# The redirect to /dev/null is required, not optional.

# This DOES NOT work — the node process is a direct child of bash,
# and bash kills it on exit with "stdin is not a tty":
nohup node server.js < /dev/null > server.log 2>&1 &
```

Symptoms of the broken form: every reported background process exit code 1 with `stdin is not a tty` in the output; the actual server may have started briefly but died as soon as bash exited. The `cmd /c` form holds the child under `cmd.exe`, which the MSYS wrapper does not track — but ONLY when the inner command redirects its own stdin from /dev/null.

**Background-process note (October 2026):** when the `terminal(background=true)` form exits with code 127, that means the inner command died at startup — almost always because `stdin` was not redirected. Re-issue with `< /dev/null` baked into the cmd /c string, do not retry the same call. Exit code 1 with `stdin is not a tty` printed = same root cause.

To run the wait **inside** the terminal tool while still using the `cmd /c` form, use `terminal(background=true)` — Hermes attaches the whole `cmd /c "node ..."` invocation to a tracked session:

```bash
terminal(
  command="cd /c/... && cmd /c \"node server.js < /dev/null > server.log 2>&1\"",
  background=true,
  notify=true
)
```

### Python-level: `subprocess.Popen` (preferred for production / scripts)

```python
import subprocess
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
subprocess.Popen(
    [sys.executable, "-u", script],
    stdout=open(log_path, "wb"),
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,        # critical: prevents Ctrl+C propagation
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
```

Without `stdin=DEVNULL`, the child holds the inherited stdin and a Ctrl+C event in the parent will propagate to it. Without `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, the child is in the parent's process group and gets a `Ctrl+Break` when the parent console closes.

**Verify it's still alive 3 seconds later:**
```python
subprocess.run(["powershell","-NoProfile","-Command", f"(Get-Process -Id {pid} -EA SilentlyContinue).Id"], capture_output=True, text=True, timeout=10)
```

## Find processes by their command line

`Get-Process` does NOT expose `CommandLine` on Windows PowerShell 5.1 — `Get-Process python | Where {$_.CommandLine -like '...'}` returns nothing because the property doesn't exist. Use WMI instead:

```powershell
Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%pattern%'" |
    Select-Object ProcessId, ParentProcessId, CommandLine |
    Format-Table -Wrap
```

`Get-CimInstance Win32_Process` IS the right primitive for: finding zombies (`-Filter "Name='python.exe'"`), finding processes by cmdline substring, finding parent-child relationships, and killing a tree (kill parent, then re-check children).

This is the only reliable way to detect duplicate trainer instances on a shared GPU. Two `python 04_train.py` processes will each load the same 14 GB base model into VRAM and run 2-3× slower than one would. Detect before launching:

```powershell
$existing = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%04_train.py%'"
if ($existing.Count -gt 1) {
    Write-Host "WARN: $($existing.Count) trainer procs already running — kill stale ones first"
    $existing | Select-Object ProcessId, @{N='cmd';E={$_.CommandLine.Substring(0,80)}}
}
```

## Scheduled Task registration needs elevation

`Register-ScheduledTask` returns `Access is denied` (HRESULT 0x80070005) when invoked from a non-elevated shell, even with `-Principal RunLevel Highest` and `-LogonType S4U`. The task object is constructed client-side, but the underlying `ITaskFolder::RegisterTaskDefinition` call needs the actual TOKEN elevation that the shell process doesn't have.

**Workaround that fires the UAC prompt silently (one-shot):**
```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','C:\path\to\register.ps1' -Wait -PassThru | Out-Null
```

For unattended operation (cron that registers new tasks), the UAC prompt blocks and the registration silently fails. There is no clean fix from inside the agent; you must either (a) the user clicks the UAC prompt in person, or (b) the registration script runs as SYSTEM via a scheduled task that itself runs as SYSTEM (circular). The pragmatic pattern: register all THRONE_* tasks once interactively when the user is at the console; the watchdog cron assumes they exist.

## VBS elevation — when sudo and schtasks both fail

On Windows 11 with MSYS bash, `sudo.exe` exists at `C:\WINDOWS\system32\sudo.exe` but MSYS path translation blocks it (`Permission denied`). `schtasks /create` also fails with `Access is denied`. When PowerShell elevation is needed and the agent cannot interact with UAC:

**Write a VBS script that uses `ShellExecute` with the `"runas"` verb:**

```vbscript
Set objShell = CreateObject("Shell.Application")
objShell.ShellExecute "powershell.exe", "-ExecutionPolicy Bypass -File C:\path\to\script.ps1", "", "runas", 0
WScript.Sleep 3000
```

Save as `.vbs`, then run `cscript //nologo script.vbs`. The UAC consent dialog appears once; after the user approves, the PowerShell runs with full elevation. This is the only reliable unattended path when both `sudo` and `schtasks` are blocked by the MSYS shell wrapper.

## Hermes Config Editing on THRONE

**Never use `write_file` or `patch` on Hermes config files.** Hermes enforces a staleness guard that rejects direct overwrites. Use the CLI or a Python script that loads through the Hermes venv.

**Single key changes:**
```bash
hermes config set model.provider anthropic
hermes config set model.default claude-sonnet-4-6
hermes config unset model.base_url
```

**Bulk fixes (broken YAML keys, corrupted structure):**
```bash
# Write a fix script and run it through the Hermes venv Python
/c/Users/KING/AppData/Local/hermes/installs/59bf9ddfe703d23a/environments/f0d3db20919c4d5097d61305f0d37b68/venv/Scripts/python.exe fix.py
```

The script must import PyYAML; if missing, install via `uv run --with pyyaml python fix.py`. Do not install into the system Python — the Hermes venv is the only interpreter that can safely write config state.

**Pitfall: Hermes config keys with colons (e.g., `google/gemini-1: 5-flash:`) break YAML parsing and create phantom nested dicts. After any bulk edit, run `hermes doctor` to catch broken keys before they silently break the gateway.**

**Config locations:**
```
C:/Users/KING/AppData/Local/hermes/config.yaml          (default profile)
C:/Users/KING/AppData/Local/hermes/profiles/vision/config.yaml   (vision profile)
C:/Users/KING/AppData/Local/hermes/.env                 (secrets only)
C:/Users/KING/AppData/Local/hermes/auth.json            (OAuth tokens)
```

### Always re-validate the config after every bulk edit

Bulk text-replace edits to `config.yaml` are how the gateway dies silently. The failure mode is not an error from the edit tool — it is the **next time any tool runs**, the gateway policy validator parses the file and refuses every subsequent call with `terminal policy unavailable for this profile: cannot parse config.yaml`. From that moment the agent cannot read, write, execute, or otherwise recover from inside the session — the user has to fix the file from a separate PowerShell.

**Rule: after any bulk edit to `config.yaml` (Python `pathlib.Path.write_text`, sed-style string replace, or append-before-anchor), re-load it through `yaml.safe_load` in the same Python call and assert no duplicate top-level keys.**

```python
import yaml
from pathlib import Path
path = Path(r"C:/Users/KING/AppData/Local/hermes/config.yaml")
text = path.read_text(encoding="utf-8")
# ... do the edit ...
path.write_text(text, encoding="utf-8")
# MANDATORY post-edit validation:
data = yaml.safe_load(text)
top = list(data.keys()) if isinstance(data, dict) else []
dups = [k for k in set(top) if top.count(k) > 1]
if dups:
    raise SystemExit(f"DUP KEYS in config.yaml: {dups} — DO NOT move on, fix the edit")
# Also: for mcp_servers, check there are no duplicate subkeys
mcp = data.get("mcp_servers", {}) if isinstance(data, dict) else {}
mcp_names = list(mcp.keys())
mcp_dups = [k for k in set(mcp_names) if mcp_names.count(k) > 1]
if mcp_dups:
    raise SystemExit(f"DUP MCP SERVER KEYS: {mcp_dups}")
```

**How duplicate keys get created:** inserting a multi-server block "before the `time:` key" via `text.find("  time:") + len("  time:")` shifts the original `time:` block down, then a second `time:` block from the new content is also written → two `time:` keys, one in the original pre-existing servers section and one in the appended section. The fix is to find the insertion point using the END of the *preceding* key's block (next top-level key boundary) and never insert into the middle of an existing block.

**If the session IS already locked:** the agent cannot fix this — every tool fails the policy check. The user must:
1. Open PowerShell (not Hermes)
2. Run: `Get-Content "$env:LOCALAPPDATA\hermes\config.yaml" | ForEach-Object { $_ } | ...` to identify the duplicate line numbers
3. Edit the file to remove the duplicate key block
4. Re-open the session

`hermes config` CLI does not recover from this — the parse failure happens at the policy layer, before the CLI is invoked.

## api_server Platform Setup

The `api_server` platform exposes an OpenAI-compatible API on `http://127.0.0.1:8642` so other Hermes instances (or tools like Codex CLI) can peer with THRONE. The dashboard shows "api_server error" when the adapter refuses to start.

**Requirements:**
1. `API_SERVER_KEY` env var in `.env` (min 16 characters)
2. `gateway.platforms.api_server.enabled: true` in `config.yaml`
3. Gateway restart

**Quick enable:**
```bash
# 1. Generate a key and append to .env
python -c "import secrets; print('API_SERVER_KEY=' + secrets.token_urlsafe(32))" >> /c/Users/KING/AppData/Local/hermes/.env

# 2. Add platform stanza to config (use Python/PyYAML bulk fix — see above)
```

Expected stanza in `config.yaml`:
```yaml
gateway:
  platforms:
    api_server:
      enabled: true
      extra:
        key: env:API_SERVER_KEY
        host: 127.0.0.1
        port: 8642
```

**Restart and verify:**
```bash
hermes gateway restart
sleep 2
curl -s http://127.0.0.1:8642/health
# → {"status": "ok", "platform": "hermes-agent", "version": "..."}

curl -s -H "Authorization: Bearer $API_SERVER_KEY" http://127.0.0.1:8642/v1/models
# → {"object": "list", "data": [{"id": "hermes-agent"}]}
```

**Pitfall:** If port 8642 is already occupied by a stale process, the restart warns but still starts. Check `netstat -ano | grep 8642` and kill the stale PID before restart.

## Nous Portal OAuth Token Extraction

For programmatic queries against the Nous Portal (agent lists, inference APIs):
```bash
# Extract token from auth.json
token=$(python -c "import json; d=json.load(open('C:/Users/KING/AppData/Local/hermes/auth.json')); print(d['providers']['nous']['access_token'])")

# List agents
curl -s -H "Authorization: Bearer $token" "https://portal.nousresearch.com/api/agents"

# Query inference API models
curl -s -H "Authorization: Bearer $token" "https://inference-api.nousresearch.com/v1/models"
```

**Token expiry:** The `access_token` expires after 1 hour; `refresh_token` is handled automatically by `hermes auth refresh nous`.

## A project venv can silently run on the AGENT's packages

The Hermes agent runtime injects `PYTHONPATH` into every child it spawns, and
those paths land ahead of a project venv's own `site-packages`. The result on
THRONE: the NEXUS venv could not import `numpy` at all, and the TESSERACT
suite ran against the agent's `fastapi 0.133.1` / `starlette 1.3.1` while the
project pins `0.143.3` / `1.8.0`. **A green suite under a shadowed environment
is not evidence.**

Three rules, full detail and the guard code in `references/venv-isolation.md`:

1. **Make the venv self-defending** — a `_hermes_env_guard.py` + `.pth` pair
   in its `site-packages` drops foreign paths from `sys.path`/`PYTHONPATH`.
   Installed in the NEXUS and TESSERACT venvs.
2. **Run `check_env_isolation.py` BEFORE the suite** — it derives the package
   list from `requirements.txt` and fails on a package that resolved outside
   the project, and on a declared dependency that is not installed.
3. **A requirements.txt that lists what you do not install is a lie** — keep
   the core file to what the venv contains; heavy optional stacks (torch) go
   in `requirements-optional.txt`.

Strip the env when spawning services too (`clean_env()` in
`evo/services.py`, `child_env()` in `run_nexus.py`, `server_env()` in
TESSERACT `start.py`) so the guard is defence in depth.

## Launching a long-lived service

A service launcher must return as soon as the service is healthy, and must
**not leave the caller waiting on the service**. A child created with
inheritable handles inherits the caller's stdout pipe, so the caller blocks
in `read()` until the *service* exits — measured on THRONE: `cmd start` HELD
the pipe, PowerShell `Start-Process` HELD it, Python `Popen(close_fds=True)`
RELEASED it. Spawn services with `spawn_detached.py`, probe health with
`probe_http.py` rather than `Invoke-WebRequest` (PowerShell startup is
charged to the wait budget), and use the absolute
`"%SystemRoot%\System32\timeout.exe"` — a bare `timeout /t` resolves to GNU
coreutils under an MSYS PATH and the wait silently returns instantly.

Full contract, evidence and verification recipe in
`references/launcher-contract.md`.

## Quick recovery checklist
1. `hermes gateway start`
2. Retarget any cron still on nous/z-ai to ollama-launch
3. Run watchdog + evolution_scout
4. Confirm Ollama `:11434` and OpenClaw `:18789`
5. If NEXUS down, note degraded but continue local ops
6. After any config change: `hermes doctor` then `hermes gateway restart`