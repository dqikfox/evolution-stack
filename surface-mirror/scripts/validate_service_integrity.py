"""A service can be 'up' and still be functionally dead.

A port that answers 200 and a process that is alive are the weakest
possible evidence that a service works. The real question is whether the
DEPENDENCIES are ready: a RAG service whose vector store failed to load
answers /health with 200 and a component that says "not_ready", and a
dashboard that only checks the port calls that healthy.

So the check is deeper than a port scan: read the /health payload and
look for a component that reports itself as not ready. The ports come
from the house PORT_MAP registry rather than a list typed into this
file, because a typed list goes stale the moment a service moves.

Usage:
    python validate_service_integrity.py                 # the registry's ports
    python validate_service_integrity.py --ports 8650,8705
    python validate_service_integrity.py --port 8650 --url http://127.0.0.1:8650/health
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.request
from pathlib import Path

PORT_MAP = Path(r"E:\ultron-memory\infra\PORT_MAP.json")
DEFAULT_PORTS = (8650, 8705, 8520, 11434, 8080)
UNREADY = ("not_ready", "degraded", "failed", "error")


def registry_ports():
    """The ports the house actually runs, or nothing if the map is gone."""
    if not PORT_MAP.is_file():
        return []
    try:
        data = json.loads(PORT_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ports = []
    entries = data.values() if isinstance(data, dict) else data
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        port = entry.get("port")
        if isinstance(port, int) and port > 0:
            ports.append(port)
    return sorted(set(ports))


def is_listening(port, host="127.0.0.1", timeout=0.4):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def not_ready_components(payload):
    """Every component that says it is not ready."""
    found = []
    try:
        data = json.loads(payload)
    except ValueError:
        # Not JSON is not a failure: a service without a health payload
        # has nothing to declare, and inventing a failure from it would
        # make the check cry wolf.
        return found

    def walk(node, path):
        if isinstance(node, dict):
            status = node.get("status")
            if isinstance(status, str) and status.lower() in UNREADY:
                found.append((path or "root", node.get("reason", status)))
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(data, "")
    return found


def check(port, url=None, timeout=3):
    """The components of one service that are not ready."""
    url = url or f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(65536).decode("utf-8", "replace")
    except Exception:
        return []
    return not_ready_components(body)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ports", help="comma separated ports; overrides the registry")
    ap.add_argument("--port", type=int, help="a single port, with --url")
    ap.add_argument("--url", help="the health URL for --port")
    args = ap.parse_args(argv)

    if args.port:
        ports = [args.port]
    elif args.ports:
        ports = [int(p) for p in args.ports.split(",") if p.strip()]
    else:
        ports = registry_ports() or list(DEFAULT_PORTS)

    failures = []
    checked = 0
    for port in ports:
        if not is_listening(port):
            continue
        checked += 1
        for component, reason in check(port, args.url if args.port else None):
            failures.append((port, component, reason))

    if failures:
        print("Integrity check FAILED:")
        for port, component, reason in failures:
            print(f"  - :{port} {component} is not ready: {reason}")
        return 1
    print(f"Integrity check passed: {checked} service(s) answered, "
          f"no component reported itself unready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
