---
name: python-environment-management
description: Manage Python environments via uv.
---
# Python Environment Management

Use this skill when a project lacks standard dependency manifests (e.g., `requirements.txt`, `pyproject.toml`) but requires running Python scripts or tests.

## Workflow
1. **Toolchain Audit**: Verify if `uv` is available via `terminal`. If present, use `uv` for all operations to ensure speed and reliability. Note that environments frequently lack `pip` entirely in favor of `uv`.
2. **Manifest Check**: Search the project root/subdirectories for `requirements.txt`, `pyproject.toml`, or `Pipfile`.
3. **Dependency Discovery (Reverse Engineering)**: If no manifest is found, scan `.py` files using `read_file` to identify `import` statements that are not part of the standard library.
4. **Environment Provisioning**: 
   - Create/Activate a virtual environment (e.g., `.venv`).
   - Use `uv pip install <package>` to satisfy discovered dependencies.
5. **Verification**: Run the target script or test suite to ensure the environment is complete and functional.

## Pitfalls
- **Missing Pip**: Do not assume `pip` exists; modern environments (like this one) often use `uv` exclusively.
- **Incomplete Scans**: A single `read_file` might miss imports in deeply nested or unindexed files; combine with recursive searches if necessary.
- **Windows venv isolation**: On Windows, `python -m venv` may create a broken venv that inherits the parent's `PYTHONPATH` (Hermes paths leak in). Use `uv venv` instead for clean isolation. See [references/uv-venv-isolation.md](references/uv-venv-isolation.md).
- **Subprocess PYTHONPATH leakage**: Even with a clean venv, subprocesses launched from Hermes inherit the parent's `sys.path`. Create a `launch.py` wrapper that cleans `sys.path` before importing project code. See [references/pythonpath-leakage-fix.md](references/pythonpath-leakage-fix.md).
- **Dependency Shadowing via Pip Cache/Path**: On Windows, even if using an absolute path to `.venv\\Scripts\\pip`, it may incorrectly report "Requirement already satisfied" by pointing to the global Agent environment (`hermes-app\\venv`) rather than the local project directory. Use `--no-cache-dir` or `--force-reinstall` with absolute paths to break this loop. See [references/dependency-shadowing-fix.md](references/dependency-shadowing-fix.md).
- **NVML/pynvml shadowed by polluted sys.path**: When `PYTHONPATH` env var puts hermes's site-packages at `sys.path[0]`, `import pynvml` resolves to that venv's package — its loader may not call `os.add_dll_directory(System32)`, so `pynvml.nvmlInit()` raises `NVMLError_LibraryNotFound` even though `C:\Windows\System32\nvml.dll` exists. Symptom is GPU telemetry stuck on "—". Fix: prepend project site-packages to `sys.path` and demote hermes paths. See `references/nvml-pynvml-syspath-fix.md`.
- **`python -m pytest` fails with `No module named pytest`** even when the project's `uv venv` has pytest installed. Reason: when launched from `execute_code` or a bash `cd`, the bare `python` resolves to the Hermes interpreter (`C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`), which has no pytest. Always invoke the project's venv explicitly. Use `uv run pytest tests/ -v` from the project root — uv resolves the project's venv automatically. If the project has no uv config (`uv.toml` / `pyproject.toml` with `[tool.uv]`), point at the venv's pytest directly: `C:/path/to/.venv/Scripts/python.exe -m pytest tests/ -v`. Bare `pytest` also works if the project venv's `Scripts/` is first on PATH. Never assume the bare `python -m pytest` will land on the project venv.

