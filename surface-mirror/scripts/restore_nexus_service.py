"""Restore NEXUS CORE after an interrupted launcher-contract run.

The contract test stops the supervisor, restarts the service, and leaves
it running. If the test process is killed mid-run, the service can be
left with a live supervisor whose server child is gone, and a supervisor
lock naming a process that owns nothing.

This restores the one canonical path:
  1. stop the stale supervisor chain (the supervisor FIRST, then its
     child - a supervisor that outlives its child resurrects it)
  2. remove the stale supervisor lock
  3. run start_nexus.cmd, which does the dependency check, the
     service_control.prepare() handover, the detached spawn and the
     health wait
  4. verify the service answers
"""
import os
import subprocess
import sys
import time
import urllib.request

import psutil

ROOT = r"E:\ultron-memory\nexus-core"
LAUNCHER = r"C:\Users\KING\AppData\Local\hermes\scripts\start_nexus.cmd"
LOCK = os.path.join(ROOT, "logs", "supervisor.lock")
URL = "http://127.0.0.1:8650/health"


def cmdline(proc):
    try:
        return " ".join(proc.cmdline() or [])
    except Exception:
        return ""


def chain_roots():
    """run_nexus.py processes whose parent is not itself a run_nexus.py."""
    infos = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(proc.info.get("cmdline") or [])
        except Exception:
            continue
        if "run_nexus" in cl and "python" in (proc.info.get("name") or "").lower():
            infos.append(proc)
    roots = []
    for proc in infos:
        try:
            ppid = proc.parent().pid
        except Exception:
            ppid = None
        parent_is_chain = False
        for other in infos:
            if other.pid == proc.pid:
                continue
            try:
                if other.pid == ppid:
                    parent_is_chain = True
            except Exception:
                pass
        if not parent_is_chain:
            roots.append(proc)
    return roots


def port_answers():
    try:
        with urllib.request.urlopen(URL, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    print("=== 1. stop the stale supervisor chain ===")
    roots = chain_roots()
    print("  supervisor chains: %s" % [p.pid for p in roots])
    for sup in roots:
        for child in sup.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        try:
            sup.terminate()
        except Exception:
            pass
    deadline = time.time() + 15
    while time.time() < deadline and chain_roots():
        time.sleep(0.5)
    for sup in chain_roots():
        for child in sup.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        try:
            sup.kill()
        except Exception:
            pass
    time.sleep(2)
    print("  remaining chains: %s" % [p.pid for p in chain_roots()])

    print("=== 2. remove the stale supervisor lock ===")
    if os.path.exists(LOCK):
        try:
            os.remove(LOCK)
            print("  removed %s" % LOCK)
        except Exception as exc:
            print("  could not remove the lock: %s" % exc)
    else:
        print("  (no lock present)")

    print("=== 3. run the one canonical launcher ===")
    res = subprocess.run(["cmd", "/c", LAUNCHER], capture_output=True, text=True,
                         timeout=420)
    print("  launcher rc=%d" % res.returncode)
    tail = (res.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        print("    %s" % line)
    if res.returncode != 0:
        for line in (res.stderr or "").strip().splitlines()[-6:]:
            print("    ERR %s" % line)

    print("=== 4. verify ===")
    deadline = time.time() + 60
    ok = False
    while time.time() < deadline:
        if port_answers():
            ok = True
            break
        time.sleep(3)
    print("  health answers: %s" % ok)
    print("  supervisor chains: %s" % [p.pid for p in chain_roots()])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
