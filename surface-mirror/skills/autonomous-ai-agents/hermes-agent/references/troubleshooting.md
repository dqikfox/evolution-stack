# Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `python -c "import pm; pm.sync_venv(['stt-whisper'], explicit=True)"` or set API key
3. In gateway: `/restart`. In CLI: exit and relaunch.

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes auth` — re-authenticate OAuth providers (or `hermes auth add <provider>`)
3. Check `.env` has the right API key
4. **Copilot 403**: `gh auth login` tokens do NOT work for Copilot API. You must use the Copilot-specific OAuth device code flow via `hermes model` → GitHub Copilot.

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** In gateway: `/restart`. In CLI: exit and relaunch.
- **Code changes:** Restart the CLI or gateway process

### web_extract shows a stale page (result caching)
`web_search`/`web_extract` cache results for 20 minutes (PR #94618) — a
repeat fetch of the same URL within the TTL is served from cache, which
can look like "my website changes aren't showing up."

Automatic carveouts (always fetched live, never cached):
- localhost / 127.0.0.1 / `*.local` / `*.localhost` / single-label LAN
  hostnames / private + link-local IP ranges (dev servers, hot-reload
  builds, chat-GUI artifact previews)
- URLs matched by `security.website_blocklist`
- failed responses and keyless-rescue-served responses

Developing a site tested over the PUBLIC internet (Vercel/Netlify
preview, ngrok/cloudflared tunnel, staging domain)? Public DNS isn't
auto-carved-out — list the host in config.yaml:

```yaml
web:
  cache_exempt_hosts:      # always fetched live; effective immediately
    - mysite.vercel.app
    - "*.ngrok-free.app"
    - mysite.dev           # suffix match: also covers preview.mysite.dev
```

Blunt instruments: `web.cache_ttl_minutes: 1` (min) or
`web.cache_enabled: false` disables both caches entirely.

### Skills not showing
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `hermes -s name` (or the skill's own `/<name>` slash command)

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

Common gateway problems:
- **Gateway dies on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`
- **Gateway dies on WSL2 close**: WSL2 requires `systemd=true` in `/etc/wsl.conf` for systemd services to work. Without it, gateway falls back to `nohup` (dies when session closes).
- **Gateway crash loop**: Reset the failed state: `systemctl --user reset-failed hermes-gateway`

### Hermes runtime venv discovery (CRITICAL — find this before installing packages)

**`hermes-agent/venv` is the git source tree's venv (Python 3.11), NOT the running agent's venv.** Installing packages there has no effect on the live Hermes process.

The actual runtime is a hashed isolated venv under:
```
%LOCALAPPDATA%\hermes\installs\<hash>\environments\<hash>\venv\
```
The Python version there may differ (e.g. 3.14.7 vs 3.11). Python 3.14 has **no `pip` module** — use `uv` instead.

**How to find the runtime venv path:**
```bash
# Look for site-packages paths in recent agent.log tracebacks
grep -m3 'site-packages' "$LOCALAPPDATA/hermes/logs/agent.log" | head -3
```
The path shown in tracebacks is the real one. Extract `...\venv\` from it.

**Installing packages into the correct venv:**
```bash
# uv works even when pip is absent (Python 3.14+)
uv pip install --python "C:/Users/KING/AppData/Local/hermes/installs/<hash>/environments/<hash>/venv/Scripts/python.exe" <package>

# Verify
"<path>/python.exe" -c "import <package>; print('OK')"
```

**Pitfall — pywin32 DLLs:** after installing `pywin32` into the venv, run `pywin32_postinstall.py -install` from the venv's Scripts dir to copy the DLLs to the venv root; otherwise `pywintypes` may fail to load at Hermes startup before PATH is fully set.

```bash
"<venv>/Scripts/python.exe" "<venv>/Scripts/pywin32_postinstall.py" -install
```

### `Failed to load plugin 'X': No module named 'X'`

This fires when a Hermes plugin directory is a wrapper around an inner sub-package of the same name, and the wrapper tries `from X import ...`. Hermes loads plugins by file path (not by inserting the plugins directory into `sys.path`), so `from X import ...` re-enters the wrapper itself — circular import.

**Fix the plugin's `__init__.py`:** replace `from <name> import ...` with an explicit `importlib.util.spec_from_file_location` call that loads the inner package under a unique module name. Also inject the active venv's `purelib` so third-party dependencies (e.g. PyNaCl/`nacl`, `zeroconf`) are findable:

```python
import importlib.util as _ilu, os, sys, sysconfig
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.join(_PLUGIN_DIR, "<name>")
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)          # flat imports inside the inner package
# Ensure venv site-packages are reachable regardless of Hermes load context
try:
    _site = sysconfig.get_path("purelib")
    if _site and os.path.isdir(_site) and _site not in sys.path:
        sys.path.insert(1, _site)
except Exception:
    pass
