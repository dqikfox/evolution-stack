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
ROOT = Path(r"C:\Users\KING\Projects\TESSERACT")
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
        print("missing server.py")
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
