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

Usage:  python probe_http.py <url> [timeout_seconds]
"""
import sys
import urllib.error
import urllib.request


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: probe_http.py <url> [timeout]", file=sys.stderr)
        return 2
    url = argv[1]
    timeout = float(argv[2]) if len(argv) > 2 else 3.0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 0 if resp.status == 200 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
