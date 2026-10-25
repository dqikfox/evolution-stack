"""
End-to-end contract test for the canonical service launchers.

The launchers are the thing that keeps seven services alive: the Startup
folder, the service healer and the registry all call the same file. Their
contract is:

  1. starting from nothing, the launcher brings the service up and exits 0;
  2. the service does NOT inherit the caller's stdout pipe - a launcher
     whose child holds the pipe blocks the caller in read() until the
     SERVICE exits, not the launcher;
  3. the launcher is idempotent - called when the service is already up, it
     exits 0 without disturbing the running instance;
  4. the launcher exits inside its own stated budget.

The test that used to live in a scratch file got the last one wrong: it
waited 90 seconds for a launcher whose own health budget is 180 seconds, so
on a loaded host it reported "LAUNCHER NEVER EXITED" for a launcher that was
correctly waiting - and it killed the live service to do it. This version
waits longer than the implementation promises, and always puts the service
back.

A test must not fail a correct implementation for being slower than the
test's patience, and it must not damage the system it is testing.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERMES = Path(r"C:\Users\KING\AppData\Local\hermes")
SCRIPTS = HERMES / "scripts"

# The launcher promises to have the service answering within 180s. The test
# must wait longer than the promise, or it measures its own impatience.
LAUNCHER_BUDGET_S = 180
TEST_DEADLINE_S = LAUNCHER_BUDGET_S + 90
# A launcher that is still within its own budget may legitimately be running
# this long. Only past that is it hung.
HUNG_AFTER_S = LAUNCHER_BUDGET_S + 60

TARGETS = [
    {
        "name": "TESSERACT",
        "launcher": SCRIPTS / "start_tesseract.cmd",
        "port": 8705,
        "health": "http://127.0.0.1:8705/health",
        "marker": "TESSERACT",
    },
    {
        "name": "NEXUS",
        "launcher": SCRIPTS / "start_nexus.cmd",
        "port": 8650,
        "health": "http://127.0.0.1:8650/health",
        "marker": "nexus-core",
    },
]


def ps(cmd: str, t: int = 90) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=t).stdout.strip()


def ancestors() -> set:
    """This process and its ancestors - never kill them."""
    out = set()
    me = ps("$PID").strip()
    cur = me
    for _ in range(8):
        if not cur.isdigit():
            break
        out.add(int(cur))
        par = ps(f"(Get-CimInstance Win32_Process -Filter 'ProcessId={cur}').ParentProcessId").strip()
        if par.isdigit():
            cur = par
        else:
            break
    return out


def port_owner(port: int) -> int | None:
    out = ps(f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty OwningProcess -Unique")
    for token in out.split():
        if token.isdigit():
            return int(token)
    return None


def health_ok(url: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def proc_info(pid: int) -> dict | None:
    out = ps(f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue; "
             "if ($p) { $p.ProcessId.ToString() + '|' + $p.ParentProcessId + '|' + $p.CommandLine }")
    if not out:
        return None
    pid_s, _, rest = out.partition("|")
    parent_s, _, cl = rest.partition("|")
    if not pid_s.strip().isdigit():
        return None
    parent = int(parent_s) if parent_s.strip().isdigit() else 0
    return {"pid": int(pid_s.strip()), "parent": parent, "cmd": cl or ""}


def process_chain(pid: int) -> list:
    """The process and its ancestors, outermost last."""
    chain = []
    cur = pid
    for _ in range(10):
        info = proc_info(cur)
        if not info:
            break
        chain.append(info)
        cur = info["parent"]
        if not cur:
            break
    return chain


def stop_service(port: int, marker: str) -> list:
    """Stop the service AND any supervisor that would silently respawn it.

    Two rules, both learned the hard way:

      * the SUPERVISOR is stopped FIRST. A supervisor whose child dies
        respawns it within seconds, so killing the child first means the
        service comes straight back, the test measures nothing, and two
        supervisors end up fighting over the port;
      * this process and its ancestors are never candidates - the test must
        not kill the tool that is running it.
    """
    protected = ancestors()
    victims: dict = {}          # pid -> depth (0 = outermost)

    owner = port_owner(port)
    chain = process_chain(owner) if owner else []
    # chain[0] is the outermost ancestor, chain[-1] the port owner. The
    # supervisor is the outermost link whose command line mentions the
    # service; everything between it and the port owner is the service tree
    # and has to go with it, or the port stays bound.
    sup_idx = None
    for i, info in enumerate(chain):
        if marker.lower() in info["cmd"].lower():
            sup_idx = i
    cut = sup_idx if sup_idx is not None else len(chain) - 1
    for depth, info in enumerate(reversed(chain[:cut + 1])):
        if info["pid"] in protected:
            continue
        victims[info["pid"]] = depth

    # any other process that mentions the service (a second supervisor, a
    # leftover launcher) - but never this test or its ancestors
    for line in ps("Get-CimInstance Win32_Process | ForEach-Object { "
                   "$_.ProcessId.ToString() + '|' + $_.CommandLine }").splitlines():
        pid_s, _, cl = line.partition("|")
        if not pid_s.strip().isdigit():
            continue
        pid = int(pid_s.strip())
        if pid in protected or pid in victims:
            continue
        if marker.lower() in cl.lower():
            victims[pid] = 0

    killed = []
    # outermost first: that is the supervisor, and it must be stopped before
    # anything it can resurrect
    for pid in sorted(victims, key=lambda p: (victims[p], p)):
        ps(f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue")
        killed.append(pid)
    time.sleep(3)
    return killed


def supervisor_count(marker: str) -> int:
    """How many independent supervisor chains are alive for a service."""
    out = ps("Get-CimInstance Win32_Process | ForEach-Object { "
             "$_.ProcessId.ToString() + '|' + $_.ParentProcessId + '|' + $_.CommandLine }")
    matching = []
    for line in out.splitlines():
        pid_s, _, rest = line.partition("|")
        parent_s, _, cl = rest.partition("|")
        if not pid_s.strip().isdigit():
            continue
        pid = int(pid_s.strip())
        if marker.lower() not in cl.lower():
            continue
        # the outermost matching process of a chain is its supervisor
        parent = int(parent_s) if parent_s.strip().isdigit() else 0
        parent_cl = ""
        if parent:
            info = proc_info(parent)
            parent_cl = (info or {}).get("cmd", "")
        if marker.lower() not in parent_cl.lower():
            matching.append(pid)
    return len(matching)


def run_launcher(launcher: Path) -> dict:
    """Run the launcher with a PIPED stdout and watch for the pipe to close.

    The pipe is the whole point: if the service inherits it, the pipe stays
    open for the service's whole life and the caller blocks in read().
    """
    t0 = time.time()
    proc = subprocess.Popen(["cmd", "/c", str(launcher)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    eof = {"ok": False}
    out = []

    def _reader():
        try:
            out.append(proc.stdout.read())
            eof["ok"] = True
        except Exception:
            pass

    import threading
    th = threading.Thread(target=_reader, daemon=True)
    th.start()

    exited = False
    while time.time() - t0 < TEST_DEADLINE_S:
        if proc.poll() is not None:
            exited = True
            break
        time.sleep(0.3)
    elapsed = time.time() - t0
    if not exited:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=60)
        except Exception:
            pass
    th.join(timeout=5)
    return {
        "exited": exited,
        "elapsed": elapsed,
        "rc": proc.returncode,
        "pipe_eof": eof["ok"],
        "output": ("".join(out) or "").strip(),
    }


def check(target: dict) -> list:
    problems = []
    name = target["name"]
    launcher = target["launcher"]
    port = target["port"]
    health = target["health"]

    if not launcher.exists():
        return [f"{name}: the launcher is missing ({launcher})"]

    # --- idempotence: called with the service already up ---------------
    if port_owner(port) is not None:
        r = run_launcher(launcher)
        if not r["exited"]:
            problems.append(f"{name}: the launcher did not exit on the no-op path")
        elif r["rc"] != 0:
            problems.append(f"{name}: the launcher exited {r['rc']} on the no-op path, expected 0")
        elif r["elapsed"] > 30:
            problems.append(f"{name}: the no-op path took {r['elapsed']:.1f}s - it should be immediate")
        else:
            print(f"  {name}: idempotent no-op ok (rc=0 in {r['elapsed']:.2f}s)")

    # --- cold start ------------------------------------------------------
    killed = stop_service(port, target["marker"])
    if port_owner(port) is not None:
        problems.append(f"{name}: the service would not stop (port {port} still held)")
        return problems
    print(f"  {name}: stopped (killed={killed}), starting via the canonical launcher")

    r = run_launcher(launcher)
    if not r["exited"]:
        problems.append(f"{name}: the launcher never exited within {TEST_DEADLINE_S}s "
                        f"(its own budget is {LAUNCHER_BUDGET_S}s)")
    else:
        if r["rc"] != 0:
            problems.append(f"{name}: the launcher exited {r['rc']}, expected 0")
        if r["elapsed"] > HUNG_AFTER_S:
            problems.append(f"{name}: the launcher took {r['elapsed']:.0f}s, past its "
                            f"{LAUNCHER_BUDGET_S}s budget")
        if not r["pipe_eof"]:
            problems.append(f"{name}: the service held the caller's stdout pipe "
                            f"(the caller would block until the SERVICE exits)")
        if not health_ok(health):
            problems.append(f"{name}: the health endpoint did not answer after the launch")
        if not problems:
            print(f"  {name}: cold start ok (rc={r['rc']} in {r['elapsed']:.1f}s, "
                  f"pipe_eof={r['pipe_eof']}, health=200)")

    # --- exactly one supervisor chain ------------------------------------
    # A second supervisor is not a cosmetic problem: two of them race for the
    # same port, and the loser retries in a loop. The test that finds this
    # has to leave the system with ONE chain, never two.
    sups = supervisor_count(target["marker"])
    if sups > 1:
        problems.append(f"{name}: {sups} supervisor chains are alive - two supervisors "
                        f"race for the same port")
    else:
        print(f"  {name}: {sups} supervisor chain(s) - clean")

    # --- always put the service back -------------------------------------
    if not health_ok(health):
        print(f"  {name}: restoring the service")
        run_launcher(launcher)
        if not health_ok(health):
            problems.append(f"{name}: the service could not be restored")
        else:
            print(f"  {name}: restored")
    return problems


def main() -> int:
    failures = []
    for t in TARGETS:
        print(f"\n=== {t['name']} (:{t['port']})")
        try:
            failures += check(t)
        except Exception as e:
            failures.append(f"{t['name']}: the test itself failed: {type(e).__name__} {e}")
    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("LAUNCHER CONTRACT OK - every launcher starts its service, releases the "
          "caller's pipe, exits inside its budget, and is idempotent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
