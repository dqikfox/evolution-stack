# Venv isolation on THRONE — a project venv can silently run on the AGENT's packages

The Hermes agent runtime injects `PYTHONPATH` into every child process it
spawns, pointing at the agent's own interpreter directories:

```
...\Temp\hermes_kernel_XXXX
...\hermes\installs\<id>\environments\<id>\venv\Lib\site-packages
...\hermes\hermes-agent
```

Those entries land AHEAD of a project virtualenv's own `site-packages` on
`sys.path`, so the project imports the agent's `numpy`/`pydantic`/`fastapi`/
`starlette` instead of its own. Measured on THRONE:

- the NEXUS venv could not import `numpy` at all (ImportError) and had no
  `pydantic` or `fastapi` — completely broken from an agent context;
- the TESSERACT suite ran against `fastapi 0.133.1` / `starlette 1.3.1`
  while the project pins `0.143.3` / `1.8.0` — green tests validating a
  dependency set the project does not ship.

**A green test suite under a shadowed environment is not evidence.**

## The fix (make the venv self-defending)

Drop a `_hermes_env_guard.py` plus a `zzz_hermes_env_guard.pth`
(`import _hermes_env_guard`) into the venv's `site-packages`. At interpreter
start the guard removes foreign `site-packages` entries from `sys.path` and
from `PYTHONPATH` (so children inherit the clean value).

Installed in:
- `C:\Users\KING\.cache\nexus-venv\Lib\site-packages`
- `C:\Users\KING\Projects\TESSERACT\.venv\Lib\site-packages`

Detection rule: an entry is foreign if it is not under this interpreter's
prefix/base-prefix and it is either a `site-packages`/`dist-packages`
directory or lives under the agent's `hermes\installs`, `hermes\hermes-agent`
or `hermes_kernel_*` trees.

## The check (run BEFORE the test suite)

- `C:\Users\KING\Projects\TESSERACT\scripts\check_env_isolation.py`
- `E:\ultron-memory\nexus-core\tools\check_env_isolation.py`

Both derive the package list from `requirements.txt` and assert every package
resolved inside the project environment, and that the interpreter itself
belongs to it.

They distinguish two different problems, which matters:

- **hard failure** — a declared dependency that is NOT installed
  (`declared in requirements.txt but NOT installed in this environment`).
  This is a real defect: it was silently being satisfied by the leaked path.
- **name mapping** — a distribution name is not an import name:
  `python-multipart` -> `multipart`, `claude-agent-sdk` -> `claude_agent_sdk`,
  `pytest-asyncio` -> `pytest_asyncio`, `pyyaml` -> `yaml`.
  `httpx2` is a DIFFERENT package and is NOT `httpx`.

## Two real defects this uncovered

1. **TESSERACT's `server.py` imports `httpx` in 9 places and the venv had no
   `httpx`** — only `httpx2`, which provides a different import name. The
   routes worked only because the leaked path supplied `httpx`. Fixed by
   `uv pip install httpx>=0.27` into the venv and adding `httpx>=0.27` to
   `requirements.txt`.
2. **NEXUS's `requirements.txt` declared `sentence-transformers` +
   `transformers` + `tokenizers` + `huggingface-hub`** (torch, gigabytes)
   while the running service embeds through chroma's ONNX MiniLM function and
   never touches them. A fresh `pip install -r requirements.txt` would have
   pulled torch for nothing, and the file stopped describing reality. The
   core file now lists only what the venv contains; the heavy stack moved to
   `requirements-optional.txt`.

## Defence in depth

When spawning a service from an agent session, strip the env anyway:

- `evo/services.py:clean_env()` (evolution-stack healer)
- `run_nexus.py:child_env()` (NEXUS supervisor)
- TESSERACT `start.py:server_env()`

Each removes `PYTHONPATH`, `PYTHONHOME` and `PYTHONSTARTUP` from the child
environment, so the venv guard is not the only line of defence.

## Verify

```bash
cd C:/Users/KING/Projects/TESSERACT && .venv/Scripts/python.exe scripts/check_env_isolation.py
cd E:/ultron-memory/nexus-core && "C:/Users/KING/.cache/nexus-venv/Scripts/python.exe" tools/check_env_isolation.py
```

Both must exit 0 with an empty `failures` list before a test result means
anything.
