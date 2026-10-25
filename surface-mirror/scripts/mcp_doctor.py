#!/usr/bin/env python
"""mcp_doctor.py - prove every configured MCP server actually connects.

`hermes mcp list` says a server is "enabled". It does not say it starts.
Six servers in this tree were enabled and dead at the same time, and the
symptom was a retry storm in mcp-stderr.log (47,739 attempts for one
server) rather than an error anyone was reading.

This does what the list command cannot: it spawns each server exactly as
Hermes does - same interpreter, same env - performs the MCP initialize
handshake, and lists the tools it actually exposes. A server that cannot
complete the handshake is reported as DEAD, with the reason.

Usage:
    python mcp_doctor.py                    # every enabled stdio server
    python mcp_doctor.py --server throne    # one server
    python mcp_doctor.py --timeout 60

Exit codes:
    0  every enabled server connected
    1  at least one server failed
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
    if not CONFIG.exists():
        print(f"config not found: {CONFIG}", file=sys.stderr)
        return {}
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8", errors="ignore")) or {}
    servers = data.get("mcp_servers") or {}
    return {k: v for k, v in servers.items() if isinstance(v, dict)}


def enabled(cfg: dict) -> bool:
    return bool(cfg.get("enabled", True))


async def probe(name: str, cfg: dict, timeout: int) -> dict:
    command = cfg.get("command")
    args = [str(a) for a in (cfg.get("args") or [])]
    env = dict(os.environ)
    for k, v in (cfg.get("env") or {}).items():
        if v is None:
            continue
        env[str(k)] = str(v)
    if not command:
        # An http/oauth server has no stdio transport to probe. It is not
        # dead - it is simply not testable this way, and calling it DEAD
        # would be a lie.
        url = cfg.get("url") or "?"
        return {"name": name, "ok": None, "reason": f"http server ({url}) - not stdio-testable"}
    params = StdioServerParameters(command=str(command), args=args, env=env)
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await asyncio.wait_for(s.initialize(), timeout=timeout)
                tools = await asyncio.wait_for(s.list_tools(), timeout=timeout)
                info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
                return {
                    "name": name,
                    "ok": True,
                    "server": getattr(info, "name", "?") if info else "?",
                    "count": len(tools.tools),
                    "tools": [t.name for t in tools.tools],
                }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        cur = e
        while getattr(cur, "exceptions", None):
            cur = cur.exceptions[0]
            reason = f"{type(cur).__name__}: {cur}"
        return {"name": name, "ok": False, "reason": reason[:300]}


async def main_async(names: list[str], timeout: int) -> int:
    servers = load_servers()
    if not servers:
        print("no MCP servers configured")
        return 2
    targets = [n for n in servers if (not names or n in names)]
    if names:
        missing = [n for n in names if n not in servers]
        for m in missing:
            print(f"  {m:<18} NOT IN CONFIG")
        if missing:
            return 2
    results = []
    for name in targets:
        cfg = servers[name]
        if not enabled(cfg):
            results.append({"name": name, "ok": None, "reason": "disabled"})
            continue
        results.append(await probe(name, cfg, timeout))
    print(f"{'server':<18} {'status':<8} {'tools':<7} detail")
    print("-" * 88)
    dead = 0
    for r in results:
        if r.get("ok") is True:
            print(f"  {r['name']:<16} {'LIVE':<8} {r.get('count', 0):<7} {r.get('server', '')}")
        elif r.get("ok") is None:
            tag = "disabled" if r.get("reason") == "disabled" else "http"
            print(f"  {r['name']:<16} {tag:<8} {'-':<7} {r.get('reason', '')}")
        else:
            dead += 1
            print(f"  {r['name']:<16} {'DEAD':<8} {'-':<7} {r.get('reason', '')[:80]}")
    live = sum(1 for r in results if r.get("ok") is True)
    total_tools = sum(r.get("count", 0) for r in results if r.get("ok") is True)
    print("-" * 88)
    n_disabled = sum(1 for r in results if r.get("ok") is None and r.get("reason") == "disabled")
    n_http = sum(1 for r in results if r.get("ok") is None and r.get("reason") != "disabled")
    print(f"  {live} live, {dead} dead, {n_disabled} disabled, {n_http} http, "
          f"{total_tools} tools exposed")
    return 1 if dead else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", action="append", default=[], help="check only this server")
    ap.add_argument("--timeout", type=int, default=45)
    a = ap.parse_args()
    return asyncio.run(main_async(a.server, a.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
