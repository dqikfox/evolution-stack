---
name: throne-sysadmin-network
description: |
  THRONE SysAdmin + Network Operations skill. Provides battle-tested
  PowerShell/Windows commands for process audit, service management,
  firewall review, disk monitoring, event log analysis, and network
  reconnaissance via the MCP throne server and native Hermes tools.
---

# THRONE SysAdmin + Network Operations

Use this skill when asked to audit, monitor, troubleshoot, or administer
THRONE (SHADOW-EOKGD) and its LAN/Tailscale peers.

## MCP Tool Reference

The `throne` MCP server exposes these tools via config.yaml:

| Tool | Purpose | Example Args |
|------|---------|-------------|
| `throne_health` | Full system health check | `{}` |
| `throne_telemetry` | CPU/RAM/disk/GPU snapshot | `{}` |
| `throne_processes` | Process list with filter | `{"name_filter":"node"}` |
| `throne_services` | Windows services | `{"name_filter":"ssh"}` |
| `throne_firewall_rules` | Active firewall rules | `{"direction":"inbound"}` |
| `throne_disk_space` | Drive free space | `{}` |
| `throne_network_adapters` | NICs + IPs | `{}` |
| `throne_event_logs` | Windows Event Log | `{"log_name":"System","max_events":50}` |
| `throne_nmap_scan` | Port/network scan | `{"target":"192.168.4.0/24","args":"-sS -T4 -F"}` |
| `throne_ping_host` | Reachability test | `{"host":"msi.tail886dbb.ts.net","count":4}` |
| `throne_port_check` | Single port probe | `{"host":"192.168.4.1","port":22}` |
| `throne_tailnet_peers` | Tailscale mesh | `{}` |
| `throne_inventory` | Cached network map | `{"format":"markdown"}` |
| `throne_rescan_network` | Force discovery | `{}` |\n| **Starlink gRPC** | Live dish telemetry | `uv run --with starlink-grpc-core python scout.py` |\n\n## Starlink gRPC Integration\n\nFor live telemetry from the Starlink Gen 3 router (`192.168.4.1:9000`):\n1. Use the `starlink-grpc-core` package.\n2. Initialize a `starlink_grpc.ChannelContext(target="192.168.4.1:9000")`.\n3. Call `starlink_grpc.get_status(context=context)` to retrieve dish state.\n4. **Pitfall:** The response object is NOT JSON serializable; access attributes directly or use `dir()` to inspect.\n\nSee `references/starlink-grpc.md` for implementation details.
| `throne_adb_devices` | Android via ADB | `{}` |
| `throne_adb_shell` | Remote shell on phone | `{"device":"","command":"whoami"}` |
| `throne_op_list` | 1Password index | `{}` |
| `throne_op_get` | Retrieve secret | `{"item_id":"abc","field":"password"}` |
| `throne_ollama_list` | Local models | `{}` |
| `throne_ollama_chat` | Chat via Ollama | `{"message":"status","model":"starscream-64k"}` |
| `throne_ollama_load` | Pre-load model into VRAM | `{"model":"starscream-64k","keep_alive":"30m"}` |
| `throne_ollama_unload` | Evict model from VRAM | `{"model":"starscream-64k"}` |
| `throne_heretik_models` | List Heretik models | `{}` |
| `throne_heretik_chat` | Fast tool inference | `{"message":"what ports are open?"}` |
| `throne_log_tail` | Read recent logs | `{"log":"watchdog","lines":100}` |
| `throne_runscript` | Execute allowlisted script | `{"name":"watchdog.py"}` |
| `throne_list_dir` | Directory listing | `{"path":"C:\\\\Users\\\\KING\\\\Projects"}` |
| `throne_read_file` | File read with pagination | `{"path":"...","offset":0,"limit":50}` |
| `throne_mounts` | SMB/local mounts | `{}` |
| `throne_nexus_query` | Search NEXUS knowledge base | `{"query":"THRONE setup","limit":5}` |
| `throne_nexus_health` | Check NEXUS health | `{}` |
| `throne_nexus_ask` | RAG question to NEXUS | `{"question":"what is THRONE?"}` |

## NEXUS CORE Integration

