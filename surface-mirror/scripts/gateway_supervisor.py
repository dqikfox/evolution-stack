"""Start the Hermes gateway idempotently, through its documented start path.

Why this file exists
--------------------
The gateway owns the cron tick on a headless host, and the way it is started
matters more than it looks:

  * The Scheduled Task `Hermes_Gateway` runs `wscript -> Hermes_Gateway.vbs`,
    which detaches the real process (window style 0, wait False). The task's
    own process therefore exits immediately and reports SUCCESS, so the task's
    `RestartOnFailure` never fires. When the gateway dies, the task stays
    green and nothing restarts it. That is exactly what happened: the gateway
    exited with code 75 on 2026-10-24 and stayed dead for three days.
  * The estate watchdog only heals what is in SERVICES.json. The gateway was
    not in that registry, so the watchdog could not heal it either.

So the gateway gets ONE idempotent launcher, and every surface - the
Scheduled Task, the estate watchdog (SERVICES.json) and a human - uses it.

Idempotence contract
--------------------
  * gateway already alive and serving  -> print ALREADY, exit 0, start nothing
  * gateway dead                        -> start it through the VBS, wait for
                                          the health endpoint, exit 0
  * the start failed                    -> exit 1 (a heal that silently
                                          "succeeded" is worse than no heal)

The health endpoint is the gateway's own api_server platform. It is the one
surface that only answers when the gateway is genuinely up.

Run:  python gateway_supervisor.py
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\KING\AppData\Local\hermes"))
VBS = HERMES_HOME / "gateway-service" / "Hermes_Gateway.vbs"
LOCK = HERMES_HOME / "gateway.lock"
HEALTH_PORT = 8642
HEALTH_URL = f"http://127.0.0.1:{HEALTH_PORT}/health"
# The gateway compiles the platform adapters and warms the turn machinery on
# a cold start; it also has to win the runtime lock. 120s is the observed
# cold-start budget with the Telegram adapter online.
START_WAIT = 120
PROBE_TIMEOUT = 6


def log(message: str) -> None:
    print(f"[gateway_supervisor] {message}", flush=True)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def healthy() -> bool:
    """A port that answers is not proof of health - the endpoint must answer too."""
    if not port_open(HEALTH_PORT):
        return False
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=PROBE_TIMEOUT) as response:
            return response.status < 500
    except urllib.error.HTTPError:
        return True                      # it answered - it just refused
    except Exception:
        return False


def lock_pid() -> int | None:
    """The pid the gateway published in its runtime lock, if it is still alive."""
    try:
        data = json.loads(LOCK.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
    except Exception:
        return None
    if pid <= 0:
        return None
    try:
        import psutil
        return pid if psutil.pid_exists(pid) else None
    except Exception:
        return pid


def start() -> bool:
    """Start the gateway through the documented VBS (it detaches on purpose)."""
    if not VBS.is_file():
        log(f"FAILED: the start path is missing: {VBS}")
        return False
    log(f"starting the gateway via {VBS}")
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//Nologo", str(VBS)],
            cwd=str(HERMES_HOME),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"FAILED: the start path could not be run: {exc}")
        return False
    return True


def main() -> int:
    if healthy():
        log(f"ALREADY: the gateway is serving {HEALTH_URL}")
        return 0

    pid = lock_pid()
    if pid:
        log(f"the gateway process {pid} exists but is not serving - it is wedged; restarting it")
    else:
        log("the gateway is not running")

    if not start():
        return 1

    deadline = time.time() + START_WAIT
    while time.time() < deadline:
        if healthy():
            log(f"the gateway is up on :{HEALTH_PORT}")
            return 0
        time.sleep(3.0)

    log(f"the gateway did not answer {HEALTH_URL} within {START_WAIT}s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
