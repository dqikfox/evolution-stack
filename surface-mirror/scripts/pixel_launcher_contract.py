"""The live contract for the Pixel studio's supervision.

Run it against the running service. It asserts the behaviours the house
depends on, and it ALWAYS leaves the service running.

    python pixel_launcher_contract.py

What it proves:

  1. exactly ONE supervisor chain, and the port owner is inside it
  2. the studio reports its own supervision in /api/state
  3. the lock file names a live owner, and that owner is in the chain
  4. a SECOND supervisor refuses with exit code 3 and does not disturb the
     live one
  5. a CRASH is recovered: kill the studio and it comes back by itself
  6. the launcher is IDEMPOTENT: a healthy service is left alone
  7. a COLD stop frees the port, and a cold start brings it back
  8. the end state is one chain, the port owned by its tree, and healthy

A permanent artifact must not be named test_* or tmp_*: the house
disk-cleanup plugin deletes anything with those prefixes at the end of the
next task, and this file is not disposable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import service_control as sc  # noqa: E402  (the house helper, same directory)

PORT = 8520
MARKER = "pixel_supervisor.py"
PROJECT = Path(r"C:\Users\KING\projects\pixel")
LOCK = PROJECT / "logs" / "supervisor.lock"
LAUNCHER = r"C:\Users\KING\AppData\Local\hermes\scripts\start_pixel.cmd"
PYTHON = r"C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
HEALTH = f"http://127.0.0.1:{PORT}/api/state"

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, description: str) -> bool:
    RESULTS.append((bool(ok), description))
    print(f"  {'PASS' if ok else 'FAIL'}  {description}")
    return bool(ok)


def state() -> dict | None:
    try:
        with urllib.request.urlopen(HEALTH, timeout=5) as response:
            return json.loads(response.read(65536).decode("utf-8", "replace"))
    except Exception:
        return None


def healthy() -> bool:
    payload = state()
    return bool(payload) and "activeCharacter" in payload


def supervisor_pids() -> list[int]:
    return [p["ProcessId"] for p in sc.supervisor_pids(MARKER)]


def chain_roots() -> list[int]:
    sups = sc.supervisor_pids(MARKER)
    ids = {p["ProcessId"] for p in sups}
    return [p["ProcessId"] for p in sups if p["ParentProcessId"] not in ids]


def wait_for(predicate, timeout: float, interval: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def start_via_launcher() -> bool:
    result = subprocess.run([r"C:\Windows\System32\cmd.exe", "/c", LAUNCHER],
                            capture_output=True, text=True, timeout=300)
    return result.returncode == 0


def stop_everything() -> None:
    sc.stop(MARKER, PORT)


def main() -> int:
    print("=== pixel: the live supervision contract ===\n")

    # 1. one chain, the port owned by its tree
    roots = chain_roots()
    listener = sc.listener_pid(PORT)
    chain = sc.chain_of(listener) if listener else []
    chain_ids = {p["ProcessId"] for p in chain}
    check(len(roots) == 1, f"exactly one supervisor chain (roots={roots})")
    check(bool(listener) and any(r in chain_ids for r in roots),
          "the port owner is inside the supervisor tree")

    # 2. the studio reports its own supervision
    payload = state()
    supervision = (payload or {}).get("supervision") or {}
    check(bool(supervision.get("supervised")), "the studio reports supervision in /api/state")
    check(supervision.get("supervisor") == MARKER,
          f"the studio names its supervisor ({supervision.get('supervisor')!r})")

    # 3. the lock names a live owner
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {}
    owner = int(lock.get("pid") or 0)
    check(owner in supervisor_pids(), f"the lock names a live supervisor (pid {owner})")

    # 4. a second supervisor refuses, and the live one is untouched
    before = supervisor_pids()
    second = subprocess.run([PYTHON, str(PROJECT / "pixel_supervisor.py")],
                             capture_output=True, text=True, timeout=120)
    check(second.returncode == 3, f"a second supervisor refuses with rc=3 (got {second.returncode})")
    check("already owns" in (second.stdout or ""), "the refusal names the live owner")
    check(supervisor_pids() == before, "the live supervisor was not disturbed")
    check(healthy(), "the studio still answers after the refusal")

    # 5. a crash is recovered
    victim = sc.listener_pid(PORT)
    subprocess.run(["taskkill", "/PID", str(victim), "/F"], capture_output=True, text=True)
    recovered = wait_for(lambda: (sc.listener_pid(PORT) not in (None, victim)) and healthy(), 90)
    check(recovered, "the studio comes back by itself after a crash")
    check(sc.listener_pid(PORT) != victim, "the replacement is a new process")

    # 6. the launcher is idempotent
    before_studio = sc.listener_pid(PORT)
    before_sup = supervisor_pids()
    start_via_launcher()
    check(sc.listener_pid(PORT) == before_studio, "the launcher left the healthy studio alone")
    check(supervisor_pids() == before_sup, "the launcher did not start a second supervisor")

    # 7. a cold stop frees the port, a cold start brings it back
    stop_everything()
    check(sc.listener_pid(PORT) is None, "a cold stop frees the port")
    check(start_via_launcher(), "the canonical launcher starts the studio again")
    check(wait_for(healthy, 120), "the studio is healthy again")
    check(len(chain_roots()) == 1, "the end state is one supervisor chain")

    # 8. the end state
    listener = sc.listener_pid(PORT)
    chain_ids = {p["ProcessId"] for p in sc.chain_of(listener)} if listener else set()
    check(bool(listener) and any(r in chain_ids for r in chain_roots()),
          "the port is owned by the supervisor tree again")

    failed = [d for ok, d in RESULTS if not ok]
    print(f"\n=== {len(RESULTS) - len(failed)}/{len(RESULTS)} assertions passed ===")
    for d in failed:
        print(f"  FAILED: {d}")

    # The service is left running whatever happened.
    if not healthy():
        print("  the service was down - restoring it")
        start_via_launcher()
        wait_for(healthy, 120)
    print(f"  final state: {'healthy' if healthy() else 'DOWN'} on :{PORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
