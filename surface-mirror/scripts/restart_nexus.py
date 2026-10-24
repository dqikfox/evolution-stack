"""Deprecated: NEXUS is restarted by its supervisor, not by killing it.

This script used to kill whatever held port 8650 and start a fresh uvicorn
with the repo .venv. That is now actively wrong twice over:

  * the repo .venv has a broken numpy, so the service came back *without* a
    working vector store (chroma: not_ready) while looking perfectly healthy;
  * killing the process fought the supervisor for the port, producing a flap
    where each side killed the other's instance.

The canonical path is start_nexus.cmd, which starts run_nexus.py - the
supervisor that restarts uvicorn with capped backoff, reclaims the port from
an orphaned instance, and uses the venv that actually has numpy + chromadb.

Kept as a filename so any existing caller keeps working, but it now only
delegates.
"""
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).parent / "start_nexus.cmd"


def main() -> int:
    if not LAUNCHER.exists():
        print(f"result ERROR launcher missing: {LAUNCHER}")
        return 1
    proc = subprocess.run(["cmd", "/c", str(LAUNCHER)], capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.strip())
    print("result OK" if proc.returncode == 0 else f"result ERROR rc={proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
