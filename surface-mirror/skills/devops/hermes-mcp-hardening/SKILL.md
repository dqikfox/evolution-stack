---
name: hermes-mcp-hardening
description: Use when an MCP server will not start or is missing.
---

# Hardening the Hermes MCP surface

## The rule that matters

**"Enabled" is not "connected."** `hermes mcp list` reports what the config
says. It never proves a server starts. A server can be enabled for
months, fail on every spawn, and nobody notices because the failure lands
in a log nobody reads. On this host, six of twenty-two servers were dead
at once and one of them had **47,739 failed start attempts** in
`logs/mcp-stderr.log`.

Prove it with a handshake:

```
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
    C:/Users/KING/AppData/Local/hermes/scripts/mcp_doctor.py
```

`mcp_doctor.py` spawns each server exactly as Hermes does, performs the
MCP `initialize` handshake and lists the tools it really exposes. It
prints `LIVE` / `DEAD` / `disabled` / `http` per server and exits 1 if
anything is dead. An http/oauth server has no stdio transport, so it is
reported as `http`, **never as dead** - calling it dead would be a lie.

To reach a tool on a server that was fixed mid-session (the desktop only
rebuilds its tool catalog at session start):

```
...venv/Scripts/python.exe .../scripts/mcp_call.py throne tailnet_peers
...venv/Scripts/python.exe .../scripts/mcp_call.py throne port_check '{"host":"127.0.0.1","port":8705}'
```

## The four ways an MCP server dies

1. **Wrong interpreter.** A stdio server must use
   `command: C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`.
   Bare `python` resolves to a uv interpreter that has no
   `mcp.server.mcpserver`, so the server exits with
   `ERROR: pip install mcp` on every spawn. The MCP package being
   importable is not enough - the module path matters.
2. **Bash-style env defaults.** `${VAR}` IS Hermes config syntax and is
   expanded from the environment. `${VAR:-default}` is NOT - Hermes
   passes the literal string through, and the server receives
   `C:/Users/KING/Downloads/media` prefixed with `${YTDLP_OUTPUT:-`,
   which is an invalid path. Put real values in the config.
3. **Pre-MCPServer API.** `server.run(r, w, server.create_initialization_options())`
   raises `AttributeError: 'MCPServer' object has no attribute
   'create_initialization_options'`. The house pattern is
   `server.run("stdio")` (or `await server.run_stdio_async()`).
4. **The package does not exist.** `mcp-server-sequential-thinking` is
   not on PyPI; the package is `sequential-thinking-mcp`, and its console
   script has the same name. A server that needs an interactive OAuth
   login (`globalping`) can never work in an agent - disable it instead
   of letting it warn on every tool load.

## Config hygiene

- A null entry (`some_server:` with no value) crashed `hermes mcp list`
  with `TypeError: argument of type 'NoneType' is not a container`, so
  the list of every *other* server never printed. Fixed in the local
  hermes-agent branch `local/throne-hardening`; the config no longer
  contains a null entry.
- Back up `config.yaml` before editing it, and edit it as **text**, not
  through a yaml round-trip - a round trip rewrites the whole file.
- After editing, re-parse it and print the changed entries. A config
  that parses is not a config that is correct.

## Reading the evidence

- `logs/mcp-stderr.log` holds the spawn attempts. Count them: a high
  count for one server is the signature of a permanent misconfiguration,
  not a transient failure.
- A server's own stdout/stderr is the authority. A config that looks
  right can still point at a path that does not exist.

## The verifier trap

The first version of `mcp_doctor.py` reported **every** server as dead,
including `throne`, which starts perfectly. The bug was in the doctor:
`init.serverInfo` does not exist in the Python SDK (it is
`init.server_info`). Nothing was wrong with the servers.

**Always run a known-good control before believing a negative result.**
If the doctor says everything is broken, test it against a server that
is known to work - if that also fails, the doctor is wrong.

Related: the same class of error made a corpus look clean when it was
not - the redaction had removed the *label* (`[DEEPSEEK_API_KEY]`) and
left the *value*. **The shape is the evidence**, and a negative result
needs a control just as much as a positive one.

## One writer per artifact

`throne_network_inventory.md` had two writers: the discovery, and a
fast tailnet updater that overwrote it with a tailnet-only table, the
wrong column headers, and hardcoded `0` / `2` counts. The updater now
writes its own `tailnet_inventory.md` and the discovery is the only
writer of the inventory.

**When two things write one file, one of them is lying.** Find the
second writer before trusting either output.
