# PYTHONPATH Leakage When Launching Subprocesses

Session: 2026-08-16  
Problem: Python subprocesses launched from Hermes inherit the parent's PYTHONPATH, causing imports from the wrong virtual environment.

## Symptom

Subprocess uses the target venv's Python executable but still imports packages from Hermes' venv:

```python
# Target venv: C:\Users\KING\project\.venv
# Hermes venv: C:\Users\KING\AppData\Local\hermes\hermes-agent\venv

import fastapi  # Works (from Hermes venv)
import chromadb  # FAILS — Hermes venv doesn't have it
```

## Root Cause

`sys.path` from the parent process leaks into the child. The child Python inherits `sys.path` entries pointing to the parent's site-packages.

## Fix: Explicit Path Isolation

Before importing anything in a subprocess script:

```python
import sys
import os

# Remove parent paths that leak in
hermes_paths = [p for p in sys.path if "hermes-agent" in p.lower()]
for p in hermes_paths:
    sys.path.remove(p)

# Add target venv FIRST (before any other paths)
venv_site = r"C:\path\to\.venv\Lib\site-packages"
if venv_site in sys.path:
    sys.path.remove(venv_site)
sys.path.insert(0, venv_site)

print(f"First path: {sys.path[0]}")
```

## Alternative: Use `uv run`

```bash
# Forces the correct interpreter, bypassing PATH resolution
uv run --python C:\path\to\.venv\scripts\python.exe script.py
```

## Alternative: Write a Launcher Script

Create `launch.py` in the project root:

```python
import sys

# Remove Hermes paths
for p in list(sys.path):
    if "hermes-agent" in p.lower():
        sys.path.remove(p)

# Add our venv first
sys.path.insert(0, r"C:\path\to\.venv\Lib\site-packages")

# Now import project code
from myapp import app
import uvicorn

uvicorn.run(app, host="127.0.0.1", port=8650)
```

## Verification

```python
import sys
print(sys.executable)  # Should show target venv
print(sys.path[0])     # Should show target venv site-packages
```

## Related

- `python-environment-management/SKILL.md` — Main venv setup workflow
