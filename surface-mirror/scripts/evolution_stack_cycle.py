"""Cron-facing wrapper around the THRONE Evolution Stack.

Runs one benchmark-gated cycle and prints a compact status block for the
evolution worker agent. The stack lives at E:/ultron-memory/evolution-stack.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STACK = Path(r"E:\ultron-memory\evolution-stack")
STATUS_FILE = Path(r"C:\Users\KING\AppData\Local\hermes\cron\output\evolution_status.json")


def run() -> int:
    if not (STACK / "evo" / "loop.py").exists():
        print("EVOLUTION STACK MISSING at", STACK)
        return 1
    r = subprocess.run([sys.executable, "-m", "evo", "cycle"],
                       cwd=str(STACK), capture_output=True, text=True, timeout=900)
    out = (r.stdout or "").strip()
    print(out[-2000:])
    if r.returncode != 0:
        print("STDERR:", (r.stderr or "")[-800:])
    if STATUS_FILE.exists():
        try:
            d = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print("status parse error:", e)
            return 0
        print(f"GATE SCORE: {d.get('gate_score')}   HOST SCORE: {d.get('host_score')}")
        learning = d.get("learning") or {}
        if learning:
            print(f"LEARNING: {learning.get('lessons')} lessons distilled, "
                  f"proposer refreshed (variant #{learning.get('variant_id')})")
        print(f"GATE-ACTIONABLE FAILURES: {d.get('gate_failed')}")
        for f in d.get("failures", [])[:10]:
            print("  FAIL", f.get("name"), "-", str(f.get("detail"))[:90])
        if d.get("gate_failed"):
            print("  ^ these are the only targets a file change can fix. "
                  "Propose a change for one of them.")
        else:
            print("  ^ gate surface is healthy. Operator-level failures "
                  "(down services, dirty repos) need operator action, not a script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
