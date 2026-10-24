# MSYS2 Bash → Windows Command Routing Traps

Session date: 2026-08-23

## The Three Command-Execution Paths Under MSYS2 Bash

When `terminal` runs commands on a Windows host inside MSYS2 bash, there are
three distinct routing paths, and they fail differently:

| Approach | What happens | Verdict |
|----------|--------------|---------|
| `cmd.exe //c "command"` | Opens an **interactive cmd prompt**. The command string is swallowed, and you get the `C:\Users\KING>` banner but the command never executes. The spawned `cmd` sits waiting for input. | **DO NOT USE** |
| `cmd.exe /c "command"` | MSYS2 **path-translates** `/c` to a Windows path (e.g. `C:\c`), so cmd.exe sees `C:\c` as its argument. Cmd either errors (`The syntax of the command is incorrect`) or silently does nothing. | **DO NOT USE** |
| `powershell.exe -NoProfile -Command "..."` | Works reliably. No path translation interference. Use `-NoProfile` to skip profile loading (faster, no side effects). | **PREFERRED** |

## Taskkill With Multiple `/PID` Switches

A one-liner `taskkill //PID 3140 //PID 2036 //F` returns
`ERROR: Invalid argument/option - '//PID'.` because MSYS2 path-translates the
second `//PID` token on the same command line.

**Fix:** one process per invocation, chained with `;`:

```
taskkill /PID 3140 /F; taskkill /PID 2036 /F
```

(Note: single `/PID`, not `//PID` — MSYS translates `//PID` to a Windows path.)

## Tasklist / NetStat / Service Commands

Windows diagnostic commands like `tasklist`, `sc`, `netstat`, and `wmic` also
suffer from the same routing trap. Never prefix them with `cmd.exe //c` or
`cmd.exe /c`. Instead, wrap in PowerShell:

```
# BAD:
cmd.exe //c "tasklist //FI \"IMAGENAME eq python*\""

# GOOD:
powershell.exe -NoProfile -Command "Get-Process -Name python*"

# GOOD for services:
powershell.exe -NoProfile -Command "Get-Service OpenClaw -ErrorAction SilentlyContinue"

# GOOD for ports:
powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort 18789"
```

## File Paths Across MSYS2 → Native Calls

When launching a native Windows `.exe` or `.py` from MSYS2 bash:

```
# BAD — MSYS2 mangles the leading /q/ into C:\q\ which doesn't exist:
C:/Users/KING/.cache/nexus-venv/Scripts/python.exe /q/ultron-memory/nexus-core/server.py
# Error: can't open file 'C:\\q\\ultron-memory\\...' — no such file

# GOOD — use Q:/ prefix (MSYS2 passes Q: through to native unchanged):
C:/Users/KING/.cache/nexus-venv/Scripts/python.exe Q:/ultron-memory/nexus-core/server.py
```

Rule: **for native Windows processes launched from MSYS2 bash, use `Q:/` (drive-letter
colon-slash) not `/q/` (MSYS mount-style).** MSYS2 resolves `/q/` to `C:\q\` when
handing arguments to native Windows processes; `Q:/` passes through intact.

## Subst Under MSYS2 — quoting eats the backslash

`subst Q: E:\` from bash fails with `Invalid parameter - E:` because bash
swallows the trailing backslash before cmd.exe sees it. Escape it so the
command that lands on the Windows side is `subst Q: E:\`:

```
subst Q: "E:\\"     # bash passes E:\ to cmd.exe — works
subst Q: E:\\       # bash strips \ → passes E: — Invalid parameter - E:
subst Q: E:        # same failure — backslash required on Windows side
```

`subst` is per-user and non-persistent. To survive logon, register a
Scheduled Task `-AtLogOn -User $env:USERNAME` that runs a .cmd wrapper
(`subst Q: E:\ 2>nul`). `mountvol Q: \?\Volume{<guid>}\` for a second native
letter on the SAME volume returns `The parameter is incorrect.` (Windows
won't dual-letter a volume natively), and `Add-PartitionAccessPath` needs
elevation the Hermes terminal lacks. Subst is the reliable path.

## Node.js Under MSYS2

Node paths also mangle. `'/c/Users/KING/AppData/Local/hermes/node/node.exe'` with
single-quoted `'/c/...'` paths can resolve to `C:\c\...`. For Node invocations:

```
# BAD — single-quoted /c/ path gets C:\c\ prefix:
'/c/Users/KING/AppData/Local/hermes/node/node.exe' '/c/Users/KING/.../openclaw/dist/index.js'
# Error: Cannot find module 'C:\\c\\Users\\...'

# GOOD — launch via cmd.exe /c with full Windows path, or use a .cmd wrapper:
cmd.exe /c "C:\\Users\\KING\\.openclaw\\gateway.cmd"
```

But note: `cmd.exe /c` only works when the argument is a **single Windows path**
(no MSYS-style slashes inside it). The `.cmd` file itself gets passed through
without path translation because it starts with `C:\`.
