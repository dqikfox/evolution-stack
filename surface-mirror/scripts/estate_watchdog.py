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
# The remote peers, and the code that knows their rules. The peer survey
# lives in the evolution stack because that is where the peer model
# lives; the watchdog calls it rather than keeping a second copy of the
# rules, because a second copy drifts.
PEER_REGISTRY = Path(r"E:\ultron-memory\infra\REMOTE_AGENTS.json")
EVOLUTION = Path(r"E:\ultron-memory\evolution-stack")
LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "logs" / "estate_watchdog.log"
PROBE_TIMEOUT = 6
# The launcher waits up to 180s for the service's health endpoint before it
# gives up. The watchdog's budget MUST EXCEED the launcher's own budget, or
# the watchdog kills the launcher mid-wait and the service never comes up -
# which is exactly what happened: the watchdog's 165s timeout fired while
# the launcher was still waiting, and the launch died with the service down.
HEAL_WAIT = 240
LAUNCHER_BUDGET = HEAL_WAIT + 120

# The pause between the first failed probe and the confirmation probe. It
# has to be long enough that a service busy with real work has a chance to
# answer, and short enough that a genuinely dead service is not left down
# for long.
CONFIRM_DELAY = 20

# A per-service probe timeout overrides PROBE_TIMEOUT for services whose
# health endpoint does more than answer. NEXUS CORE's /health walks its
# components - the database, the Ollama roster, the embedding models - and
# that walk can outlast the 6s default. Probing a busy service with a
# timeout shorter than its own work is how a healthy service gets
# restarted.
PROBE_TIMEOUTS = {
    "nexus-core": 90,
    "nexus": 90,
}


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
    timeout = PROBE_TIMEOUTS.get(str(service.get("name") or "").lower(), PROBE_TIMEOUT)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
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
    args = start.get("args", "")
    if not path or not Path(path).exists():
        log(f"  {service.get('name')}: no usable start path ({path})")
        return False
    command = f"{path} {args}".strip()
    log(f"  {service.get('name')}: restarting via {command}")
    try:
        result = subprocess.run(["cmd.exe", "/c", command], capture_output=True,
                                text=True, timeout=LAUNCHER_BUDGET,
                                encoding="utf-8", errors="replace",
                                # stdin must NOT be inherited. Several of the
                                # house launchers end with "pause", and an
                                # inherited console makes that wait for a
                                # keypress that never comes - the heal would
                                # then burn its whole budget and report the
                                # service as still down when the launcher had
                                # actually worked. With stdin closed, "pause"
                                # returns at once.
                                stdin=subprocess.DEVNULL)
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


def check_peers() -> tuple[list, list]:
    """Probe the remote peers, and heal what the peers can heal.

    A peer that is UNREACHABLE is reported and not failed: the machine
    is away, nobody can start its service, and a watchdog that fails for
    that is a watchdog whose exit code means nothing. A peer that is
    reachable and whose service is down CAN be healed, because the far
    side has its own start path - and that is a failure if the heal
    does not work.
    """
    healed, failed = [], []
    if not PEER_REGISTRY.exists():
        return healed, failed
    try:
        result = subprocess.run(
            [sys.executable, "-m", "evo.peers", "--heal"],
            cwd=str(EVOLUTION), capture_output=True, text=True, timeout=HEAL_WAIT + 60,
            encoding="utf-8", errors="replace")
    except Exception as exc:
        log(f"  peers: the peer survey could not run: {exc}")
        return healed, failed
    try:
        rows = json.loads(result.stdout or "[]")
    except ValueError:
        log(f"  peers: the peer survey did not answer with a result "
            f"(rc={result.returncode})")
        for line in (result.stderr or "").strip().splitlines()[-3:]:
            log(f"    {line}")
        return healed, failed
    for row in rows:
        name = row.get("name", "?")
        state = row.get("status", "?")
        if state == "up":
            continue
        if state == "unreachable":
            log(f"  {name}: the peer is unreachable - reported, not healed")
            continue
        log(f"  {name} (:{row.get('port')}) is DOWN on the peer")
        if row.get("healed"):
            log(f"  {name}: {row['healed']}")
            healed.append(name)
        else:
            failed.append(name)
    return healed, failed


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
        if start.get("heal") is False:
            # An explicit opt-out. The service may have a start path and still
            # be unsafe to auto-heal - a GPU-heavy service that would starve
            # the agent's own model, for example. "has a start path" and
            # "should be auto-healed" are different questions, so the registry
            # states the answer instead of inferring it from the path.
            log(f"  {name} (:{service.get('port')}) is marked heal: false - "
                f"reported, deliberately not healed")
            continue
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
        # CONFIRM before healing. One failed probe is not proof of a dead
        # service: a service that is BUSY can fail a health check and be
        # perfectly healthy. The real case on 2026-10-27 was NEXUS CORE
        # running a vector reindex that re-embeds every note - that work
        # holds the collection and the health walk stalls behind it, so
        # the probe timed out and the watchdog RESTARTED a service that was
        # in the middle of legitimate work. Restarting it did not fix the
        # stall; it just destroyed the work in progress.
        #
        # So: probe again, and only heal a service that fails twice. A
        # service that answers the second probe was never down.
        log(f"  {name} (:{service.get('port')}) did not answer the first probe "
            f"- confirming before any heal")
        time.sleep(CONFIRM_DELAY)
        try:
            if healthy(service):
                log(f"  {name} (:{service.get('port')}) answered the confirmation "
                    f"probe - busy, not down. Not healed.")
                continue
        except Exception as exc:
            log(f"  {name}: the confirmation probe broke: {exc}")
        log(f"  {name} (:{service.get('port')}) is DOWN")
        (healed if heal(service) else failed).append(name)
    peers_healed, peers_failed = check_peers()
    if peers_healed:
        log(f"peers healed: {peers_healed}")
    if peers_failed:
        log(f"peers STILL DOWN: {peers_failed}")
    if healed:
        log(f"healed: {healed}")
    if failed or peers_failed:
        log(f"STILL DOWN: {failed + peers_failed}")
        return 1
    log("estate is healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
