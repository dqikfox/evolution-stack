# MSYS2 Bash → Windows Binary Bridging

Hermes sessions on Windows run inside MSYS2 bash. Several common command patterns fail silently or break in unexpected ways.

## Path Mangling

MSYS2 rewrites POSIX paths when they appear as arguments to non-MSYS2 binaries:
- `/q/ultron-memory/server.py` → `C:\q\ultron-memory\server.py` (WRONG)
- `//q/ultron-memory/server.py` → preserved as `/q/...` but still risky

**Always use explicit drive-letter paths with non-MSYS2 binaries:**
```bash
# WRONG — path gets mangled
python /q/ultron-memory/nexus-core/server.py

# RIGHT — drive-letter form passes through unmangled
python Q:/ultron-memory/nexus-core/server.py

# ALSO RIGHT — C:/ form
python C:/Users/KING/project/server.py
```

## cmd.exe //c Trap

`cmd.exe //c "command"` does NOT work in MSYS2 bash for most complex commands. It often spawns an interactive cmd session instead of running the command.

**Use `powershell.exe -NoProfile -Command` instead:**
```bash
# WRONG — spawns interactive cmd, hangs
cmd.exe //c "tasklist //FI \"IMAGENAME eq python*\""

# RIGHT — clean PowerShell execution
powershell.exe -NoProfile -Command "Get-Process python* | Format-Table Id,ProcessName"
```

## curl in MSYS2

MSYS2 curl can behave differently from native Windows curl (WinSSL vs OpenSSL). Use `-4` to force IPv4 and avoid DNS issues:
```bash
curl -4 -s --max-time 5 http://127.0.0.1:8650/health
```

## Node.js Paths

When launching Node.js apps from MSYS2, use C: drive-letter form for both the node binary and the script:
```bash
/c/Users/KING/AppData/Local/hermes/node/node.exe /c/Users/KING/path/to/script.js
# NOT: //c/Users/... — double-slash form works for filesystem access but breaks for exec
```

## Process Management

- `tasklist` and `taskkill` need cmd syntax; prefer PowerShell `Get-Process` / `Stop-Process`
- Windows Services: `powershell.exe -NoProfile -Command "Get-Service sshd | Restart-Service -Force"`
- Ollama is NOT a Windows Service on THRONE — it's a system-tray executable. Use `ollama stop` + `ollama serve &` or restart via tray.

## PowerShell via `terminal -Command` — quoting pitfalls

Embedding PowerShell inside `terminal -Command "..."` strings breaks in three predictable ways:

1. **`===` is consumed by bash.** Bash treats `=` as assignment and `==` as test. A PS command like `Write-Host '=== title ==='` becomes mangled. Use ASCII separators or quotes the section differently (`--- title ---` works).
2. **Format-string `→` (U+2192) and similar Unicode in PS `-f` operator** drop or split the line. `[Tool loop warning: same_tool_failure_warning; count=N]` errors are the visible symptom — bash ate half the command before PS saw it.
3. **`if (...) -and ...` and `$var.match(...)` inside `terminal -Command`** lose their `-` characters. PowerShell sees `if (...) and ...` and throws `Unexpected token 'and'`.

**Reliable pattern: write the PowerShell to a `.ps1` file via `write_file`, then `terminal powershell -NoProfile -ExecutionPolicy Bypass -File <path>`.**

```bash
# Step 1: write the script
write_file path="C:/Users/KING/AppData/Local/Temp/my_script.ps1" content='...PS...'

# Step 2: invoke it
terminal powershell -NoProfile -ExecutionPolicy Bypass -File "C:/Users/KING/AppData/Local/Temp/my_script.ps1"
```

This keeps bash out of the PowerShell quoting entirely. The pattern is reused throughout host optimisation tasks (HKCU registry edits, `Get-Process | Stop-Process`, GPU power-mode probes) and is the same pattern referenced in the throne-windows-adaptation skill under "Shell elevation model."
