#!/usr/bin/env python
"""mcp_call.py - call any tool on any configured MCP server from the CLI.

The desktop loads its MCP tool catalog when a session starts, so a server
that was fixed mid-session stays invisible until the next one. This calls
the tool directly over the same stdio transport Hermes uses, which both
proves the server works and gives immediate access to its tools.

Usage:
    python mcp_call.py --list throne
    python mcp_call.py throne health
    python mcp_call.py throne port_check '{"host": "127.0.0.1", "port": 8705}'

Exit codes:
    0  the call succeeded
    1  the call failed (the server's own error is printed)
    2  bad usage
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("mcp is not installed in this interpreter: pip install mcp", file=sys.stderr)
    raise SystemExit(2)

HERMES_HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes"
CONFIG = HERMES_HOME / "config.yaml"


def load_servers() -> dict:
    import yaml
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8", errors="ignore")) or {}
    return {k: v for k, v in (data.get("mcp_servers") or {}).items() if isinstance(v, dict)}


def build_env(cfg: dict) -> dict:
    env = dict(os.environ)
    for k, v in (cfg.get("env") or {}).items():
        if v is not None:
            env[str(k)] = str(v)
    return env


async def run(server: str, tool: str | None, args: dict, timeout: int) -> int:
    servers = load_servers()
    if server not in servers:
        print(f"unknown server '{server}'. known: {', '.join(sorted(servers))}", file=sys.stderr)
        return 2
    cfg = servers[server]
    if not cfg.get("command"):
        print(f"'{server}' is an http/oauth server - it has no stdio transport to call", file=sys.stderr)
        return 2
    params = StdioServerParameters(
        command=str(cfg["command"]),
        args=[str(a) for a in (cfg.get("args") or [])],
        env=build_env(cfg),
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), timeout=timeout)
            if tool is None:
                tools = await asyncio.wait_for(s.list_tools(), timeout=timeout)
                print(f"{server}: {len(tools.tools)} tools")
                for t in tools.tools:
                    desc = (t.description or "").splitlines()
                    first = desc[0][:96] if desc else ""
                    print(f"  {t.name:<22} {first}")
                    # the python SDK is snake_case; the wire format is camelCase
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                    props = schema.get("properties") or {}
                    if props:
                        print(f"  {'':<22} args: {', '.join(props.keys())[:110]}")
                return 0
            try:
                res = await asyncio.wait_for(s.call_tool(tool, args), timeout=timeout)
            except Exception as e:
                print(f"call failed: {type(e).__name__}: {e}", file=sys.stderr)
                return 1
            out = []
            for c in getattr(res, "content", []) or []:
                out.append(getattr(c, "text", str(c)))
            text = "\n".join(out) if out else ""
            if not text:
                sc = getattr(res, "structuredContent", None)
                text = json.dumps(sc, indent=2) if sc else "(empty response)"
            print(text)
            if getattr(res, "isError", False):
                return 1
            return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("server")
    ap.add_argument("tool", nargs="?")
    ap.add_argument("args", nargs="?", default="{}")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    try:
        args = json.loads(a.args) if a.tool else {}
    except json.JSONDecodeError as e:
        print(f"args must be JSON: {e}", file=sys.stderr)
        return 2
    return asyncio.run(run(a.server, a.tool, args, a.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
