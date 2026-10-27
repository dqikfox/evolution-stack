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


def command_line_matches_marker(command_line: str, marker: str) -> bool:
    """Does this command line belong to the service we manage?

    A marker match for a SUPERVISOR means the command line ENDS with the
    script. An ORPHAN - the service's own child left holding the port
    after its supervisor died - has a different shape: the script sits in
    the middle of the command line, followed by its arguments. So the
    orphan check is a containment test, and it is the only thing standing
    between a reclaim and an unrelated process that happens to hold the
    port.

    A TRUE orphan is harder: the supervisor is gone, so the only identity
    left on the port is the project itself. The marker "TESSERACT\\start.py"
    therefore also matches a command line that carries the project token
    "TESSERACT" - the interpreter path of the service's own venv, its log
    config, anything of ours. That is still a service-specific token, so
    an unrelated process on the port is still left alone, but our own
    orphan can finally be cleared instead of blocking every restart.
    """
    if not command_line:
        return False
    low = command_line.lower()
    marker = marker.lower()
    if marker in low:
        return True
    if "\\" in marker:
        token = marker.split("\\")[0]
        if token and token in low:
            return True
    return False


def chain_belongs_to_service(chain, marker) -> bool:
    """Is this process chain ours?

    A service's identity is not always on the process that HOLDS the port.
    The venv shim is the parent: the interpreter path carries the project
    (TESSERACT\\.venv\\Scripts\\python.exe), while the real interpreter that
    ends up owning the socket is a bare uv python with no project token at
    all. Checking only the holder therefore refused our own orphan and
    blocked every restart.

    So the check walks the chain - but only its INTERPRETER members. A
    shell whose command line merely mentions the project (a transcript
    command, a grep) must never make a stranger look like our service.
    """
    for p in chain:
        name = (p.get("Name") or "").lower()
        if not name.startswith("python"):
            continue
        cmd = p.get("CommandLine") or ""
        if command_line_matches_marker(cmd, marker):
            return True
    return False


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
            holder = next((p for p in chain if p["ProcessId"] == lp), {})
            if not (command_line_matches_marker(holder.get("CommandLine") or "", marker)
                    or chain_belongs_to_service(chain, marker)):
                # Something that is not our service holds the port. Stopping
                # our own processes is done; killing the stranger is not.
                print(f"  :{port} is held by a process that is not ours - "
                      f"left alone")
                print(f"  :{port} listener after stop:",
                      listener_pid(port) or "(free)")
                return True
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


def ensure(port, marker):
    """Decide what a launcher must do about the port - and take the
    destructive action only when it is the only correct action.

    A launcher that reclaims first is destructive before it knows anything:
    a healthy, supervised service gets torn down and restarted on every
    call, and a launcher whose own tools are missing kills the service and
    THEN reports the missing tool. So the port is inspected first and the
    answer is a decision, not a boolean:

        0  - a live supervisor owns the port; do nothing
        10 - the port was held by an ORPHAN; it has been reclaimed
        11 - nothing holds the port
        1  - a stranger holds the port; it must not be stolen

    An orphan is ours to replace: it is unsupervised, it may be running
    stale code, and nothing restarts it when it dies. A stranger is not
    ours at all, and killing it would take out an unrelated process.
    """
    lp = listener_pid(port)
    if not lp:
        print(f"  :{port} is free - the launcher must start it")
        return 11
    chain = chain_of(lp)
    chain_pids = {p["ProcessId"] for p in chain}
    sups = supervisor_pids(marker)
    roots = [p for p in sups if p["ParentProcessId"] not in
             {s["ProcessId"] for s in sups}]
    if any(p["ProcessId"] in chain_pids for p in roots):
        print(f"  :{port} is owned by a live supervisor "
              f"({[p['ProcessId'] for p in roots]}) - nothing to reclaim")
        return 0
    print(f"  :{port} is held by an ORPHAN (no supervisor above it): "
          f"{[p['ProcessId'] for p in chain]}")
    holder = next((p for p in chain if p["ProcessId"] == lp), {})
    if not (command_line_matches_marker(holder.get("CommandLine") or "", marker)
            or chain_belongs_to_service(chain, marker)):
        # Something that is NOT our service holds the port. Killing it
        # would take out an unrelated process, so the reclaim refuses and
        # the launcher reports the conflict instead of stealing the port.
        print(f"  refusing to touch it: the holder is not ours "
              f"(no {marker!r} in its command line)")
        return 1
    for p in chain:
        subprocess.run(["taskkill", "/PID", str(p["ProcessId"]), "/F", "/T"],
                       capture_output=True, text=True)
    for _ in range(20):
        if not listener_pid(port):
            print(f"  :{port} reclaimed")
            return 10
        time.sleep(0.5)
    print(f"  :{port} would not release")
    return 1


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
    return ensure(port, marker) != 1


