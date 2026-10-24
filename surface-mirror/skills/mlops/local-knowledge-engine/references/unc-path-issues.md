# UNC Path Issues on Q: Drive (and other mapped network drives)

## The problem

On this machine, `Q:` is a mapped network drive to `\\Msi\e\`. When git-bash spawns `cmd.exe` (which is what `hermes verify` and any subprocess launched via Hermes does), the working directory becomes a UNC path. cmd.exe refuses to run with a UNC cwd and prints:

```
'\\Msi\e\ultron-memory\nexus-core'
CMD.EXE was started with the above path as the current directory.
UNC paths are not supported.  Defaulting to Windows directory.
```

Symptoms:

- `pip install` from the project directory silently installs into the wrong Python (or fails to find a target at all)
- Background `uvicorn` servers started by `hermes verify` can't bind to a known port
- File watcher / sync scripts lose track of their working directory

## The fix — venv on C:, source on Q:

Keep your project source on Q: (so the path matches across machines, e.g. `\\Msi\e\ultron-memory\nexus-core`), but **put the venv on C:** where the filesystem is local and fast:

```python
# Q:\ultron-memory\nexus-core\.hermes\environment.json
{
  "name": "NEXUS CORE",
  "kind": "fastapi",
  "bootstrap": [
    "C:\\Users\\KING\\.cache\\nexus-venv\\Scripts\\python.exe -m pip install -q fastapi uvicorn jinja2 chromadb requests pyyaml python-multipart"
  ],
  "start": "C:\\Users\\KING\\.cache\\nexus-venv\\Scripts\\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8650",
  "test": "C:\\Users\\KING\\.cache\\nexus-venv\\Scripts\\python.exe -m pytest tests/ -v",
  ...
}
```

Use **absolute paths** in the bootstrap and test commands, never relative. The whole point is that the venv interpreter is independent of the project cwd.

## Detection

When `hermes verify` prints the "UNC paths are not supported" warning followed by a successful install, that install was running in an *unintended* environment. Check:

```bash
# Wrong — pip finds system Python, ignores the project's venv
which python   # → /c/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe

# Right — the venv lives on C:
ls C:/Users/KING/.cache/nexus-venv/Scripts/python.exe
```

If your venv is on Q: (e.g. `Q:\ultron-memory\nexus-core\.venv\Scripts\python.exe`), and the project `.venv/pyvenv.cfg` has a `home =` pointing to a path that no longer exists (common after moving the project), every `pip install` will silently install into the wrong tree and the venv stays broken.

## The pyvenv.cfg trap

The default venv layout has a `.venv/pyvenv.cfg` with a `home` line that hard-codes the original Python path. If you copy or move the venv, the `home` line is now wrong. Symptom: the venv's `python.exe` is a "shim" that fails to find its real interpreter with errors like:

```
uv trampoline failed to spawn Python child process (entity not found os error 2)
```

Two fixes, in order of preference:

1. **Edit pyvenv.cfg** to point at a real on-disk Python. This is what worked for the Hermes venv in this session:

   ```ini
   # Q:\ultron-memory\nexus-core\.venv\pyvenv.cfg
   home = C:\Users\KING\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none
   ```

2. **Recreate the venv from scratch** on C: with a fresh interpreter:

   ```bash
   uv venv C:/Users/KING/.cache/nexus-venv --python "C:/Users/KING/AppData/Roaming/uv/python/cpython-3.11-windows-x86_64-none/python.exe"
   C:/Users/KING/.cache/nexus-venv/Scripts/python.exe -m pip install fastapi uvicorn jinja2 chromadb requests pyyaml python-multipart
   ```

   Always use the **copy** link mode when installing into a venv on a network drive (uv defaults to hardlinks, which fail across filesystems):

   ```bash
   UV_LINK_MODE=copy C:/Users/KING/.cache/nexus-venv/Scripts/python.exe -m pip install ...
   ```

## Verifying your setup

A healthy brain on Q: drive should:

- Have source files on Q: (e.g. `Q:\ultron-memory\nexus-core\server.py`)
- Have the venv on C: (e.g. `C:\Users\KING\.cache\nexus-venv\Scripts\python.exe`)
- Have a manifest in `Q:\ultron-memory\nexus-core\.hermes\environment.json` referencing the C: venv
- Start a uvicorn on :8650 in <2 seconds
- Pass all `hermes verify` phases with exit 0

If any of these is false, the Q: UNC issue is the prime suspect.

## Why this is a session-specific fix worth saving

The venv isolation pattern in `references/venv-isolation-windows.md` covers Hermes Python leaking into subprocesses. This file extends it to cover the related-but-distinct issue of venvs on network/UNC paths, which the venv-isolation doc doesn't address. Together they cover "Python works on this Windows machine" end-to-end.