NEXUS is the local knowledge base at `E:\ultron-memory\nexus-core\`. It exposes:
- `GET /api/search?q={query}&limit=N` — hybrid FTS5 + ChromaDB search
- `GET /health` — DB notes count, Ollama models, Chroma vectors, Megatron memory
- `POST /api/ask` — RAG with source citations

**Status:** NEXUS CORE is live on port 8650. The indexed-note and vector counts change as notes are added — read `/health` for the live numbers instead of trusting a pinned figure. Megatron memory operational.

## Port Management Rules

THRONE uses a canonical port map at `E:\ultron-memory\infra\PORT_MAP.json`. Four mandatory rules:

1. **CHECK_PORT_MAP_FIRST** — Read PORT_MAP.json before starting any service. No two services may share the same port.
2. **REGISTER_BEFORE_START** — Every new service registers its name, port, and protocol in PORT_MAP.json before first launch.
3. **CONFLICT_RESOLUTION** — If a collision is detected, the lower-priority service moves. Priority: infrastructure > user-facing > experimental.
4. **ENDPOINTS_ENV_SYNC** — Any port change must be reflected in `C:\Users\KING\.ultron\endpoints.env` within the same action.

**Canonical ports:**
| Port | Service | Status |
|------|---------|--------|
| 8650 | NEXUS CORE | Active |
| 8666 | ULTRON 2.1 | Retired — do not health-check it |
| 8500 | KRYSYS shop | Active |
| 8705 | TESSERACT | Active |
| 8080 | llama-server (Heretik) | Expected |
| 11434 | Ollama | Active |
| 8510 | Furby emulator | Expected |
| 8511 | Lummings engine | Expected |

**Pitfall:** Before claiming a service is down, verify which process actually owns the expected port using `netstat -ano` and `tasklist`. Services may have moved or another process may have taken their canonical port.

## PowerShell One-Liners (fallback / raw terminal)

**Process audit:**
```powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 ProcessName,Id,CPU,WorkingSet | Format-Table -AutoSize
```

**Service audit:**
```powershell
Get-Service | Where-Object {$_.Status -eq 'Running'} | Select-Object Name,Status,StartType | Format-Table -AutoSize
```

**Firewall audit:**
```powershell
Get-NetFirewallRule | Where-Object {$_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound'} | Select-Object DisplayName,Action,Profile | Format-Table -AutoSize
```

**Disk audit:**
```powershell
Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}},@{n='TotalGB';e={[math]::Round(($_.Used+$_.Free)/1GB,1)}} | Format-Table -AutoSize
```

**Network adapters:**
```powershell
Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object Name,LinkSpeed | Format-Table -AutoSize; Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '169.254.*'} | Select-Object InterfaceAlias,IPAddress,PrefixLength | Format-Table -AutoSize
```

**Event log (last 50 System errors):**
```powershell
Get-WinEvent -LogName System -MaxEvents 50 | Where-Object {$_.LevelDisplayName -eq 'Error'} | Select-Object TimeCreated,Id,Message | Format-Table -AutoSize
```

**Port check:**
```powershell
$c = New-Object System.Net.Sockets.TcpClient; try { $c.Connect('TARGET', PORT); 'OPEN' } catch { 'CLOSED' } finally { $c.Close() }
```

### Windows Environment Variable Retrieval

When credentials or config values are stored in Windows user environment variables (set via Settings app or PowerShell `SetEnvironmentVariable`), they are **not visible** to a running MSYS/bash Python process through `os.environ`. The process environment is frozen at startup.

**Read via fresh PowerShell subprocess:**
```powershell
$val = [Environment]::GetEnvironmentVariable('IBM_API_KEY', 'User')
Write-Output $val
```

**Or from bash/git-bash:**
```bash
powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('IBM_API_KEY', 'User')"
```

**Pitfall — `env | grep IBM` shows nothing.** MSYS `env` and Python `os.environ` both read the process block. If the variable was set after the process started (e.g., via Windows Settings), neither sees it. Always spawn a fresh subprocess or restart the terminal.

**Pitfall — `GetEnvironmentVariable('User')` vs `GetEnvironmentVariable('Machine')`.** 'User' scope = current user only. 'Machine' scope = system-wide. Credentials stored in user scope are invisible to other accounts and services running as SYSTEM.

## Pagefile validity check

A common silent-OOM cause on Windows: `HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PagingFiles` is set to `?:\pagefile.sys` (the `?` placeholder from a half-finished system-managed setup that never resolved to a real drive). The system then refuses to materialize a pagefile, no fallback paging occurs, and `Get-CimInstance Win32_PageFileSetting` returns nothing.

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management').PagingFiles
# If you see '?:\pagefile.sys' or any value starting with '?', the pagefile is broken.
```

