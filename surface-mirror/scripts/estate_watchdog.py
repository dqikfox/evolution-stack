"""Keep the estate up, from a task that does not depend on any agent session.

The estate's automatic recovery was DEAD and nobody knew: both scheduled
tasks ran a bare `python`, and a Scheduled Task runs with a minimal
environment where `python` does not resolve. Both tasks had been failing
with 0x80070002 (file not found) while the scripts sat right there on
disk. The only symptom was a `Last Result` nobody read - and a service
outage that sat unattended for minutes.

This is the watchdog that actually heals the estate:

  * it reads the canonical registry (SERVICES.json), so the service list
    has exactly one source of truth,
  * it probes each healable service's health endpoint,
  * it restarts the ones that are down through their DOCUMENTED launcher
    (the same launcher the Startup shortcut, the healer and the agent all
    use - one launcher per service, always),
  * it writes a timestamped line per action to a durable log,
  * and it exits 0 when the check completed and every needed heal
    succeeded, 1 when a heal failed or the check itself broke. The exit
    code reports the WORK, not the weather: a service that was down and
    is now up is a successful run.

Run:  python estate_watchdog.py
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

REGISTRY = Path(r"E:\ultron-memory\infra\SERVICES.json")
LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "logs" / "estate_watchdog.log"
PROBE_TIMEOUT = 6
# The launcher waits up to 180s for the service's health endpoint before it
# gives up. The watchdog's budget MUST EXCEED the launcher's own budget, or
# the watchdog kills the launcher mid-wait and the service never comes up -
# which is exactly what happened: the watchdog's 165s timeout fired while
# the launcher was still waiting, and the launch died with the service down.
HEAL_WAIT = 240
LAUNCHER_BUDGET = HEAL_WAIT + 120


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def healthy(service: dict) -> bool:
    """The health endpoint, and the port, both have to answer.

    A port that answers is not proof of health - a wedged process can hold
    a port forever - so the endpoint has to answer too. A 401/403 still
    counts: the service is alive, it just wants credentials.
    """
    port = int(service.get("port") or 0)
    if not port or not port_open(port):
        return False
    url = service.get("health")
    if not url:
        return True
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as response:
            return response.status < 500
    except urllib.error.HTTPError:
        return True                     # it answered - it just refused
    except Exception:
        return False


def load_registry() -> list[dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [s for s in data.get("services", []) if s.get("status") != "retired"]


def heal(service: dict) -> bool:
    """Restart through the documented launcher. Never improvise a start path."""
    start = service.get("start") or {}
    path = start.get("path")
    if not path or not Path(path).exists():
        log(f"  {service.get('name')}: no usable start path ({path})")
        return False
    log(f"  {service.get('name')}: restarting via {path}")
    try:
        result = subprocess.run(["cmd.exe", "/c", path], capture_output=True,
                                text=True, timeout=LAUNCHER_BUDGET,
                                encoding="utf-8", errors="replace")
    except Exception as exc:
        log(f"  {service.get('name')}: the launcher failed to run: {exc}")
        return False
    deadline = time.time() + HEAL_WAIT
    while time.time() < deadline:
        if healthy(service):
            log(f"  {service.get('name')}: recovered on :{service.get('port')}")
            return True
        time.sleep(2.0)
    log(f"  {service.get('name')}: still down after the heal "
        f"(launcher rc={result.returncode})")
    for line in (result.stdout or "").strip().splitlines()[-4:]:
        log(f"    {line}")
    return False


def main() -> int:
    try:
        services = load_registry()
    except Exception as exc:
        log(f"the registry could not be read: {exc}")
        return 1
    log(f"estate check: {len(services)} services in the registry")
    healed, failed = [], []
    for service in services:
        name = service.get("name")
        start = service.get("start") or {}
        if not start.get("path"):
            # An operator-level service with no documented start path is not
            # a failure - it is a task for a human, and the gate reports it
            # on the host score. Failing the run for it would make the task
            # result meaningless.
            log(f"  {name} (:{service.get('port')}) is operator-level - "
                f"no start path, reported not healed")
            continue
        try:
            if healthy(service):
                continue
        except Exception as exc:
            log(f"  {name}: the health check broke: {exc}")
            failed.append(name)
            continue
        log(f"  {name} (:{service.get('port')}) is DOWN")
        (healed if heal(service) else failed).append(name)
    if healed:
        log(f"healed: {healed}")
    if failed:
        log(f"STILL DOWN: {failed}")
        return 1
    log("estate is healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
