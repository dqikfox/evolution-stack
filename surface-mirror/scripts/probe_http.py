"""
Minimal HTTP health probe for the service launchers.

Exit 0 when the URL answers 200, 1 otherwise.

Why this exists: the launchers used to probe health with
`Invoke-WebRequest`, which costs 1-3s of PowerShell process startup on a
loaded host - that startup time is charged to the launcher's wait budget, so
a busy machine could time out waiting for a server that was already up.
`curl` in a pipeline is no better: on Windows it can fail with "Input
redirection is not supported". A stdlib urllib call in an interpreter that
is already warm answers in tens of milliseconds and behaves the same
everywhere.

Usage:  python probe_http.py <url> [timeout_seconds] [--contains TEXT]

--contains TEXT additionally requires TEXT to appear in the response body.
A launcher that probes before it reclaims needs that: "something answered
200 on this port" is not the same claim as "MY service answered". The
substring is checked against the first 64 KiB of the body, which is where
a service's identity marker lives.
"""
import sys
import urllib.error
import urllib.request

BODY_LIMIT = 65536


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a not in ("--contains",)]
    contains = None
    if "--contains" in argv:
        idx = argv.index("--contains")
        if idx + 1 >= len(argv):
            print("probe_http.py: --contains needs a value", file=sys.stderr)
            return 2
        contains = argv[idx + 1]
        args = [a for i, a in enumerate(argv[1:], start=1) if i not in (idx, idx + 1)]
    if not args:
        print("usage: probe_http.py <url> [timeout] [--contains TEXT]", file=sys.stderr)
        return 2
    url = args[0]
    timeout = float(args[1]) if len(args) > 1 else 3.0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return 1
            if contains is None:
                return 0
            body = resp.read(BODY_LIMIT)
            if isinstance(body, bytes):
                body = body.decode("utf-8", "replace")
            return 0 if contains in body else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
