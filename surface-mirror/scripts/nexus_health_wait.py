"""Wait for a health endpoint to answer, in the NEXUS interpreter.

A multi-line `python -c "..."` in a batch file is a liability: cmd
mangles the quoting and the line breaks. This helper is a real file, so
the launcher calls it with two plain arguments and the probe is a plain
stdlib urllib call.

Exit 0 when the endpoint answers with a healthy body before the budget
runs out, 1 otherwise.
"""
import sys
import time
import urllib.request

OK_MARKERS = ('"ok"', '"status":"live"', '"status": "live"')


def main(argv):
    url = argv[1]
    budget = float(argv[2]) if len(argv) > 2 else 180.0
    deadline = time.time() + budget
    last = "no attempt"

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read(65536).decode("utf-8", "replace")
            if any(m in body for m in OK_MARKERS):
                print(f"[nexus] healthy: {url}")
                return 0
            last = f"answered, but the body is not healthy: {body[:160]}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(2)

    print(f"[nexus] not healthy within {budget:.0f}s - {last}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
