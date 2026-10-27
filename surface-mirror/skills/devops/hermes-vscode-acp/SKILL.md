---
name: hermes-vscode-acp
description: Use when wiring VS Code to Hermes via ACP.
type: skill
version: 1.0.0
author: THRONE
license: private
metadata:
  hermes:
    tags: [vscode, acp, hermes, editor, plugins, mcp]
    related_skills: [hermes-agent, hermes-startup-automation, memory-graph-ops]
---

# Hermes in VS Code (ACP)

## When to Use
- The user asks to set up Visual Studio Code for Hermes, or to make Hermes
  Agent Desktop open files in VS Code.
- The Hermes sidebar in VS Code loads but never becomes usable, or a new
  session hangs with no output.
- Deciding which toolsets and MCP servers an editor-side Hermes session
  should get.

## The shape of the integration

VS Code does not embed Hermes. It spawns the Hermes CLI over the **ACP
protocol** (Agent Client Protocol) on stdio, and the extension talks to it
with JSON-RPC.

| Piece | Where | Value |
|---|---|---|
| Editor | `C:\Users\KING\AppData\Local\Programs\Microsoft VS Code\Code.exe` | `code` is on PATH |
| Extension | `eyanlin.hermes-agent-vscode` | the official one; `formulahendry.acp-client` is the generic fallback |
| Agent | `C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe` | **absolute path required** |
| Settings | `C:\Users\KING\AppData\Roaming\Code\User\settings.json` | user scope |

**Use the absolute `hermes.exe`.** The Hermes venv's `Scripts` directory is
not on the user PATH, so the extension's shipped default of a bare
`hermes` resolves to nothing and the sidebar silently falls back to a
local mock ("Agent backend not connected").

### The settings the extension actually reads

The extension declares **flat, dotted** property names
(`hermesAgent.command`), NOT a nested `hermesAgent` object. A settings
file that writes

```json
"hermesAgent": { "command": "..." }
```

is silently ignored, and a check like `'hermesAgent' in settings` reports
False on a file that is perfectly correct. Read `hermesAgent.command`.

```
hermesAgent.command                  absolute path to hermes.exe
hermesAgent.useAcp                   true
hermesAgent.model                    the estate's configured default model label
hermesAgent.defaultMode              "Auto" | "Manual"
hermesAgent.permissionReminderMinutes 5
hermesAgent.nodePath                 standalone node.exe, for the background host
acp.agents."Hermes Agent".command    same absolute path
acp.agents."Hermes Agent".args       ["acp"]
```

The extension spawns `hermes acp` with `shell: true` and
`HERMES_ACCEPT_HOOKS=1`.

### Other pieces

- `EDITOR` and `VISUAL` are set to `code --wait` (user scope), so callers
  that wait for the editor to exit behave.
- Per-user file associations bind source and text types to VS Code, because
  Hermes Desktop opens artifacts through the OS, not through an internal
  editor selector.
- Regenerate the settings with a script that preserves the user's existing
  keys. Do not hand-edit: the file holds the user's High Contrast theme
  and GitLens settings, and a wholesale replace loses them.

### The settings generator must MERGE, not overwrite

Writing a fixed key set to `settings.json` silently drops every key that
VS Code or an extension added — the Azure extension's
`@azure.argTenant`, the native chat's `chat.byokUtilityModelDefault`, a
language-specific formatter, whatever the Copilot extension writes on
activation. The user finds out days later when a setting has reverted
and nothing explains it.

Merge semantics that hold up:

- a key the generator manages keeps the managed value
- a key the generator does not manage is preserved verbatim
- for a managed object (`acp.agents`, `[python]`, ...) the managed
  sub-keys win and any extra sub-key is kept
- write a timestamped backup on EVERY run, not a fixed filename that is
  only ever written once

### Recovering a clobbered settings.json

VS Code keeps **Local History** for any file that was open in an editor:
`%APPDATA%\Code\User\History\<hash>\<id>.json`, with `entries.json` in
the same directory mapping each id to its timestamp and source. After a
bad write, enumerate every version, count the keys in each, and diff
them against the live file. That is how the two dropped keys above were
recovered after a fixed-key-set generator had already removed them.

## Pitfall — the plugin loader can deadlock every ACP session

**Final working config on this estate: `plugins.load_timeout_seconds: 10`,
with `obsidian-context-bridge` and `langfuse` removed from
`plugins.enabled`.** Do NOT set the timeout to 0 — see the correction
below.

### The mechanism

`model_tools.py` calls `discover_plugins()` at MODULE LEVEL, inside a
`try/except`. So importing `model_tools` triggers a full plugin
discovery.

