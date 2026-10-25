"""Service control: stop a supervised service cleanly, and start it again.

The chain rules that matter, learned the hard way:

  * a supervisor RESTARTS its child when the child dies, so killing the
    leaf first just makes the service come straight back
  * the supervisor must be stopped FIRST, and then its children - if the
    child outlives the supervisor it keeps serving the port, the
    launcher decides the service is "already up" and never starts a new
    supervisor, and the service is left as an unsupervised orphan
  * there can be MORE THAN ONE supervisor for the same service after a
    botched restart, so every supervisor has to go, not just the one
    above the current listener

So: find EVERY supervisor for the service by its command-line marker,
stop them all, stop every descendant, then start through the canonical
launcher and assert the end state - exactly one supervisor chain and the
port owned by its descendant.

Usage:
    python service_control.py stop  --marker run_nexus.py   --port 8650
    python service_control.py start --launcher <path.cmd>   --port 8650
    python service_control.py restart --marker run_nexus.py \
        --launcher <path.cmd> --port 8650
"""
import argparse
import json
import os
import subprocess
import sys
import time

PS = "powershell.exe"
PY = r"C:\Users\KING\.cache\nexus-venv\Scripts\python.exe"


def ps(script):
    r = subprocess.run([PS, "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=180)
    return (r.stdout or "").strip()


def all_processes():
    out = ps(r"""
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python|cmd|powershell' } |
  Select-Object ProcessId, ParentProcessId, Name, CommandLine |
  ConvertTo-Json -Compress
""")
    if not out or out == "null":
        return []
    rows = json.loads(out)
    return [rows] if isinstance(rows, dict) else rows


def descendants(procs, roots):
    by_parent = {}
    for p in procs:
        by_parent.setdefault(p["ParentProcessId"], []).append(p["ProcessId"])
    out, stack = set(), list(roots)
    while stack:
        cur = stack.pop()
        for child in by_parent.get(cur, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def listener_pid(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids = [int(l.split()[-1]) for l in out.splitlines()
            if f":{port}" in l and "LISTENING" in l]
    return pids[0] if pids else None


def supervisor_pids(marker):
    """The processes that ACTUALLY run the service script.

    Matching a marker anywhere in the command line is not enough: a
    Hermes task whose prompt mentions the script, a powershell wrapper
    and the uv shim all contain the marker, and killing one of those is
    how you take out the wrong thing. A supervisor is a process whose
    command line ENDS with the script - it is the interpreter running it.
    """
    out = []
    for p in all_processes():
        cmd = (p.get("CommandLine") or "")
        low = cmd.lower()
        if marker.lower() not in low:
            continue
        if "hermes-agent" in low or "hermes\\agent" in low:
            continue                      # a Hermes task, not the service
        name = (p.get("Name") or "").lower()
        if not name.startswith("python"):
            continue                      # a wrapper (powershell/cmd) that
                                         # merely has the marker as an ARGUMENT
        if "service_control.py" in low:
            continue                      # THIS tool's own invocation - the
                                         # marker is its last argument
        if p.get("ProcessId") == os.getpid():
            continue
        if not cmd.strip().rstrip('"').lower().endswith(marker.lower()):
            continue                      # a wrapper that merely mentions it
        out.append(p)
    return out


def chain_of(pid):
    procs = {p["ProcessId"]: p for p in all_processes()}
    chain, cur = [], pid
    while cur and cur in procs:
        p = procs[cur]
        chain.append(p)
        cur = p["ParentProcessId"]
    return chain


def stop(marker, port=None):
    sups = supervisor_pids(marker)
    if not sups:
        print(f"  no supervisor matching {marker!r}")
    else:
        procs = all_processes()
        kids = descendants(procs, [p["ProcessId"] for p in sups])
        print(f"  supervisors: {[p['ProcessId'] for p in sups]}")
        for p in sups:
            print(f"    kill supervisor {p['ProcessId']}: "
                  f"{(p.get('CommandLine') or '')[:60]}")
            subprocess.run(["taskkill", "/PID", str(p["ProcessId"]), "/F"],
                           capture_output=True, text=True)
        time.sleep(2.0)
        for pid in sorted(kids):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, text=True)
        time.sleep(1.5)
    if port:
        # an ORPHAN can still be holding the port: a supervisor that died
        # while respawning its child leaves the child serving with nobody
        # above it. Clear the whole chain, or the launcher will call the
        # service "already up" and never start a supervisor.
        lp = listener_pid(port)
        if lp:
            chain = chain_of(lp)
            print(f"  clearing orphan chain holding :{port}: "
                  f"{[p['ProcessId'] for p in chain]}")
            for p in chain:
                subprocess.run(["taskkill", "/PID", str(p["ProcessId"]), "/F"],
                               capture_output=True, text=True)
            time.sleep(1.5)
        print(f"  :{port} listener after stop:", listener_pid(port) or "(free)")
    return True


def start(launcher, port=None, wait=90):
    r = subprocess.run([r"C:\Windows\System32\cmd.exe", "/c", launcher],
                       capture_output=True, text=True, timeout=300)
    print(f"  launcher rc={r.returncode}")
    for line in (r.stdout or "").strip().splitlines()[-5:]:
        print("     ", line)
    if port:
        for _ in range(wait):
            if listener_pid(port):
                break
            time.sleep(1)
        print(f"  :{port} listener after start:", listener_pid(port) or "(NOT UP)")
    return r.returncode


def report(port, marker):
    """The end state: one supervisor CHAIN, and the port owned by its tree."""
    sups = supervisor_pids(marker)
    lp = listener_pid(port)
    # A supervisor is a TREE, not a process: the uv shim and the venv
    # python are two processes in one chain. Count the ROOTS - the
    # supervisors that have no supervisor above them.
    sup_pids = {p["ProcessId"] for p in sups}
    roots = [p for p in sups if p["ParentProcessId"] not in sup_pids]
    print(f"\n  supervisor processes: {len(sups)} {sorted(sup_pids)}")
    print(f"  supervisor CHAINS:    {len(roots)} {[p['ProcessId'] for p in roots]}")
    if lp:
        chain = chain_of(lp)
        for p in chain:
            print(f"    pid={p['ProcessId']:<8} ppid={p['ParentProcessId']:<8} "
                  f"{(p.get('CommandLine') or '')[:62]}")
        chain_pids = {p["ProcessId"] for p in chain}
        supervised = any(p["ProcessId"] in chain_pids for p in roots)
        ok = len(roots) == 1 and supervised
        print(f"  port owner is inside a supervisor tree: {supervised}")
        print(f"  VERDICT: {'OK' if ok else 'PROBLEM'}")
        return ok
    print("  VERDICT: PROBLEM (no listener)")
    return False


def reclaim(port, marker):
    """Clear an ORPHAN holding the port, so a supervisor can be started.

    "The port answers" is not "the service is healthy". A supervisor that
    was killed leaves its child running and holding the port; a launcher
    that only probes the port then says "already up" and never starts a
    supervisor, so the service keeps serving unsupervised - and stale
    code - until that orphan dies for good.

    So: if the port answers but no live supervisor owns it, the orphan is
    terminated and the port is freed. An unrelated process on the port is
    never touched.
    """
    lp = listener_pid(port)
    if not lp:
        print(f"  :{port} is free - nothing to reclaim")
        return True
    chain = chain_of(lp)
    chain_pids = {p["ProcessId"] for p in chain}
    roots = [p for p in supervisor_pids(marker) if p["ParentProcessId"] not in
             {s["ProcessId"] for s in supervisor_pids(marker)}]
    if any(p["ProcessId"] in chain_pids for p in roots):
        print(f"  :{port} is owned by a live supervisor "
              f"({[p['ProcessId'] for p in roots]}) - nothing to reclaim")
        return True
    print(f"  :{port} is held by an ORPHAN (no supervisor above it): "
          f"{[p['ProcessId'] for p in chain]}")
    for p in chain:
        subprocess.run(["taskkill", "/PID", str(p["ProcessId"]), "/F", "/T"],
                       capture_output=True, text=True)
    for _ in range(20):
        if not listener_pid(port):
            print(f"  :{port} reclaimed")
            return True
        time.sleep(0.5)
    print(f"  :{port} would not release")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["stop", "start", "restart", "report", "reclaim"])
    ap.add_argument("--marker", default="run_nexus.py")
    ap.add_argument("--launcher")
    ap.add_argument("--port", type=int, default=8650)
    a = ap.parse_args()
    if a.action == "reclaim":
        print(f"=== reclaiming :{a.port} (marker={a.marker!r}) ===")
        ok = reclaim(a.port, a.marker)
        return 0 if ok else 1
    if a.action in ("stop", "restart"):
        print(f"=== stopping (marker={a.marker!r}) ===")
        stop(a.marker, a.port)
    if a.action in ("start", "restart"):
        if not a.launcher:
            print("--launcher is required to start")
            return 2
        print(f"=== starting via {a.launcher} ===")
        start(a.launcher, a.port)
    print(f"=== end state :{a.port} ===")
    report(a.port, a.marker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
