---
name: powershell-scripting-pitfalls
description: Avoid PowerShell parsing pitfalls on Windows.
---

# PowerShell Scripting Pitfalls (Windows)

The PowerShell parser is line-oriented and unforgiving about nested quoting. These pitfalls cost real debugging time on this host (Windows 11, MSYS bash + PowerShell 5.1).

## When to Use

- Writing a `.ps1` script that gets a "Missing closing '}'" or "string is missing the terminator" parse error
- Driving PowerShell from the `terminal` tool via `powershell -File` or `powershell -Command`
- Mixing bash heredocs with PowerShell single-line commands (the bash layer eats `$` and `\`)

Don't use for: PowerShell modules, DSC, or anything beyond simple scripts.

## Pitfall 6 — `terminal` tool strips `=` from `-Command` strings

The Hermes `terminal` tool's command parser silently strips `=` characters from
PowerShell `-Command` arguments before they reach the shell. Multi-statement
PowerShell fails with `parser errors` (e.g. `An expression was expected after '('`)
because variable assignments like `$sc = New-Object ...` arrive truncated to
`New-Object ...`. The shell then sees `.CreateShortcut(...)` as a literal cmdlet
name and the entire pipeline breaks.

Symptoms (look for this exact shape in the error):

```
= : The term '=' is not recognized as the name of a cmdlet, function, script file, or operable program.
.TargetPath : The term '.TargetPath' is not recognized ...
```

**Fix:** any non-trivial PowerShell goes in a `.ps1` file on disk, run with
`-File`. The `terminal` parser does not strip the contents of a file argument.

```bash
# Write once, then invoke by file — the contents are safe from stripping
cat > "$LOCALAPPDATA/Temp/fix_shortcut.ps1" << 'EOF'
$sh = New-Object -ComObject WScript.Shell
$sc = $sh.CreateShortcut('C:\Users\KING\Desktop\Cradle.lnk')
$sc.TargetPath = 'cmd.exe'
$sc.Arguments = '/c cd C:\Users\KING\projects\Cradle && npm run dev'
$sc.Save()
EOF
powershell -ExecutionPolicy Bypass -File "$LOCALAPPDATA/Temp/fix_shortcut.ps1"
```

If the script body is built dynamically (e.g. with f-strings in Python), wrap
the whole `subprocess.run(['powershell', '-File', ...])` call in `execute_code`
so the `.ps1` contents never touch the `terminal` parser. This is the most
reliable path when the PowerShell is generated from a Python script.

**Rule:** treat any PowerShell command longer than one simple statement as
file-only. One-statement `Get-Process foo` is fine inline; anything with
variable assignment, multi-line logic, or `New-Object` belongs in a `.ps1`.

## Pitfall 1 — Single quotes inside double-quoted strings

`Write-Host "[$(Get-Date -Format 'HH:mm:ss')] hello"` parses as:
- `"[..$(.. 'HH:mm:ss')] hello"` — the first `'` after `Format` terminates the outer string

Error: `The string is missing the terminator: ".` (line + column point at the `"` immediately after the single quote).

**Fix:** wrap timestamp formatting in a helper function:

```powershell
function Log([string]$msg) {
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$ts] $msg"
}
```

**Verify a script parses before running:**
```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors) | Out-Null
$errors | ForEach-Object { "PARSE_ERR line=$($_.Extent.StartLineNumber): $($_.Message)" }
```

## Pitfall 2 — Bash heredoc mangles backslashes

Bash interprets `\U` in `\Users\KING\...` as a unicode escape and truncates the string. Then PowerShell sees an incomplete path or a malformed f-string.

**Fix:** never embed Windows paths with backslashes inside a Python `-c` heredoc that runs through bash. Use one of:

```bash
# Option A: write the script to a file first, run it
/c/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python "C:/Users/KING/AppData/Local/Temp/foo.py"

# Option B: use forward slashes (Python accepts both on Windows)
python "C:/Users/KING/..."

# Option C: use a raw string in Python — but only if the string is INSIDE Python source, not the bash layer
```

Same trap hits `\n`, `\t`, `\r` if the heredoc is unquoted.

## Pitfall 3 — `$` interpolation in `powershell -Command`

`powershell -Command "Write-Host $env:HOME"` looks fine but bash expands `$env:HOME` to empty (bash, not PowerShell). The `Log` line in `adb-keepalive.ps1` originally had this.

**Fix:** prefer `powershell -File <script.ps1>` over `-Command` when the script touches env vars, `$PID`, or any `$` variable.

## Pitfall 4 — `$_` in `Where-Object` inside bash strings

Bash MSYS eats `$_` before PowerShell sees it. Symptom:

```bash
# BROKEN — bash expands $_ to empty; PS sees '/c/Users/KING.OwningProcess'
powershell -Command "Get-NetTCPConnection | Where-Object {\$_.OwningProcess -eq 10244}"
# Error: "The term '/c/Users/KING.OwningProcess' is not recognized"
```

**Fixes (any one works):**

```bash
# Option A: write the script to a .ps1 file first, run with -File (cleanest)
cat > "$LOCALAPPDATA/Temp/probe.ps1" << 'EOF'
Get-Process llama-server | ForEach-Object {
  $port = (Get-NetTCPConnection -State Listen -OwningProcess $_.Id -EA SilentlyContinue | Select-Object -First 1).LocalPort
  Write-Output ("PID=" + $_.Id + " PORT=" + $port)
}
EOF
powershell -ExecutionPolicy Bypass -File "$LOCALAPPDATA/Temp/probe.ps1"

# Option B: backtick-escape every $_ (ugly, fragile, easy to miss one)
powershell -Command "Get-NetTCPConnection | Where-Object {\`$_.OwningProcess -eq 10244}"

# Option C: drop the pipeline filter, query each PID separately
powershell -Command "Get-NetTCPConnection -State Listen | Where-Object { \$_.OwningProcess -eq 10244 }"
# Note: same $_ problem still hits here — Option A is the right answer
```

**Rule:** for any `Where-Object {$_.X ...}` or `ForEach-Object { $_ ... }` pattern, write a `.ps1` file and run with `-File`. Trying to inline-escape `$_` through bash is a 2-minute debugging trap every time, and partial escapes (some `$_` escaped, others not) produce confusing "Missing ')' in method call" parse errors that point at unrelated tokens.

## Pitfall 5 — PowerShell built-in cmdlet name shadowing

Don't name a function `Test-Connection` — that's `Microsoft.PowerShell.Commands.Test-Connection` (ping cmdlet). The script still works (your function wins), but readers get confused and tools that grep for cmdlet usage misfire. Use a distinct name like `Test-AdbConnection`.

## Pitfall 6 — `Get-Process` does not expose `CommandLine`

On Windows PowerShell 5.1, `Get-Process` returns objects whose `.CommandLine` property does not exist — the property exists on `.NET`'s `Process` class in some documentation but PS 5.1's `Get-Process` does not surface it. So `Get-Process python | Where-Object { $_.CommandLine -like '*train.py*' }` matches nothing and you conclude "no trainers running" while one is consuming your entire VRAM.

Use WMI `Win32_Process` for any "find process by command-line" need:

```powershell
Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%train.py%'" |
    Select-Object ProcessId, ParentProcessId, CommandLine
```

This is also the only reliable way to get parent PID and full command line for tree-killing. Use it for: detecting zombies, detecting duplicate processes on a shared GPU, and finding which process owns a port (`-Filter "Name='python.exe'" | % { Get-NetTCPConnection -State Listen -OwningProcess $_.ProcessId }`).

## Pitfall 7 — `Register-ScheduledTask` needs an elevated shell

`Register-ScheduledTask` returns `Access is denied. (0x80070005)` from a non-elevated shell, even with `-Principal RunLevel Highest -LogonType S4U`. The S4U principal tells the task *what* rights to run with, but the registration call itself needs the calling shell to be elevated.

```powershell
# Triggers UAC prompt, runs the registration as Administrator:
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','C:\path
egister.ps1' -Wait -PassThru | Out-Null
```

If you cannot interact with UAC (headless cron, agent-driven), register tasks once when the user is at the console and reuse them; do not try to auto-register from cron.

## Pitfall 8 — MSYS bash also mangles `$_` inside `ForEach-Object` and hash-table literals

Same root cause as Pitfall 4 (`$_` in `Where-Object`) but hits a different shape: PowerShell `[PSCustomObject]@{Name=$_.X; SizeGB=[math]::Round($_.Size/1GB,1)}` inside `ForEach-Object {...}` invoked from the `terminal` tool. Bash sees `$_` and expands it to its own `$_` (last argument of the previous command), so PowerShell receives `/c/Users/KING.X` and `/c/Users/KING.Size` instead of the current pipeline object. Errors look like:

```
Missing ')' in method call.
Unexpected token 'c/Users/KING.Size/1GB' in expression or statement.
The hash literal was incomplete.
```

**Rule:** any time you would write `$_.Foo` inside a `ForEach-Object {...}` or `[PSCustomObject]@{}` block from the `terminal` tool, write a `.ps1` file and invoke it with `-File`. Same fix as Pitfall 4 — file-only is the only reliable path. Trying to escape `$_` with backslashes/backslashes-quotes through the `terminal` parser is the same 2-minute debugging trap.

## Pitfall 9 — Smart-quote / em-dash bytes inside Write-Host literal strings break the parser

When authoring a `.ps1` through `write_file`, an em-dash (`—`, U+2014) or en-dash (`–`, U+2013) inside a `Write-Host "... — ..."` literal looks fine in your editor but PowerShell's parser raises `Missing closing '}'` and `The string is missing the terminator: "` against the line that contains the dash. The em-dash byte is valid UTF-8, but `write_file` may emit it as a different encoding on some hosts, and PowerShell 5.1's parser is encoding-sensitive on non-ASCII bytes inside double-quoted strings.