- **Kernel `python` (your shell, in `execute_code`/tool calls) and BG `terminal`'s `python` are TWO DIFFERENT interpreters, not the same one.** The kernel Python auto-injects site-packages from `C:\Users\KING\AppData\Local\hermes\installs\...venv\Lib\site-packages` into `sys.path` so `import fastapi`, `import stripe`, `import requests` resolve there. The BG `terminal`'s `python` (the bare interpreter in your bash terminal) does NOT have that injection — it only sees its own site-packages. Symptom: my shell can `import fastapi` and `python -c "import fastapi"` works, but `cd /path && python -u script.py` in BG exits with `FastAPI not installed` or `ModuleNotFoundError: No module named 'fastapi'`. Fix: set `PYTHONPATH` to the install's site-packages in the BG shell BEFORE `python script.py`:
  ```bash
  export PYTHONPATH="C:\Users\KING\AppData\Local\hermes\installs\59bf9ddfe703d23a\environments\6eeb6a5315e9474d872af255795d046c\venv\Lib\site-packages"
  cd /c/.../scripts && python -u script.py
  ```
  Distinct from parent→child PYTHONPATH leakage: the kernel Python already has the right path on `sys.path`, but BG shell `python` doesn't inherit the kernel's `sys.path` — only env vars persist. Diagnostic: if `python -c "import X"` works in your execute_code but BG `terminal` says `ModuleNotFoundError`, you have a kernel-vs-BG split, not a leak. Fix: identify the install that owns the package (look at `sys.path[0]` in your kernel and find its `Lib/site-packages`), then `export PYTHONPATH=<that-path>` in the BG invocation.
- **Test runner must be verified before trusting pass counts.** When a sub-agent reports "20/20 tests passing" after a refactor, re-run the same suite from the parent context with the same invocation the user will see — the sub-agent may have used a venv pytest while the user's terminal would hit the bare Hermes python and see `ModuleNotFoundError`. A test suite the user can't reproduce is not a passing test suite.
- **Renaming a brand or persona across the repo requires six sweeps, not one.** File names, JSON content, docstring, generator constants, hardcoded HTML in the server template, and rendered artifacts (SVG portraits, JSONL SFT) are independent. A `grep -rn` catches the first four; the rendered artifacts only update when the generator runs again. Sequence: (1) rename files, (2) update JSON `name` fields, (3) update generator constants + phrase-level swaps, (4) re-run generator to overwrite artifacts, (5) update HTML templates, (6) commit + push + verify the live page shows the new name. Skipping (4) leaves the public-facing artifacts stale.
- **Filenames with hyphens cannot be imported as Python modules.** `python -m shop-bot` exits 1 with `No module named 'shop_bot'` because Python module identifiers must match `[A-Za-z_][A-Za-z0-9_]*`. A file named `shop-bot.py` is not importable — only its sibling with underscores (`shop_bot.py`) works. When you find yourself writing `import shop_bot` in launcher code, verify the source file uses underscores (not hyphens). Symptom: `cd <dir> && python -m <hyphen-name>` fails even though the file sits in the cwd. The cwd-on-sys.path behavior plus the invalid identifier is the giveaway. Copy or rename to the underscored form before any `import` statement.

- **A namespace package loses to a regular package of the same name anywhere on
  `sys.path`.** A directory without `__init__.py` is only a namespace portion, and
  any regular package of the same name found elsewhere on the path wins —
  regardless of which one comes first. Symptom: `ModuleNotFoundError` naming the
  SUBMODULE (`No module named 'tools.history_secret_sweep'`) while `import tools`
  itself works fine; the imported `tools` was simply the wrong one. Fix: give the
  directory an `__init__.py` so it is a regular package found first on the path.

## References
- references/dependency_discovery_via_import_scan.md: Notes on using regex/import scanning to rebuild missing manifests.
- references/pythonpath-leakage-fix.md: Runtime sys.path cleanup when subprocess inheritance can't be avoided.
- references/uv-venv-isolation.md: Why `uv venv` is preferred over `python -m venv` on Windows.
- references/fastapi-pydantic-v2-pitfall.md: FastAPI union return type crash under Pydantic v2 and the `response_model=None` fix.
- references/fastapi-windows-runtime-pitfalls.md: 10 hard-won Windows+FastAPI+asyncio pitfalls (asyncio.wait_for can't cancel threads, Win32 PSAPI via ctypes, missing `: WebSocket` annotations, kwargs-only signatures with run_in_executor, multicast IP hangs, log buffering, etc.).