def _probe(url, contains=None, timeout=6):
    """Is the SERVICE answering, or merely something on the port?

    A body check is what separates them: a stray process can answer 200
    on the same port, and a launcher that believes it is the service will
    report the service as healthy when it is not.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(65536).decode("utf-8", "replace")
    except Exception as exc:
        return False, f"no answer ({type(exc).__name__})"
    if contains and contains not in body:
        return False, "answered, but not our service"
    return True, "healthy"


def prepare(port,
    marker, health=None, contains=None, allow_unhealed=True):
    try:
        import json
        with open(r"E:\ultron-memory\infra\SERVICES.json", "r") as f: reg = json.load(f)
        for s in reg.get("services", []):
            if str(s.get("port")) == str(port) and s.get("start", {}).get("heal") is False:
                return 1, "forbidden"
    except Exception: pass
    """Put the port in a state a launcher can start from, and say which.

    The decision the launcher needs is one of three things:

        0  - start it: the port is free, an orphan was reclaimed, or a
             supervised-but-silent chain was stopped
        1  - refuse: a stranger holds the port and must not be stolen
        2  - leave it alone: it is healthy AND supervised

    Order matters. The tools are checked by the launcher before it calls
    this. The SERVICE is probed before anything is destroyed, so a healthy
    service is never torn down to be rebuilt. And a supervised but silent
    chain is stopped rather than duplicated - two generations of one
    service is worse than one broken one.
    """
    healthy, why = (False, "not probed")
    if health:
        healthy, why = _probe(health, contains)
        print(f"  probe {health}: {why}")

    lp = listener_pid(port)
    if not lp:
        print(f"  :{port} is free - the launcher must start it")
        return 0
    chain = chain_of(lp)
    chain_pids = {p["ProcessId"] for p in chain}
    sups = supervisor_pids(marker)
    roots = [p for p in sups if p["ParentProcessId"] not in
             {s["ProcessId"] for s in sups}]
    supervised = any(p["ProcessId"] in chain_pids for p in roots)

    if supervised:
        if healthy:
            print(f"  :{port} is healthy and supervised by "
                  f"{[p['ProcessId'] for p in roots]} - leave it alone")
            return 2
        print(f"  :{port} is supervised by {[p['ProcessId'] for p in roots]} "
              f"but not answering - stopping the chain so it can be replaced")
        stop(marker, port)
        for _ in range(20):
            if not listener_pid(port):
                break
            time.sleep(0.5)
        if listener_pid(port):
            print(f"  :{port} would not release")
            return 1
        print(f"  :{port} released - the launcher must start it")
        return 0

    # unsupervised: an orphan of ours, or a stranger
    holder = next((p for p in chain if p["ProcessId"] == lp), {})
    if not (command_line_matches_marker(holder.get("CommandLine") or "", marker)
            or chain_belongs_to_service(chain, marker)):
        print(f"  refusing to touch :{port} - the holder is not ours "
              f"(no {marker!r} in its command line)")
        return 1
    print(f"  :{port} is held by an ORPHAN of ours: "
          f"{[p['ProcessId'] for p in chain]} - reclaiming it")
    for proc in chain:
        subprocess.run(["taskkill", "/PID", str(proc["ProcessId"]), "/F", "/T"],
                       capture_output=True, text=True)
    for _ in range(20):
        if not listener_pid(port):
            print(f"  :{port} reclaimed - the launcher must start it")
            return 0
        time.sleep(0.5)
    print(f"  :{port} would not release")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["stop", "start", "restart", "report", "reclaim", "ensure", "prepare"])
    ap.add_argument("--marker", default="run_nexus.py")
    ap.add_argument("--launcher")
    ap.add_argument("--port", type=int, default=8650)
    ap.add_argument("--health")
    ap.add_argument("--contains")
    a = ap.parse_args()
    if a.action == "prepare":
        print(f"=== preparing :{a.port} (marker={a.marker!r}) ===")
        return prepare(a.port, a.marker, a.health, a.contains)
    if a.action == "ensure":
        print(f"=== deciding on :{a.port} (marker={a.marker!r}) ===")
        return ensure(a.port, a.marker)
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
