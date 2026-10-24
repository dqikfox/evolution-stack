# PowerShell-String-With-Parens-and-Apostrophes Trap

When invoking PowerShell from MSYS bash with `-Command "..."`, the
double-quoted string is parsed by **PowerShell itself first** before bash
gets a chance. Specific patterns inside the string will crash the parse.

## Parens inside double-quoted strings

```powershell
Write-Host "Test: press Ctrl+Alt+N now (or click Start Menu entry)."
```

PowerShell sees the `(` inside the double-quoted string and tries to
evaluate it as a subexpression. Result:

```
At line:1 char:51
+ Write-Host "Test: press Ctrl+Alt+N now (or click Start Menu entry)."
+                                                  ~
The string is missing the terminator: ".
```

**Fix:** Replace parens with dashes, or escape with backticks:
```powershell
Write-Host "Test: press Ctrl+Alt+N now - or click Start Menu entry."
# OR
Write-Host "Test: press Ctrl+Alt+N now `(or click Start Menu entry`)."
```

## Apostrophe inside single-quoted PowerShell string

A `'` inside `'...'` terminates the string early. Use either double-quotes or
escape with doubled `''`:

```powershell
# WRONG — the 'N' apostrophe is treated as end of string
$desc = 'Open NEXUS CORE brain GUI. Hotkey Ctrl+Alt+N. Server starts when needed.'

# RIGHT
$desc = "Open NEXUS CORE brain GUI. Hotkey Ctrl+Alt+N. Server starts when needed."
# OR escape:
$desc = 'Open NEXUS CORE brain GUI. Hotkey Ctrl+Alt+N. Server starts when needed''s, but apostrophe-eaten.'
```

## cmd.exe /c + MSYS path translation

```bash
cmd.exe /c "call start.bat"  # expands /c to a path argument, errors with "The syntax of the command is incorrect"
cmd.exe //c "start.bat"      # opens an interactive cmd prompt, doesn't actually run start.bat
```

The MSYS path translation layer mangles `cmd.exe`'s switch character.

**Fix:** Skip cmd.exe entirely. Launch via a `.ps1` script, a Python wrapper, or
Powershell directly:
```powershell
powershell.exe -ExecutionPolicy Bypass -File "Q:\path\script.ps1"
# OR
/c/path/to/python.exe script.py
```

## UTF-8 BOM bites PowerShell scripts

Files written by Python or vim may include a UTF-8 BOM (Byte Order Mark,
bytes `EF BB BF` at the start). PowerShell <= 5.1 treats BOM-prefixed files
as UTF-8 but prints garbled error messages. When editing a `.ps1` later,
the BOM can sneak back in and cause cryptic parse errors on the first
character.

**Fix:** When writing new `.ps1` files from a tool that may emit BOM,
write as ASCII-only first, or strip the BOM with:
```powershell
$bytes = [System.IO.File]::ReadAllBytes('Q:\path\script.ps1')
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    [System.IO.File]::WriteAllBytes('Q:\path\script.ps1', $bytes[3..($bytes.Length - 1)])
}
```
