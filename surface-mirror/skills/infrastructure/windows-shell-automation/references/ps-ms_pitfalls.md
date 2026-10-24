# MSYS2 vs PowerShell Parsing Pitfalls

When executing `powershell -Command "..."` from an MSYS2/Bash terminal, certain syntax patterns will fail due to how the shell wrapper handles characters before they reach PowerShell.

## The Error
The user sees errors like:
`At line:1 char:51 ... Missing variable name after foreach.` 
or 
`Unexpected token 'c/Users/KING.Length' in expression...`

## Root Cause
MSYS2 performs path translation (e.g., converting `/c/Users/...` to `C:\Users\...`). If a PowerShell command contains strings that *look* like Unix paths or use unquoted variables that Bash might attempt to expand, the string becomes corrupted before PowerShell can parse it. Additionally, complex object access using dots (`$_.`) inside single-line quotes can be misinterpreted by the shell as part of its own parsing logic.

## Mitigation Strategies
1.  **Use Windows Primitives**: Always use `$env:USERPROFILE`, `$env:TEMP`, or absolute Windows-style paths (`C:\...`) instead of bash-style aliases (`$HOME`, `/c/...`).
2.  **Simplify Expressions**: Avoid nested property access (e.g., `[math]::Round($_.Length...)`) within a single `-Command` string passed via Bash. Break complex operations into multi-line scripts if possible, or pass them through an existing file.
3.  **Quote Aggressively**: Wrap all internal PowerShell strings in single quotes to prevent the MSYS2 layer from attempting expansion/translation on contents that are intended for the PowerShell engine.