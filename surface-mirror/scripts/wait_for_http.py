"""
wait_for_http.py - block until an HTTP endpoint answers 200, then exit 0.

Why this exists instead of a sleep loop in the .cmd launchers
------------------------------------------------------------
The launchers used `timeout.exe /t 2 /nobreak >nul` between probes. Two
things make that wrong:

  * `timeout.exe` REFUSES to run when stdin is redirected - it prints
    "ERROR: Input redirection is not supported, exiting the process
    immediately." and returns in ~0.1s. A launcher driven by an agent
    tool, CI, or any non-console caller has redirected stdin, so the
    wait collapsed to nothing.
  * The launcher's budget was therefore fiction. A loop of 90 iterations
    that sleep 0.1s each gives up after ~14 seconds while the script
    claims to wait 180.

This helper does the waiting in Python: it is portable, it works with
redirected stdin, it costs one interpreter start (~30ms), and the
deadline it reports is the deadline it keeps.

Usage:  wait_for_http.py <url> [deadline_seconds] [interval_seconds]
Exit:   0 when the endpoint answered 200, 1 on timeout.
"""
from __future__ import annotations

import sys
import time
import urllib.request


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    url = argv[0]
    deadline = float(argv[1]) if len(argv) > 1 else 180.0
    interval = float(argv[2]) if len(argv) > 2 else 2.0
    end = time.time() + deadline
    attempts = 0
    while True:
        attempts += 1
        try:
            with urllib.request.urlopen(url, timeout=max(interval, 2.0)) as r:
                if r.status == 200:
                    print(f"up after {attempts} attempt(s): {url}")
                    return 0
        except Exception:  # noqa: BLE001 - any failure means "not up yet"
            pass
        if time.time() >= end:
            print(f"timed out after {deadline:.0f}s ({attempts} attempts): {url}",
                  file=sys.stderr)
            return 1
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
