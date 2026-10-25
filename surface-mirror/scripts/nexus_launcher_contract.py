"""Launcher contract test for NEXUS CORE.

NOT NAMED test_*.py ON PURPOSE. The house disk-cleanup plugin classifies
any file whose name starts with "test_" or "tmp_" as disposable and
deletes it at the end of the next task, unless it sits inside a git
worktree. hermes/scripts is not a worktree, so a file called
test_nexus_launcher_contract.py was deleted out from under a passing
run - and the contract it enforced quietly stopped existing. A contract
is a permanent artifact; it is named like one.

The contract this file exists to enforce:

  * ONE idempotent launcher (start_nexus.cmd) owns the service
  * exactly ONE supervisor chain for the port afterwards
  * a second supervisor is refused, not fought with
  * the service is restored before the test ends
  * the test waits longer than the implementation's own start budget

Every assertion is checked against the live machine, not against a
mock. If the launcher cannot bring the service back, the test fails
loudly rather than leaving a stopped service behind.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(r"E:\ultron-memory\nexus-core")
LAUNCHER = Path(r"C:\Users\KING\AppData\Local\hermes\scripts\start_nexus.cmd")
LOCK = ROOT / "logs" / "supervisor.lock"
PORT = 8650

# the launcher is given a generous budget; the supervisor's own backoff
# starts at 1s and doubles, so a start can legitimately take a while
START_BUDGET_S = 120


def supervisor_roots() -> list[dict]:
    """The top of each supervisor chain.

    The supervisor runs under a venv shim, so one supervisor is TWO
    processes with "run_nexus.py" in their command line: the shim and the
    real interpreter it spawns. Counting both would report a duplicate
    where there is one chain, so a root is a run_nexus.py process whose
    PARENT is not itself a run_nexus.py process.
    """
    infos = _all_processes()
    by_pid = {i["pid"]: i for i in infos}
    roots = []
    for info in infos:
        if "python" not in (info.get("name") or "").lower():
            continue
        if "run_nexus.py" not in _cmdline(info):
            continue
        parent = by_pid.get(info.get("ppid"))
        if parent is not None and "run_nexus.py" in _cmdline(parent):
            continue          # a wrapper inside a chain, not a chain head
        roots.append(info)
    return roots


def nexus_uvicorn() -> list[dict]:
    """Every uvicorn process serving the port, wrappers included."""
    return [i for i in _all_processes()
            if "uvicorn" in _cmdline(i) and f"--port {PORT}" in _cmdline(i)]


def lock_holder_pid() -> int | None:
    try:
        holder = json.loads(LOCK.read_text(encoding="utf-8"))
        return int(holder.get("pid") or 0) or None
    except Exception:
        return None


def _cmdline(info: dict) -> str:
    """Command line of a process, from a process_iter info dict."""
    try:
        return " ".join(info.get("cmdline") or [])
    except Exception:
        return ""


def _all_processes() -> list:
    out = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline", "create_time"]):
        try:
            out.append(p.info)
        except Exception:
            continue
    return out


def supervisors() -> list[dict]:
    """Every live run_nexus.py supervisor.

    psutil is used rather than PowerShell: a detection helper that has to
    be quoted through a shell is a detection helper that will quietly
    report nothing and make every assertion below vacuous.
    """
    rows = []
    for info in _all_processes():
        name = (info.get("name") or "").lower()
        cl = _cmdline(info)
        if "python" not in name:
            continue
        if "run_nexus.py" not in cl:
            continue
        rows.append(info)
    return rows


def uvicorn_children() -> list[dict]:
    rows = []
    for info in _all_processes():
        cl = _cmdline(info)
        if "uvicorn" in cl and f"--port {PORT}" in cl:
            rows.append(info)
    return rows


def listener_pid() -> int | None:
    """PID listening on the port, from the OS (not from a process guess)."""
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == PORT:
                return c.pid
    except Exception:
        pass
    return None


def ancestors(pid: int) -> list[int]:
    chain = []
    cur = pid
    for _ in range(8):
        try:
            p = psutil.Process(cur)
            cur = p.ppid()
        except Exception:
            break
        if cur <= 0:
            break
        chain.append(cur)
    return chain


def port_answers(timeout: float = 5.0) -> bool:
    """True when the service answers /health with a healthy body.

    urllib, not a raw socket: a single recv() can return the headers and
    leave the body in the next packet, and a health check that reads
    only the headers reports a healthy service as dead.
    """
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health",
                                    timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
        return '"ok"' in body or '"status":"live"' in body
    except Exception:
        return False


def health_json(timeout: float = 30.0) -> dict:
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health?deep=1",
                                    timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return {}


def search_results(query: str = "evolution", limit: int = 2) -> list:
    try:
        import urllib.parse
        import urllib.request
        url = (f"http://127.0.0.1:{PORT}/api/search?"
               + urllib.parse.urlencode({"q": query, "limit": limit}))
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "ignore")).get("results", [])
    except Exception:
        return []


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("  PASS  " if ok else "  FAIL  ") + msg)
        if not ok:
            failures.append(msg)

    print("=== BEFORE ===")
    before = supervisor_roots()
    print(f"  supervisor chains={[s['pid'] for s in before]}  listener={listener_pid()}")
    check(port_answers(), "service answers before the test")
    check(len(before) == 1, f"one supervisor chain before the test (found {len(before)})")

    print("=== STOP: the supervisor first, then its child ===")
    # stopping the supervisor before its child is the whole point: a
    # supervisor that outlives its child will resurrect it
    for sup in before:
        try:
            psutil.Process(sup["pid"]).terminate()
        except Exception:
            pass
    deadline = time.time() + 15
    while time.time() < deadline and supervisor_roots():
        time.sleep(0.5)
    for sup in before:
        try:
            psutil.Process(sup["pid"]).kill()
        except Exception:
            pass
    # only now, with no supervisor left to resurrect it, the child goes
    for child in nexus_uvicorn():
        try:
            psutil.Process(child["pid"]).kill()
        except Exception:
            pass
    deadline = time.time() + 30
    while time.time() < deadline and listener_pid() is not None:
        time.sleep(0.5)
    check(listener_pid() is None, "port is free after the stop")
    check(not supervisor_roots(), "no supervisor survives the stop")

    print("=== START: the one canonical launcher ===")
    t0 = time.time()
    subprocess.run(["cmd", "/c", "start", "", "/b", str(LAUNCHER)],
                   capture_output=True, text=True, timeout=60)
    deadline = time.time() + START_BUDGET_S
    up = False
    while time.time() < deadline:
        if port_answers():
            up = True
            break
        time.sleep(2)
    elapsed = time.time() - t0
    check(up, f"service is back within {START_BUDGET_S}s (took {elapsed:.0f}s)")
    if not up:
        print("  the service did NOT come back - restoring is impossible, failing hard")
        return 2

    print("=== ASSERT ONE CHAIN ===")
    time.sleep(3)
    chains = supervisor_roots()
    check(len(chains) == 1,
          f"exactly one supervisor chain (found {len(chains)}: {[s['pid'] for s in chains]})")
    lp = listener_pid()
    check(lp is not None, "the listener exists")
    if lp is not None:
        chain = ancestors(lp)
        check(any(pid in chain for pid in
                  [i["pid"] for i in _all_processes() if "run_nexus.py" in _cmdline(i)]),
              f"the listener descends from a supervisor (chain {chain})")
    check(LOCK.exists(), "the supervisor wrote its singleton lock")
    holder = lock_holder_pid()
    check(holder is not None, "the lock names a process")
    if holder is not None and lp is not None:
        check(holder in ancestors(lp),
              f"the lock names the supervisor that owns the listener ({holder})")
        check(psutil.pid_exists(holder), "the lock holder is alive")

    print("=== A SECOND SUPERVISOR MUST BE REFUSED ===")
    # it must refuse and exit, not serve. If it does not refuse, it will
    # fight the running service for the port, so the process is killed
    # on timeout rather than left behind.
    second = subprocess.Popen([sys.executable, str(ROOT / "run_nexus.py")],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
    try:
        out, _ = second.communicate(timeout=60)
        refused = "refusing to start a second one" in (out or "")
        check(refused, f"the second supervisor refused (rc={second.returncode})")
        check(second.returncode == 3, f"the refusal exits 3 (got {second.returncode})")
    except subprocess.TimeoutExpired:
        second.kill()
        try:
            second.communicate(timeout=15)
        except Exception:
            pass
        check(False, "a second supervisor did not refuse - it served instead")
    check(port_answers(), "the running service is undisturbed by the refusal")
    time.sleep(2)
    check(len(supervisor_roots()) == 1,
          "still exactly one supervisor chain after the refusal")

    print("=== FINAL STATE ===")
    print(f"  supervisor chains={[s['pid'] for s in supervisor_roots()]}  "
          f"listener={listener_pid()}")
    h = health_json()
    if h:
        notes = h.get("components", {}).get("database", {}).get("notes_count")
        vectors = h.get("components", {}).get("chroma", {}).get("vectors")
        check(h.get("ok") is True, "health is ok")
        check(bool(notes) and notes == vectors,
              f"the index survived the restart ({notes} notes, {vectors} vectors)")
    else:
        check(False, "health endpoint answered")
    check(len(search_results()) > 0, "search still answers end to end")

    print()
    if failures:
        print(f"LAUNCHER CONTRACT: {len(failures)} FAILURE(S)")
        for f in failures:
            print("   - " + f)
        return 1
    print("LAUNCHER CONTRACT: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