**Fix path (requires reboot):**

```powershell
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management' `
                 -Name 'PagingFiles' -Value 'C:\pagefile.sys 8192 24576'
# Reboot, then verify:
Get-CimInstance Win32_PageFileUsage | Format-Table Name,AllocBaseSize,CurrentUsage -AutoSize
```

Never apply this on a live system with <500 MB free RAM — the kernel will try to resize the pagefile live and can stall service hosts mid-call. Confirm the reboot first.

## Diagnose-then-act gate for system tune-up / "speed up my PC" requests

When the user asks to upgrade performance, free up RAM, or "speed up the box", do not start killing processes or changing pagefile settings immediately. Follow this order every time:

1. **Inventory first** — collect CPU, RAM, disk, pagefile, GPU, power plan, startup items, top-10 processes. Show the numbers; do not act.
2. **Compute free-RAM pressure tier**:
   - `>4 GB free` → normal, recommend safe optimizations only.
   - `500 MB–4 GB free` → elevated, recommend fixes but confirm before kill lists.
   - `<500 MB free` → critical; do NOT trigger live paging changes, do NOT bulk-kill processes. Report the diagnosis, present a ranked action menu, wait for user OK.
3. **Rank changes by impact / reversibility** — pagefile fixes, RAM-hog trims (with `MainWindowHandle` guard), startup-item trims, HAGS, hardware-accelerated GPU scheduling. Spend proposals (more RAM, NVMe, etc.) come last and only after the user agrees.
4. **Present menu as `1..N` / `A` / `ALL` letter options** — never assume. Never act on the most impactful fix without confirmation. Reversible free wins with `MainWindowHandle` guards can ship as a numbered action; irreversible changes need a `PROCEED` token.
5. **After execution** — verify before/after numbers, state what changed + how to revert + whether a reboot is required.

This gate exists because a near-OOM system is fragile: any live process kill or pagefile resize can hang WMI and leave the host in a worse state than the user started. The rule is "diagnose first, ask before acting on pressure-tier-critical systems, then ship free wins".

## RAM Pressure and "GIL stall" Reports

A multi-second Python stall reported as GIL pressure on a RAM-tight host is usually swap thrash — the interpreter's threads stall on page faults while the OS pages memory back in from disk. Check memory before touching any Python code:

```powershell
$os = Get-CimInstance Win32_OperatingSystem
[math]::Round($os.FreePhysicalMemory/1MB,1)  # free RAM GB
[math]::Round(($os.SizeStoredInPagingFiles-$os.FreeSpaceInPagingFiles)/1MB,1)  # GB held in page file
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 @{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB)}},ProcessName
```

Rule: single-digit free GB plus a large page-file residency = pressure confirmed. Find the largest private-RAM consumer that is not load-bearing and remove it or make it demand-driven. A resident llama-server idling for a small tool model is the classic flex target — demand-proxy it (see `devops/local-llm-endpoints`, `templates/demand_proxy.py`) instead of offloading to a slower node. Weight working set AND commit together: commit includes file-backed mmap pages, so a huge commit with a small working set is normal for mmap'd model weights.

## nmap Patterns

| Task | Command |
|------|---------|
| Quick host discovery | `nmap -sn 192.168.4.0/24` |
| Fast port scan | `nmap -sS -T4 -F --open 192.168.4.1` |
| Full port scan | `nmap -sS -p- --open -T4 TARGET` |
| Service detection | `nmap -sV -sC -p 22,80,443 TARGET` |
| Vuln scan | `nmap --script vuln -p 22 TARGET` |
| OS fingerprint | `nmap -O --osscan-guess TARGET` |

## Tailscale Operations

### NoState reset loop (ROOT CAUSE 2026-10-13 — read before any Tailscale fix)

**Two tailscaled.exe PIDs is NORMAL** (service + engine child). Not a rogue.

**The root cause chain:** with the GUI client (`tailscale-ipn.exe`) NOT running, every `tailscale up`/`tailscale login` CLI process EXIT is logged by the daemon as `client disconnected (THRONE\KING): disconnecting Tailscale` → backend stops → state resets to NoState. The Windows GUI tray client is the persistent session holder. A CLI-only login will NEVER hold: it connects, logs in (control plane says Success), then the CLI exits and the backend disconnects. Symptom: `up` returns silently or "Success", then `unexpected state: NoState` minutes later; login errors show `fetch control key: context canceled` (boot-race cancel, cached).

**Fix order (verified 2026-10-13):**
1. Start the GUI client FIRST: `powershell -NoProfile -Command "Start-Process 'C:\Program Files\Tailscale\tailscale-ipn.exe'"` — it holds the session.
2. Then `tailscale up` (silent connect if node registered, or auth URL → complete in browser).
3. Only after the GUI is running does state persist. Client 1.104.1 (upgraded from crash-looping 1.102.2 via `winget upgrade --id Tailscale.Tailscale -e --silent`).

**Never** rely on a CLI `up` without the GUI running, and never kill tailscaled PIDs as "rogues". After any Tailscale service restart, start `tailscale-ipn.exe` before anything else.

**Profile store corruption pattern:** a logout + re-login while profiles exist creates duplicate profiles (e.g. 29ca + 390b); daemon boots with `profile data directory: profile not found` → NoState→NeedsLogin loop that no restart fixes. Clean fix: stop service, archive `C:\ProgramData\Tailscale\{server-state.conf, profile-data}` (state archive kept at `Tailscale-state-archive-<date>`), start service, fresh login. A fresh machine key = new device row in admin console (old row goes stale — delete it there).

**Browser re-auth flow (drivable via computer_use, GitHub SSO for dqikfox.github tailnet):** auth URL → `Sign in with GitHub` → `Authorize tailscale` (session usually already approved) → connect page: **click the tailnet selector row FIRST** (Connect button is greyed out with tooltip 'Please select a tailnet' until selected) → then `Connect device to tailnet`. Poll `tailscale status` for the flip to Running. Auth URLs are single-use per daemon login session — mint a fresh one (`tailscale up --timeout 300s` in background) and complete it FAST; a superseded session's Connect click does nothing.

`tailscale up --reset` is only safe after `tailscale debug prefs` shows `AdvertiseRoutes: null` and `ExitNodeID: ""` — otherwise you drop advertised routes silently.

### Tailscale API v2 `online` field is unreliable (use `lastSeen` instead)
The `tailscale` MCP server and any direct hit to `GET /api/v2/tailnet/<tn>/devices` returns `online: null` for every device — the v2 API does not populate that field. Compute online from `lastSeen`: parse the ISO timestamp, treat < 5 minutes as online, else offline. The `tailscale status` CLI output uses `-` (no data) and `offline, last seen Nd ago` for the same reason; it computes fresh from lastSeen. If a report claims "0 online" but `tailscale status` shows several `active` peers, the script is reading the raw `online` field instead of computing from `lastSeen` — fix the script, not the API.

### Tailscale destructive operations are externally visible
`tailscale delete-device <id>` removes a node from the tailnet immediately and the admin console. There is no undo. Never call it from a script without an explicit user OK + the exact node id. To probe first, list devices with their ids and let the user confirm.

### Peer unreachability ≠ daemon fault
`tailscale status` `-` vs `offline` distinction: ping loss to a peer that shows recent `lastSeen` (tailnet_inventory.json) usually means the peer is asleep (MSI) — verify with the control-plane inventory before diagnosing the local daemon.

### "The phone" is the live one, not the closest one
When the user says "the phone", "my phone", or "the S23", don't assume
Cyclone-C4 (the rooted test rig) is the device in their hand just
because it's the only Android currently on the tailnet. Three checks
before treating any device as "the phone":
- **Tailscale `lastSeen` within minutes**, not days. Cyclone-C4 is
  always-on because it sits on the desk; S19 / S23 cycle based on the
  user's charging habits and are frequently offline.
- **SIM and telephony service.** `dumpsys telephony.registry | grep
  mSignalStrength` — `2147483647` (`Integer.MAX_VALUE`) everywhere
  means no SIM. The user's daily-driver phone will show real signal
  values; Cyclone-C4 won't.
- **Signed into the user's accounts.** Telegram, WhatsApp, Google Play
  — if the user mentioned any of these, the device they read those
  accounts on is the one they care about. `pm list packages | grep
  telegram` on a SIM-less test rig returns nothing — that's a feature
  of the test rig, not the user's phone.

If the user's daily-driver phone is offline, say so and propose an
alternative (e.g. install on the test rig if they want, or wait for
the daily driver to come online). Don't conflate "the only online
Android" with "the phone the user is holding".

### Launch .bat/.cmd services from git-bash
Never `cmd //c "C:\\path\\x.bat"` — MSYS mangles it into an interactive prompt that exits silently. Run the bat's contents directly: `cd "C:/project" && "./.venv/Scripts/python.exe" start.py` via `terminal(background=true)`.

