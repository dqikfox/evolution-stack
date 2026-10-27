"""Start TESSERACT detached on THRONE if not healthy."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8705

# The application root is RESOLVED, not hardcoded.
#
# TESSERACT has two branches: master is the Python FastAPI app, main is
# the TypeScript lattice rewrite. They live in the same directory, and
# the other agent checks out main there - which removes the Python app's
# files from disk and leaves a tree that cannot start this service.
#
# So the launcher looks for a directory that actually HAS the app:
#
#   1. TESSERACT_ROOT, if the operator set it.
#   2. The canonical worktree, which is pinned to master and therefore
#      keeps the Python app and the live data/ directory.
#   3. The shared checkout, for when the tree is on master.
#
# The first candidate that contains server.py wins. A launcher that
# hardcodes one path breaks the moment the tree is switched underneath
# it, and a service that cannot be restarted is not a service.
_ROOT_CANDIDATES = (
    os.environ.get("TESSERACT_ROOT", ""),
    r"C:\Users\KING\Projects\TESSERACT-py",
    r"C:\Users\KING\Projects\TESSERACT",
)


def resolve_root() -> Path:
    """The directory that actually holds the Python app."""
    for cand in _ROOT_CANDIDATES:
        if not cand:
            continue
        p = Path(cand)
        if (p / "server.py").is_file():
            return p
    # Nothing had server.py. Return the first real candidate so the
    # error message names a path that exists.
    for cand in _ROOT_CANDIDATES:
        if cand and Path(cand).is_dir():
            return Path(cand)
    return Path(_ROOT_CANDIDATES[0])


ROOT = resolve_root()
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes" / "cron" / "output" / "tesseract_start.log"


def port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.4):
            return True
    except OSError:
        return False


def health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if health_ok():
        print("already_healthy")
        return 0

    py = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    if not (ROOT / "server.py").exists():
        print("missing server.py in", ROOT)
        print("candidates:", [c for c in _ROOT_CANDIDATES if c])
        return 2

    # free port if zombie
    if port_open() and not health_ok():
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
            for line in out.splitlines():
                if f":{PORT}" in line and "LISTENING" in line.upper():
                    pid = int(line.split()[-1])
                    subprocess.run(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-Command",
                            f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
                        ],
                        check=False,
                    )
                    print("killed", pid)
        except Exception as e:
            print("kill_err", e)
        time.sleep(1)

    logf = open(LOG, "a", encoding="utf-8")
    creation = 0
    if os.name == "nt":
        creation = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

    cmd = [str(py), "-m", "uvicorn", "server:app", f"--host={HOST}", f"--port={PORT}", "--log-level=info"]
    print("root", ROOT)
    print("starting", cmd)
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=logf,
        stderr=subprocess.STDOUT,
        creationflags=creation if os.name == "nt" else 0,
        close_fds=True,
    )
    print("spawned", proc.pid)
    for _ in range(40):
        if health_ok():
            print("health_ok")
            return 0
        time.sleep(0.5)
    print("health_timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
