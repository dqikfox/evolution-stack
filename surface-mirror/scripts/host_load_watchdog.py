"""
host_load_watchdog.py - alert when the host is under SUSTAINED pressure.

The problem this replaces: the 5-minute Ollama health beat used to exit
non-zero whenever the machine was busy, so a loaded host produced a failed
job every 5 minutes. That buries real failures - a failure channel that
fires constantly is a failure channel nobody reads.

The fix has two halves:
  * the probe always exits 0 when it managed to measure, and records the
    load state as data;
  * this watcher reads those samples and speaks only on a TRANSITION -
    when sustained pressure begins, and when it ends.

"Transition" is the important word. An alert per sample is an alarm
nobody can act on; an alert per episode says "the host has been loaded for
15 minutes" and names the processes responsible.

Exit codes:
    0  nothing to report (healthy, or already reported)
    2  the watcher could not read its inputs
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BEAT = Path(r"C:\Users\KING\AppData\Local\hermes\health\ollama-beat.jsonl")
STATE = Path(r"C:\Users\KING\AppData\Local\hermes\state\host_load_state.json")


def read_samples(limit: int = 40) -> list[dict]:
    if not BEAT.exists():
        return []
    out = []
    try:
        with BEAT.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out[-limit:]


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def consecutive_degraded(samples: list[dict], needed: int) -> tuple[bool, int]:
    """True when the last `needed` samples are all degraded."""
    if len(samples) < needed:
        return False, 0
    tail = samples[-needed:]
    if all(s.get("degraded") for s in tail):
        return True, needed
    # also count how long the run of degraded samples is
    run = 0
    for s in reversed(samples):
        if s.get("degraded"):
            run += 1
        else:
            break
    return False, run


TESSERACT_DB = Path(r"C:\Users\KING\Projects\TESSERACT\data\tesseract.db")


def raise_alert(kind: str, message: str, data: dict) -> bool:
    """Record the transition as a first-class TESSERACT alert.

    The load episode belongs in the same feed the operator already watches
    - a separate notification channel would be a second place to look. If the
    dashboard is not there, the alert is simply skipped: the watchdog must
    never fail because an optional sink is missing.
    """
    if not TESSERACT_DB.exists():
        return False
    try:
        con = sqlite3.connect(str(TESSERACT_DB), timeout=5)
        con.execute("insert into alerts(type, message, data, ts) values (?,?,?,?)",
                    (kind, message, json.dumps(data), time.time()))
        con.commit()
        con.close()
        return True
    except Exception:                                       # noqa: BLE001
        return False


def top_consumers(limit: int = 3) -> list[str]:
    """Name the processes currently burning CPU, so the alert is actionable."""
    try:
        import psutil
    except ImportError:
        return []
    # psutil's cpu_percent() is a delta since the previous call, so the first
    # pass always reads 0. Prime it, wait, then measure.
    procs = []
    for proc in psutil.process_iter(["name"]):
        try:
            proc.cpu_percent()          # prime
            procs.append(proc)
        except Exception:               # noqa: BLE001
            continue
    time.sleep(0.8)
    names: dict[str, float] = {}
    for proc in procs:
        try:
            cpu = proc.cpu_percent()
            if cpu and cpu > 5:
                nm = proc.info.get("name") or "?"
                names[nm] = names.get(nm, 0) + cpu
        except Exception:               # noqa: BLE001
            continue
    top = sorted(names.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [f"{n} ({c:.0f}%)" for n, c in top]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=3,
                    help="consecutive degraded samples required to raise an episode")
    ap.add_argument("--force-report", action="store_true",
                    help="report the current state even if it is not a transition")
    args = ap.parse_args()

    samples = read_samples()
    if not samples:
        print("host_load_watchdog: no samples yet", file=sys.stderr)
        return 2

    state = load_state()
    episode = state.get("episode", "unknown")
    since = state.get("since")

    degraded_now, run = consecutive_degraded(samples, args.samples)
    latest = samples[-1]
    cpu = latest.get("cpu", 0)
    ram = latest.get("ram_pct", 0)
    gpu = latest.get("gpu_temp")

    if degraded_now and episode != "degraded":
        state = {"episode": "degraded", "since": time.time(), "run": run}
        save_state(state)
        who = ", ".join(top_consumers()) or "unknown"
        detail = {"episode": "started", "cpu": cpu, "ram_pct": ram, "gpu_temp": gpu,
                  "samples": args.samples, "consumers": who}
        raise_alert("host_load",
                    f"Host load episode started (cpu {cpu}%, ram {ram}%)", detail)
        print(f"Host load episode STARTED: sustained pressure over {args.samples} samples "
              f"(cpu {cpu}%, ram {ram}%, gpu {gpu}C). Main consumers: {who}.")
        return 0

    if not degraded_now and episode == "degraded":
        state = {"episode": "normal", "since": time.time(), "recovered_from": since}
        save_state(state)
        raise_alert("host_load",
                    f"Host load episode ended (cpu {cpu}%, ram {ram}%)",
                    {"episode": "ended", "cpu": cpu, "ram_pct": ram, "gpu_temp": gpu,
                     "duration_s": round(time.time() - (since or time.time()))})
        print(f"Host load episode ENDED: pressure cleared (cpu {cpu}%, ram {ram}%, gpu {gpu}C).")
        return 0

    if episode == "degraded":
        state["run"] = run
        state["last_seen"] = time.time()
        save_state(state)

    if args.force_report:
        print(f"Host load: cpu {cpu}%, ram {ram}%, gpu {gpu}C, "
              f"episode={episode}, degraded run={run}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