```bash
# List all peers
tailscale status

# Check direct vs relay
tailscale status --json | python -c "import sys,json; d=json.load(sys.stdin); [print(p['HostName'], p['Online'], p.get('Direct')) for p in d.get('Peer',{}).values()]"

# Force funnel refresh
tailscale funnel --bg PORT
```

## ADB Operations

Phone-side work — install APKs, drive UI, verify what the screen shows.
The full procedure (ABI check, install flow, screencap-vs-uiautomator
fallback, sign-in-without-SIM, Magisk extras) is in
`references/adb-android-ops.md`.

**Critical updates not in older versions of the reference:**
- Jetpack Compose apps (Simplex, modern Telegram) break `uiautomator dump` — it returns empty XML. You must use screencap + visual verification or coordinate trial-and-error.
- FLAG_SECURE apps block `exec-out screencap`. Two escape paths: (1) edit shared_prefs to disable the flag if the app exposes a toggle, or (2) use `su -c 'screencap /sdcard/...'` which bypasses the pipe restriction.
- `/data` at 100% full causes silent 0-byte screencaps and failed file ops — check `df -h /data` before debugging any mysterious zero-byte output.

```bash
# List devices
adb devices -l

# Reach a phone on the tailnet
adb connect 100.71.239.65:5555

# Probe ABI before downloading an arm64-only APK onto a 32-bit device
adb -s SERIAL shell "getprop ro.product.cpu.abi"

# Shell to S23
adb -s SERIAL shell "whoami"

# Push/pull
adb push local.txt /sdcard/Download/
adb pull /sdcard/Download/remote.txt ./
```

