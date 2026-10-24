# uv venv vs python -m venv: Clean Isolation on Windows

Session: 2026-08-16  
Problem: `python -m venv .venv` creates a broken venv on Windows that inherits the parent Python's `sys.path`, causing imports from the wrong environment.

## Symptom

After creating a venv with `python -m venv`:
```python
# Target venv Python: C:\project\.venv\scripts\python.exe
# But sys.path still includes Hermes packages:
import sys
print(sys.path)
# ['C:\\project', 'C:\\Users\\KING\\AppData\\Local\\hermes\\hermes-agent\\venv\\Lib\\site-packages', ...]
```

This causes `ModuleNotFoundError` for packages installed in the target venv (e.g., `chromadb`, `uvicorn`) because Python finds the parent paths first.

## Root Cause

The MSYS/Python `venv` module may set `include-system-site-packages = true` in `pyvenv.cfg`, or the Windows venv creation inherits `PYTHONPATH` from the parent process.

## Fix: Use `uv venv`

```bash
# Remove broken venv
rm -rf .venv

# Create clean isolated venv with uv
uv venv

# Verify isolation
.venv/scripts/python.exe -c "import sys; print(sys.path[0])"
# Should show: C:\project\.venv\Lib\site-packages
# Should NOT show Hermes paths
```

## Why uv venv works

`uv venv` creates a venv with `include-system-site-packages = false` by default and does not inherit the parent's `PYTHONPATH`. The resulting interpreter is truly isolated.

## Verification

```bash
# Check pyvenv.cfg
cat .venv/pyvenv.cfg
# include-system-site-packages = false  ✅

# Check no parent leakage
.venv/scripts/python.exe -c "
import sys
for p in sys.path:
    if 'hermes' in p.lower():
        print('LEAK:', p)
"
# Should print nothing
```

## Related

- `references/pythonpath-leakage-fix.md` — Runtime sys.path cleanup in launcher scripts
- `python-environment-management/SKILL.md` — Main uv workflow
