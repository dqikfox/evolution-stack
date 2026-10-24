# Windows-Specific Quirks

Hermes runs natively on Windows (PowerShell, cmd, Windows Terminal, git-bash
mintty, VS Code integrated terminal). Most of it just works, but a handful
of differences between Win32 and POSIX have bitten us — document new ones
here as you hit them so the next person (or the next session) doesn't
rediscover them from scratch.

### Input / Keybindings

**Alt+Enter doesn't insert a newline** — Windows Terminal (and mintty) grab it
for fullscreen before prompt_toolkit sees it. Use **Ctrl+Enter** instead (the
CLI binds it to newline on Windows; raw Ctrl+J does the same, harmlessly).
To inspect how your terminal reports a keystroke, run
`python scripts/keystroke_diagnostic.py` from the repo root.

### Config / Files

**HTTP 400 "No models provided" on first run** — `config.yaml` was saved with
a UTF-8 BOM (Notepad does this). Re-save as UTF-8 without BOM;
`hermes config edit` writes correctly.

### `execute_code` / Sandbox

**WinError 10106** from the sandbox child process — it can't create an
`AF_INET` socket. Root cause is usually Hermes's env scrubber dropping
`SYSTEMROOT`/`WINDIR`/`COMSPEC` (Python's `socket` needs `SYSTEMROOT` to find
`mswsock.dll`), not a broken Winsock LSP. The `_WINDOWS_ESSENTIAL_ENV_VARS`
allowlist in `tools/code_execution_env.py` covers it; if you still hit it,
echo `os.environ` inside an `execute_code` block to confirm `SYSTEMROOT` is set.

### Testing on Windows

Prepare the checkout through PM first. With its Python 3.14, build an independent
test environment at a fresh path:

```powershell
python -m pm.build_env --source . --out .venv --group dev --group test
```

The output must not exist. Before regeneration, stop its processes and explicitly
remove only that disposable environment. Do not install into the application
payload or modify a selected dependency generation.

Run the canonical runner through Git Bash:

```bash
scripts/run_tests.sh tests/foo/test_bar.py -v --tb=short
```

The runner discovers `.venv/Scripts/python.exe`, clears credentials and
`PYTHONPATH`, and isolates each test file. For an external test environment,
set `HERMES_PYTHON` to its Python executable. PM shell activation alone does
not supply pytest after the runner clears `PYTHONPATH`.

### pywin32 / concurrent-log-handler at startup

**`pywintypes is required for Win32Locker but not found` warning in logs** — `pywin32` is installed but its DLLs aren't at the venv root, so the log handler can't find them before Python's DLL search path is fully set up. Fix once:

```bash
"$HERMES_VENV/Scripts/python" "$HERMES_VENV/Scripts/pywin32_postinstall.py" -install
```

Where `HERMES_VENV=C:/Users/KING/AppData/Local/hermes/hermes-agent/venv`. This copies `pywintypes311.dll` and `pythoncom311.dll` to the venv root. Restart Hermes after. The "you do not have permissions to install COM objects" message is cosmetic — the DLL copy still succeeds.

### Hermes venv Python / pip in MSYS bash

**`pip show` and `pip install` hang or error with version-mismatch warnings** in MSYS/git-bash — the system pip resolves to Python 3.14 while the Hermes venv is 3.11, causing a mismatch that blocks. Always target the Hermes venv directly:

```bash
PYEXE="/c/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
"$PYEXE" -m pip install <package>       # install into Hermes venv
"$PYEXE" -m pip show <package>          # check Hermes venv packages
```

Use `uv pip show <package>` as a fast alternative for presence checks (no hang, no mismatch). Do NOT use a `$HERMVENV`-style variable with path expansion — MSYS expansion of backslash paths fails silently in certain quoting contexts; use the explicit POSIX path above.

### Path / Filesystem

**Line endings.** Git may warn `LF will be replaced by CRLF`. Cosmetic — the
repo's `.gitattributes` normalizes. Don't let editors auto-convert committed
POSIX-newline files to CRLF.

**Forward slashes work almost everywhere.** `C:/Users/...` is accepted by
every Hermes tool and most Windows APIs. Prefer forward slashes in code
and logs — avoids shell-escaping backslashes in bash.