**Always pass `-s SERIAL` explicitly** when more than one device is
connected — `adb` will pick the wrong one for a bare `shell` otherwise.

**Verify after every operation** with `pm list packages`, `pm path`,
`dumpsys package`, and `uiautomator dump` — don't trust a 0-byte
screencap as a failure signal (some Compose/Skia render surfaces block
`screencap` and the UI is actually fine; use `uiautomator dump` as the
universal fallback for "what is on the screen").

## Metasploit Quick-Launch

```bash
# Scan LAN
msfconsole.bat -q -x "use auxiliary/scanner/discovery/arp_sweep; set RHOSTS 192.168.4.0/24; run; exit"

# SMB version check
msfconsole.bat -q -x "use auxiliary/scanner/smb/smb_version; set RHOSTS 192.168.4.230; run; exit"
```

## Service and Peer Contracts

The house registers every service in `E:\ultron-memory\infra\SERVICES.json` and every
remote peer in `E:\ultron-memory\infra\REMOTE_AGENTS.json`. These rules are what make
those two files true rather than decorative.

**Local services**
- **The start path and its arguments are separate fields.** A registry entry whose
  path is stored as `"script.bat --http"` cannot be checked for existence —
  `Path("script.bat --http").exists()` is False — so the service reads as having no
  start path and the watchdog refuses to heal it. Store `path` and `args` separately.
- **A launcher for a long-running service must spawn it detached and return.** A
  launcher that runs the service in the foreground never exits, so the caller waits
  for the whole heal budget on a process that was working the entire time. Spawn
  through `hermes/scripts/spawn_detached.py`, then wait for the endpoint.
- **A health endpoint must not block on heavyweight work.** Serve first, do the
  expensive scan in a background thread. A LAN scan that runs before the bind keeps
  the port closed for the whole scan, so the service looks unstartable while it is
  working.
- **Bind a service to `127.0.0.1` unless it is meant to be reachable.** The empty
  string binds every interface and publishes the machine's inventory to the tailnet.
- **Define a handler class before the server that uses it.** A class is a local of
  its function: referencing it before the `class` statement raises
  `UnboundLocalError` on the first line of work, and the process stays alive with
  the port closed — it reads as "present but not serving" forever.

**Probing any service**
- **Speak the scheme the service actually speaks.** A TLS service answers a plain
  HTTP request with a 400 that says so, and reporting that as the service's health
  is a false failure — the service is up and the probe was wrong. Discover the
  scheme (one retry over TLS, certificate verification off on a private tailnet)
  rather than assuming it.