With the default `plugins.load_timeout_seconds: 10`, each plugin's
import + `register()` runs on a DEADLINE WORKER THREAD
(`plugins_loader.run_with_load_deadline`). A plugin that imports
`model_tools` therefore triggers a discovery from that worker, which
calls `discover_and_load()` and tries to take the sweep's
`_discovery_lock` — an RLock HELD BY THE SWEEP on another thread. The
worker blocks; the sweep is waiting for the worker; ABBA deadlock.
Upstream's guard (`if self._discovered and not force and
in_plugin_load_worker(): return`) does not fire, because the re-entrant
call arrives on a thread that is not the plugin's own deadline worker.

`load_timeout_seconds: 0` runs the load inline on the sweep thread
itself. The re-entrant `discover_and_load()` then re-acquires the RLock
on the SAME thread, which succeeds, sees `_discovered` already true, and
returns. No deadlock. The session then builds in ~20s.

**Disabling the two proven offenders IS the fix, and it is cheap.**
`obsidian-context-bridge` and `langfuse` are the two plugins that
reproduced the deadlock on this estate. `langfuse` additionally imports
numpy, whose lazy Windows `_core` initialisation can deadlock when it
first runs off the main thread (upstream `plugins/memory/__init__.py`
references issue #58083). Removing both — and nothing else — plus
`plugins.load_timeout_seconds: 10` gives a reliable `session/new` in
20-40s.

**Do NOT set `plugins.load_timeout_seconds: 0`.** It was tried and it
"works", but only because inline loading hides the re-entrant discovery
race; the numpy off-main-thread cycle and the provider-resolution
problems it exposes are still there, and it leaves the estate with a
misleading knob value. 10 plus the two exclusions is the configuration
that was actually verified end to end.

**Do NOT disable every plugin that imports `model_tools`.** Only the two
above were proven to trigger the deadlock here. Disabling the rest costs
real capability for no measured benefit.

**Do not patch the upstream checkout in place.** `hermes-agent` tracks
upstream directly, not an estate fork. The config-level fix is correct
and survives an upstream pull.

### Diagnosing it, do not guessing

`uv tool install py-spy`, then `py-spy dump --pid <pid>`.

Two things to get right:
- The ACP server is the GRANDCHILD. `hermes_bootstrap.py` relaunches a
  child (`subprocess.call`), which runs the real server. Dump the
  grandchild, not the launcher — the launcher always shows
  `subprocess.call` and looks like the blocker.
- A healthy process shows threads blocked at
  `hermes_cli/plugins.py:1289` (`with self._discovery_lock`) while the
  sweep sits in `run_with_load_deadline`. That is the deadlock.

Confirm the theory with `HERMES_SAFE_MODE=1` (skips plugin discovery
entirely): if `session/new` answers in seconds, the plugin loader is the
cause.

`session/new` never answering is the symptom. The child is alive, the
event loop is idle, and the logs go silent after the plugin phase.

## Pitfall — one dead MCP server stalls every session

An ACP session builds its tool surface at `session/new` and connects
**every** globally enabled MCP server. The connections run in parallel
(`asyncio.gather`), so the wall-clock cost is the SLOWEST server's
timeout, not the sum.

Three of this estate's servers never answer:

| Server | Why |
|---|---|
| `thinking` | `uvx` - TimeoutError |
| `ibm-watsonx` | `uvx` - TimeoutError, and `uvx` installs 95 packages first |
| `unreal-engine` | http on 127.0.0.1:8000, nothing is listening |

`platform_toolsets.<platform>` accepts a list of toolset names, and **MCP
server names in that list act as an allowlist**
(`hermes_cli/tools_config.py::_merge_mcp_servers`: "listed names form an
allowlist, else every globally enabled server"). The `no_mcp` sentinel
disables all of them.

`platform_toolsets.acp` is set to the same 14 toolsets as the CLI plus the
21 servers that actually answer. The three dead ones are excluded. An
explicit list REPLACES the platform composite, so the toolset half must
be spelled out or the agent loses terminal, file and skills.

**"enabled" is not "working."** `hermes mcp list` shows a server as
enabled from config alone. Use `scripts/mcp_doctor.py` to find the ones
that are configured but DEAD, and `scripts/mcp_call.py <server> <tool>`
to prove one answers.

## Verifying the wiring end to end

Do not stop at "the settings look right". Drive the ACP session the way
the extension does: read the command from `settings.json`, spawn it with
`shell: true` and `HERMES_ACCEPT_HOOKS=1`, then `initialize`,
`session/new`, and a real `session/prompt`.

Expect roughly: `initialize` at 10-20s, `session/new` at 20-40s, a prompt
answer after that. A healthy run prints `VSCODE_WIRING PASS`.

Two things to get right in the harness:
- Read `hermesAgent.command` (dotted), not `hermesAgent["command"]`.
- Send the request ONLY after the previous response arrives, and give
  `session/new` a large budget (300s+): the agent construction is slow
  and silent, and an impatient harness reports a hang that is really a
  slow success.

## Pitfall — the extension is installed but never appears in the UI

Installing the extension is not the same as it running. Three separate
things can keep the Hermes Agent icon out of the activity bar while the
extension sits in the Extensions list, enabled, with a green tick.

### 1. The view container is pinned but hidden

The activity-bar container is recorded in the profile state database
(`%APPDATA%\Code\User\globalStorage\state.vscdb`, ItemTable key
`workbench.activity.pinnedViewlets2`). An entry like

```json
{"id": "workbench.view.extension.hermesAgent", "pinned": true, "visible": false}
```

means the container is pinned but the icon is hidden — the extension
never activates, and the Extensions view still lists it as installed and
enabled. VS Code 1.143's CLI has **no** `--enable-extension` and no
"reset activity bar" command, so edit the database directly:

1. Close VS Code (it rewrites the state database on shutdown and would
   overwrite the change).
2. `UPDATE ItemTable SET value=? WHERE key='workbench.activity.pinnedViewlets2'`
   with `visible: true` on that entry.
3. Relaunch.

### 2. Workspace Trust silently disables it

The official extension declares no `capabilities.untrustedWorkspaces`, so
VS Code disables it in an untrusted workspace — the window shows a
Restricted Mode banner and the icon never appears. Trust the folders:

```json
"security.workspace.trust.enabled": true,
"security.workspace.trust.trustedFolders": ["E:\\ultron-memory", "..."]
```

Trust is **not** inherited from a parent folder: listing
`E:\ultron-memory` does not trust `E:\ultron-memory\nexus-core`. List
every folder you actually open.

### 3. The extension never scanned

Confirm the extension is even in the scan. `code --list-extensions` must
show it, and the activity-bar `TabItem` must exist in the accessibility
tree with the label `Hermes Agent`. If the AX tree has no such TabItem,
the extension was never loaded — suspect a profile mismatch, a manifest
that fails to parse, or a missing `main` entry.

Also check the extension actually installed: a batch `code
--install-extension` run can hang and silently skip one. `ms-python.
vscode-pylance` was missing this way. Verify with `code
--list-extensions | wc -l` and compare against the requested set.

## Proving it in the real UI

The ACP harness proves the protocol. It does not prove the extension
renders. Confirm both:

- The accessibility tree contains `TabItem 'Hermes Agent'`.
- The panel shows a session with a real prompt and a real reply, and the
  model selector shows the configured model.

A screenshot of a completed turn is the artifact that settles it. The
agent should be able to run tools in the workspace from the VS Code
panel (e.g. `git status`) and report the result — that is end to end
through VS Code, not just through a protocol harness.

Note: a nonsense or truncated prompt makes the agent improvise, and it
will happily reconfigure the open repository. Review any file it wrote
before committing, and never let it near the user's curated settings
file.

## Other traps hit while doing this

- **The Hermes venv is not on PATH.** Use the absolute `hermes.exe`.
- **`session/new` is a blocking agent construction.** `acp_adapter`
  runs it in a thread (`asyncio.to_thread`) because it is slow and fully
  blocking; that is expected, not a hang.
- **A plugin load can time out at 10s** (`plugins.load_timeout_seconds`)
  without failing the session. `langfuse` does this on every start.
  Lowering the timeout does not help a true deadlock.
- **PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM.** It
  corrupts JSONL and JSON files in place. Use Python to write them.
- **A `cmd.exe /c mklink` with a quoted path** fails with "The filename,
  directory name, or volume label syntax is incorrect."
- **An MSYS symlink is a POSIX path.** `ln -s /e/... ` creates a link
  Windows Node cannot resolve; the target process dies at startup with
  "Connection closed". See `memory-graph-ops` for the instance of this
  that broke the memory MCP server.
- **Hermes Desktop opens files through the OS, not through an internal
  editor picker.** `shell.openPath` and the "reveal in file manager"
  action both go to the Windows default handler, so binding the file
  types per-user to VS Code is what actually moves the Desktop onto
  VS Code. The CLI's `/prompt` compose path uses `$VISUAL`/`$EDITOR`.
- **Desktop UI automation can be lossy.** When driving VS Code by
  synthetic input, modifier chords may not register and coordinate
  clicks may be rejected. Do not conclude a feature is broken from a
  failed synthetic click — re-verify against logs, the accessibility
  tree, or the protocol harness.
