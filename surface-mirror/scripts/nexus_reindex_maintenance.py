#!/usr/bin/env python
"""Nightly vector-index rebuild for NEXUS CORE, with the service restored after.

Why this exists
---------------
On 2026-10-27 the vector index had to be rebuilt, and the rebuild was
started by hand in the middle of the working day. Three things went
wrong, and all three are the reason this script exists:

1. The rebuild and the server deadlocked. The server holds
   chroma.sqlite3 open for its lifetime; the rebuild writes to it. The
   rebuild blocked on the server's connection and the server's reads
   blocked on the rebuild's transaction. The knowledge base was offline
   for the better part of two hours.

2. Nothing stopped the health job from starting the server in the
   middle of the rebuild, and the five-minute watchdog did exactly
   that. The lock file is the guard, but the guard has to be somewhere
   the rebuild controls the timing of - which means the rebuild has to
   own the window, not borrow one from a working day.

3. The rebuild was started more than once. The first run was killed
   part way through and, because the old script dropped the collection
   before it began, all of its work was thrown away. The script is now
   resumable, so this is survivable - but a rebuild that runs once, on
   a schedule, in a window where nobody needs the brain, is the right
   answer rather than the resilient one.

What this does
--------------
Stops the service, rebuilds the index, and starts the service again -
in that order, with the service restored whether the rebuild succeeds,
fails, or is interrupted. The service comes back. That is the promise.

The rebuild itself takes the lock and releases it when it finishes, so
a crash cannot leave the service permanently unable to start.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERMES = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes"
NEXUS_PROJECT = Path(r"E:\ultron-memory\nexus-core")
NEXUS_VENV = Path(r"C:\Users\KING\.cache\nexus-venv\Scripts\python.exe")
SERVICE_CONTROL = HERMES / "scripts" / "service_control.py"
LAUNCHER = HERMES / "scripts" / "start_nexus.cmd"
MARKER = "run_nexus.py"
PORT = 8650
LOG = HERMES / "logs" / "nexus_reindex_maintenance.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def run(args: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            cwd=str(NEXUS_PROJECT) if "reindex" in " ".join(args) else None,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


def stop_service() -> None:
    rc, out = run([str(NEXUS_VENV), str(SERVICE_CONTROL), "stop",
                   "--marker", MARKER, "--port", str(PORT)], timeout=120)
    log(f"stop: rc={rc}")
    for line in out.strip().splitlines()[-6:]:
        log(f"  {line}")


def start_service() -> None:
    rc, out = run([str(NEXUS_VENV), str(SERVICE_CONTROL), "start",
                   "--marker", MARKER, "--port", str(PORT),
                   "--launcher", str(LAUNCHER)], timeout=300)
    log(f"start: rc={rc}")
    for line in out.strip().splitlines()[-6:]:
        log(f"  {line}")


def wait_for_health(timeout_s: int = 180) -> bool:
    import urllib.request
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main() -> int:
    log("=== vector index rebuild: starting ===")
    # The server must be DOWN before the rebuild touches the collection.
    # Starting it afterwards is handled in the finally, so a failed
    # rebuild still leaves the estate serving.
    stop_service()
    rc = 1
    try:
        log("rebuild: running the RESILIENT rebuild wrapper (fresh, resumable)")
        # The wrapper, not the tool directly, because a rebuild on this
        # host is an event rather than an exception - it was killed
        # three times on 2026-10-27. The wrapper takes the lock ONCE
        # and holds it across every pass, so the five-minute health
        # job cannot start the server onto a half-built index, and it
        # RESUMES rather than starting over: the first pass is fresh
        # (the chunking policy changed, so an incremental run would
        # leave a mixture of two chunking regimes) and every pass after
        # that keeps the work it completed.
        #
        # --fresh is spelled twice on purpose: dropping the index is
        # destructive and has to be asked for explicitly.
        wrapper = HERMES / "scripts" / "nexus_reindex_resilient.cmd"
        rc, out = run(["cmd", "/c", str(wrapper), "12", "fresh"], timeout=60 * 150)
        for line in out.strip().splitlines()[-25:]:
            log(f"  {line}")
        log(f"rebuild: rc={rc}")
    finally:
        # THE PROMISE: the service comes back. Whatever happened above.
        log("restoring the service")
        start_service()
        if wait_for_health():
            log("health: OK")
        else:
            log("health: NOT OK - the service did not answer within 180s")
            rc = rc or 1
    log(f"=== vector index rebuild: done (rc={rc}) ===")
    return rc


if __name__ == "__main__":
    sys.exit(main())