**Fix:** stick to ASCII (`-`) inside any string literal that PowerShell will parse. If you need a typographic dash, put it in the OUTPUT path (`text_to_speech`, a `.md` comment, a console message via .NET `Console.WriteLine`) — never inside a literal the parser reads.

## Pitfall 10 — Division-by-zero on null WMI memory fields when the system is near-OOM

`Get-CimInstance Win32_OperatingSystem` returns objects whose `FreePhysicalMemory` is sometimes `0` or `$null` on near-OOM Windows hosts (free RAM dropped below the WMI service's own working-set needs). Code like

```powershell
[math]::Round(($os.FreePhysicalMemory/$os.TotalVisibleMemory)*100,1)
```

throws `Attempted to divide by zero.` even when both operands are present — because `TotalVisibleMemory` itself can be `0` on a fully-paged host, or the rounding math runs before the null guard.

**Fix:** always guard before computing ratios against WMI memory fields:

```powershell
if ($os.FreePhysicalMemory -and $os.TotalVisibleMemory -gt 0) { ... } else { Write-Host 'WMI memory unavailable - OOM suspected' }
```

If the guard fails, the system is in fact so out of memory that WMI itself is unreliable. Stop gathering telemetry; switch to non-WMI commands (`nvidia-smi`, `Get-PSDrive`, `Get-Process`) for further diagnosis. Do not retry the CIM call — it will keep returning 0 until pressure releases.

## Pitfall 11 — WMI/CIM calls hang on near-OOM systems (exit code 124 from terminal)

On a host with <500 MB free RAM, `Get-CimInstance` queries against broad classes (`Win32_LogicalDisk`, `Win32_StartupCommand`, `Win32_Service`) can stall for 60–120+ seconds before either returning or timing out from the `terminal` tool's `timeout=` ceiling. Symptom: command exits with `124` and no output. The kernel is paging WMI's working set in and out so the call never completes.

**Fix:** when the system is near-OOM, replace CIM/WMI with the lighter `Get-PSDrive`, `Get-Process`, `Get-Service`, `Get-NetAdapter`, `powercfg`, `bcdedit`, and `nvidia-smi`. They each query a single provider and don't pull full WMI repositories. Never run a 60-second broad CIM sweep as the first command on a near-OOM host; you'll burn the budget and end up with no data.

## Quick Reference

```powershell
# Check if a script parses (run before -File)
$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('path.ps1', [ref]$null, [ref]$errors) | Out-Null; if (-not $errors) { "OK" } else { $errors }

# Run a script bypassing policy (PowerShell 5.1 default blocks unsigned scripts)
powershell -ExecutionPolicy Bypass -File "C:\path\to\script.ps1"
```

## Verification

After every `.ps1` write, run the parser-checker above before `powershell -File`. A passing parse takes ~50ms; a confusing runtime failure takes minutes.