_spec = _ilu.spec_from_file_location(
    "_<name>_inner",
    os.path.join(_PKG_DIR, "__init__.py"),
    submodule_search_locations=[_PKG_DIR],
)
_inner = _ilu.module_from_spec(_spec)
sys.modules["_<name>_inner"] = _inner
_spec.loader.exec_module(_inner)
register = _inner.register
# ... re-export whatever the plugin surface needs
```

**Pitfall — wrong `No module named` error after the circular-import fix:** if the error changes from `No module named '<plugin>'` to `No module named '<dep>'` (e.g. `nacl`, `zeroconf`), the wrapper loaded but the inner package's third-party dependencies are missing from Hermes's runtime venv. Identify the correct venv first (see *Hermes runtime venv discovery* below) and install there — NOT into `hermes-agent/venv`.

Verify the fix using the **runtime Python** (see venv discovery below):
```bash
RUNPY="<path-from-discovery-below>"
cd "$LOCALAPPDATA/hermes/plugins"
"$RUNPY" -c "import sys; sys.path.insert(0, '.'); import <name>; print('OK:', <name>.register)"
```

**Plugin reload is per-turn — no Hermes restart needed.** Plugins are re-discovered at the start of every conversation turn. Fix the file, then send any message; the next turn's plugin-discovery log will confirm success.

### `credential pool: no available entries (all exhausted or empty)` in logs

This is **INFO-level noise, not an error.** It fires every turn when no secondary credential pool is configured — meaning you're running your primary API key only, with no pool of backup keys for automatic failover. If you're not using multi-key credential sharing, ignore it completely.

### Langfuse tracing: `SDK unavailable` / plugin import hangs

**`Langfuse plugin is enabled but the langfuse SDK is unavailable`** — package not installed in the Hermes runtime venv. Find the correct Python first (see *Hermes runtime venv discovery* below), then install:
```bash
uv pip install --python "<RUNPY>" langfuse
```

**After installing, do NOT verify with `import langfuse`** — the SDK fires startup telemetry on import and hangs indefinitely in a non-interactive shell. Use `find_spec` instead:
```bash
"$RUNPY" -c "import importlib.util; print(importlib.util.find_spec('langfuse').origin)"
```

Hermes's langfuse plugin guards its own import — the agent won't hang. The bare shell import test is what hangs.

### ALL tool calls fail with "Gateway policy rejected config" / "Refusing to write" / hang on first call after a config edit

The gateway **re-validates `config.yaml` on every tool call** as a policy gate. A duplicate top-level key (e.g. two `time:` blocks after merging an MCP server entry) is parsed as a fatal YAML error, and the validator returns failure BEFORE dispatching the tool — so `write_file` outside Hermes, `browser_exec`, `react_to_message`, `terminal`, and `execute_code` all fail with cryptic refusal messages, even though the failure has nothing to do with the tool being called or the path being written.

**Symptoms to recognize this:**
- `patch` and `write_file` both refuse the same path that was just edited
- `execute_code` returns "while constructing a mapping" / "expected a single mapping" YAML errors even when reading unrelated files
- `terminal` returns blank output or "policy rejected" instead of the command
- `browser_exec` and `react_to_message` time out
- The pattern: the failure started immediately after a config edit (adding/removing an MCP server, tweaking a secret mapping, etc.)

**Diagnostic (no Hermes tool calls needed — Hermes can't run its own tools while the gateway is wedged):**
```bash
python -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('OK' if d else 'EMPTY')" \
  "$LOCALAPPDATA/hermes/config.yaml"
```
On Windows: `C:\Users\KING\AppData\Local\hermes\config.yaml`. If this throws a `ConstructorError` / "while constructing a mapping" / "expected a single document" with line numbers, that's the bug.

**Fix (outside Hermes):**
1. Open the file in any text editor that shows line numbers (VS Code, Notepad++).
2. Find the duplicate block by line number from the YAML error.
3. Delete one of the two copies (keep the one that matches the surrounding context).
4. Save. Do NOT need to restart Hermes — the validator picks up the corrected file on the next call.
5. Verify the same Python parse runs clean, then re-try the original failing tool.

**Why this happens during MCP server registration:** when a server block is appended to `mcp_servers:` via `hermes config set` or an in-place YAML edit, the new block's fields (command, args, env, time, …) can collide with an existing top-level key. The pattern that bit hardest was two `time:` keys — one for a timer field inside the new server block, one for the top-level `[time]` MCP server. Reordering or carefully matching indentation prevents it.

**Same trap class — duplicate keys inside `secrets.onepassword.env`:** a duplicate env-var name in this map also crashes the validator. When adding a new `op://` mapping, search the block for the same env-var name first; do not assume `hermes config set` will deduplicate (it appends).

### Platform-specific issues
- **Discord bot silent**: Must enable **Message Content Intent** in Bot → Privileged Gateway Intents.
- **Slack bot only works in DMs**: Must subscribe to `message.channels` event. Without it, the bot ignores public channels.
- **Windows-specific issues** (`Alt+Enter` newline, WinError 10106, UTF-8 BOM config, line endings): see `references/windows-quirks.md`.

### Auxiliary models not working
If `auxiliary` tasks (vision, compression, session_search) fail silently, the `auto` provider can't find a backend. Either set `OPENROUTER_API_KEY` or `GOOGLE_API_KEY`, or explicitly configure each auxiliary task's provider:
```bash
hermes config set auxiliary.vision.provider <your_provider>
hermes config set auxiliary.vision.model <model_name>
```

### "Reset permissions" / auto-approving everything
See `references/security-privacy.md` — wipe the "Always allow" stores, don't touch yolo mode.