- **An open port with no answer is a third thing, not a failure.** A responding port
  is not proof of health, a 400 is not proof of failure, and "port open, no HTTP
  answer" is its own state — report it in those words.
- **A timeout with the port still open is degraded, not offline.** A service that is
  slow to answer is alive; paging the operator for it is the false failure.

**Remote peers**
- **Ask the peer about itself.** A peer's services are bound to its own loopback, so
  a probe from here sees a closed port for a perfectly healthy service. Probe over
  ssh, against the peer's own health endpoint.
- **Three states, not two: `up`, `down`, `unreachable`.** An unreachable peer cannot
  be healed by anyone. It is reported, it lands on the host score rather than the
  gate, and it is never "healed" — a heal that cannot possibly work is a slow way
  to fail. A gate that fails for a machine that is switched off is a gate that cries
  wolf.
- **Heal a peer through the peer's own start path** (its scheduled task), never a
  command invented here. The far side knows how to start its own service.
- **A peer that is stopped and knows how to be woken is not a failure** — it is a
  node that is not being paid for right now. The wake command runs here, because
  the provider's control plane is what starts it.
- **Keep peers out of the service census.** A peer that is off must never raise a
  service alert; peers belong in the network panel, and the estate publishes their
  state (with its own age) for the dashboard to read.

**Running a long-lived child from a tool call**
- **Redirect the child's output to files, not a pipe.** A detached service that
  inherits the caller's stdout pipe holds it open, so `subprocess.run(...,
  capture_output=True)` blocks forever on a call that already finished its work.
- **Bound every search.** An unbounded recursive walk over a large tree pins CPU and
  can wedge the tool kernel; search a named root and cap the result count.

### Launching a service that a customer can reach

- **A launcher's job order is dependencies, then body-aware probe, then
  leave/replace/refuse, then detached start.** Every launcher in this house
  checks its tools before it touches the port, so a launcher missing a probe
  cannot destroy a working service and only then report the missing file.
- **A TCP connect is not a health check.** A port that accepts a connection
  proves nothing: an SPA answers `/health` with its own shell, so a 200 there
  is a file being served, not a service being ready. Probe the BODY of the
  real route for a service marker, and point the registry at that route.
- **cmd strips the quotes from an argument like `"ok":true`,** so the token
  that reaches the program is not the token that was written. A probe marker
  must be a bare word (`--contains krysys`).
- **`cmd start /B` inherits every inheritable handle in the parent,** so a
  service started that way dies with the caller's job object - a tool call
  that starts a service leaves it dead seconds later. Spawn it with
  `close_fds`, explicit log files, and `stdin=DEVNULL`.
- **A service with no supervisor stays down until a human notices.** Run it
  under a supervisor that restarts a crash and replaces a wedge, and prove
  the recovery by killing the process and watching it come back.
- **A launcher's idempotence is a property you must test, not assert.** Run
  it twice: the second run must be a no-op, not a second copy.

### Exposing a working local service to the public

- **A Tailscale Funnel URL is a public HTTPS endpoint with no spend, no
  deploy hook and no token.** It is the fastest route from a working local
  service to a reachable one - use it before reaching for a hosting account.
- **A client that hardcodes its API host breaks on every deployment that is
  not that one.** The storefront must call `location.origin`, so it works
  wherever it is served.
- **Expose the service, then verify it from outside.** Fetch the real route
  over the public URL and create a real checkout, not a dry run.

See `references/peer-and-service-contracts.md` for the peer model's states,
transports, and the estate-side implementation.

## Rules of Engagement

1. **Always check inventory first** — `throne_inventory` before launching scans.
2. **Never brute-force without explicit order** — report finding, ask permission.
3. **Prefer MCP over raw terminal** — MCP tools have timeouts, sanitization, and audit trails.
4. **Escalate on unknown devices** — if a new MAC appears, investigate before ignoring.
5. **Check port occupancy before claiming a service is down** — verify with `netstat -ano` + `tasklist`. Services may have moved or another process may have taken their canonical port.
6. **Port changes require updating endpoints.env AND PORT_MAP.json** — downstream consumers read endpoints.env; PORT_MAP.json is the single source of truth for assignments.
7. **Log all changes** — write to MEMORY.md or decisions log.

## Verification Checklist

After any sysadmin action:
- [ ] Output captured and truncated if > 8KB
- [ ] No secrets echoed in response
- [ ] Relevant MEMORY.md entry written
- [ ] If state changed: what changed, how to revert, reboot required?
