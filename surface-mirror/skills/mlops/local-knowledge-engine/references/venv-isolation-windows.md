# Venv Isolation for Local Servers on Windows

## Problem

On Windows with Hermes Agent installed, the system Python (`python.exe` in PATH) is often the Hermes-managed Python (e.g., `C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`). When spawning subprocesses or running scripts, this Python leaks into child processes, causing:

- Wrong `sys.path` (Hermes packages visible before venv packages)
- Import errors for packages installed in the project venv (`requests`, `uvicorn`, `chromadb`)
- `ModuleNotFoundError` even after `pip install` succeeds in the project venv

## Symptom

```
File "...\server.py", line 17, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'
```

But `pip list` inside the venv shows `requests` installed. The process is running under the wrong Python.

## Root Cause

Windows process creation inherits the parent's environment. When Hermes Agent's Python spawns a subprocess, `sys.path` from Hermes leaks in. The venv's `python.exe` is technically correct, but `PYTHONPATH` or executable resolution finds the Hermes interpreter first.

## Solution: Explicit venv Python Path

### 1. Always use absolute venv Python path

```python
import subprocess
import sys

# ❌ Wrong — may resolve to Hermes Python
subprocess.run(["python", "server.py"])

# ✅ Correct — absolute path to venv Python
VENV_PYTHON = r"C:\Users\KING\nexus-core-throne\.venv\scripts\python.exe"
subprocess.run([VENV_PYTHON, "server.py"])
```

### 2. Isolate `sys.path` at startup

Create a `launch.py` wrapper that removes Hermes paths:

```python
"""Launcher script that ensures clean Python path."""
import sys
import os

# Remove Hermes paths that leak into the venv
hermes_paths = [p for p in sys.path if "hermes-agent" in p.lower()]
for p in hermes_paths:
    sys.path.remove(p)

# Add venv site-packages FIRST
venv_site = r"C:\Users\KING\nexus-core-throne\.venv\Lib\site-packages"
if venv_site not in sys.path:
    sys.path.insert(0, venv_site)

# Now import and run
import uvicorn
from server import app

uvicorn.run(app, host="127.0.0.1", port=8650)
```

### 3. Use `uv` for venv creation (not `python -m venv`)

`python -m venv` on Windows sometimes links to the system Python that has Hermes packages. `uv venv` creates a cleaner isolation:

```bash
# Remove broken venv
rm -rf .venv

# Create clean venv with uv
uv venv .venv

# Install dependencies INTO the venv
uv pip install -r requirements.txt
```

**Critical:** Do NOT use `pip install` without `uv` prefix — it may install into Hermes Python.

## Verification

```python
import sys
print("Executable:", sys.executable)
print("Path 0:", sys.path[0])
assert "hermes-agent" not in sys.executable.lower(), "WRONG PYTHON!"
assert "nexus-core-throne" in sys.executable.lower(), "Not using Nexus venv!"
```

## Common Mistakes

| Mistake | Result |
|---------|--------|
| `python server.py` (no absolute path) | Runs Hermes Python, import errors |
| `pip install requests` (no venv prefix) | Installs into Hermes, not project venv |
| `.venv\scripts\python.exe -m pip install` | May still leak Hermes paths into subprocesses |
| Not checking `sys.executable` | Silent failure, confusing import errors |

## For Hermes Agent Sessions

When using `terminal()` or `execute_code()` to run a project server:

```bash
# Always prefix with absolute venv path
cd /c/Users/KING/nexus-core-throne
.venv/scripts/python.exe launch.py
```

For `execute_code` Python scripts:

```python
import subprocess
result = subprocess.run(
    [r"C:\Users\KING\nexus-core-throne\.venv\scripts\python.exe", "script.py"],
    capture_output=True, text=True, timeout=60
)
```

## References

- `uv` docs: https://docs.astral.sh/uv/
- Python venv isolation: https://docs.python.org/3/library/venv.html
- Windows process environment inheritance: https://docs.python.org/3/library/subprocess.html#popen-constructor
