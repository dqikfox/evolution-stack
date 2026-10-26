"""Remote peers are part of the estate, not a side quest.

THRONE is not alone. SHADOW (SHADOW-EOKGST4R) runs a full Hermes install
- a channels gateway, an Electron desktop, Ollama - on another machine,
reachable over the tailnet. Until a peer is in the registry, the estate
cannot see it, the gate does not cover it, and the watchdog cannot heal
it: it is an island that only exists when somebody remembers to look.

So a peer is modelled the same way a local service is: a name, a port, a
health endpoint, and a documented way to bring it back. The difference
is the transport. A local service is probed over loopback; a peer is
probed by asking the peer itself, over ssh, because the peer's
surfaces are bound to ITS loopback and are not reachable from here.

The rules that keep this honest:

  * A peer is matched by IP, never by name. A tailnet node registers
    under a different name than the hostname it reports (SHADOW is
    registered as "ultron-brain" and calls itself "shadow"), and the
    "online" flag is not the authority either - the network is.
  * The probe asks the PEER, over ssh, for its own health endpoint. A
    tailnet probe would answer "connection refused" for a service that
    is perfectly healthy and bound to 127.0.0.1.
  * The heal runs the peer's OWN canonical start path - a scheduled
    task on the far side - not a command invented here. The far side
    knows how to start its own service; THRONE does not.
  * A peer that cannot be reached is reported as unreachable, and the
    reason is carried with it. Silence is not health.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

# The command line is capped by Windows (~8191 characters), and the peer
# is a Windows box, so a remote script travels as base64 of UTF-16LE.
# Only SHORT scripts go this way: a peer probe is a few lines, and a
# long script belongs in the upload-and-run transport, not on a command
# line.


@dataclass
class PeerService:
    name: str
    port: int
    health: str | None = None
    heal_task: str | None = None
    critical: bool = False
    notes: str = ""


@dataclass
class Peer:
    name: str
    ip: str
    user: str
    key: str
    services: list[PeerService] = field(default_factory=list)
    notes: str = ""
    # How to bring the peer INTO EXISTENCE, for a peer that is not a
    # machine on the desk but a rented node that is stopped when it is
    # idle. The command runs HERE, on THRONE, because the thing that
    # starts a rented node is the provider's own control plane, and the
    # provider does not know how to start itself.
    wake: list[str] = field(default_factory=list)
    wake_timeout: int = 180

    @property
    def healable(self) -> bool:
        return any(s.heal_task for s in self.services)


def load() -> list[Peer]:
    """Read the peer registry. An absent registry means no peers, not an error."""
    reg = paths.PEER_REGISTRY
    if not reg.exists():
        return []
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    peers: list[Peer] = []
    for name, host in data.items():
        if name.startswith("_") or not isinstance(host, dict):
            continue
        services = []
        for svc in host.get("services", []) or []:
            services.append(PeerService(
                name=svc.get("name", "?"),
                port=int(svc.get("port", 0)),
                health=svc.get("health"),
                heal_task=svc.get("heal_task"),
                critical=bool(svc.get("critical", False)),
                notes=svc.get("notes", ""),
            ))
        wake = host.get("wake") or []
        if isinstance(wake, str):
            wake = [wake]
        peers.append(Peer(
            name=name,
            ip=host.get("ip", ""),
            user=host.get("user", ""),
            key=host.get("key", ""),
            services=services,
            notes=host.get("notes", ""),
            wake=list(wake),
            wake_timeout=int(host.get("wake_timeout", 180)),
        ))
    return peers


def ssh_script(peer: Peer, script: str, timeout: int = 45) -> tuple[int, str, str]:
    """Run a short PowerShell script on the peer and return (rc, stdout, stderr)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new",
           "-i", peer.key, f"{peer.user}@{peer.ip}",
           "powershell", "-NoProfile", "-EncodedCommand", encoded]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, "", f"the peer did not answer within {timeout}s"
    except FileNotFoundError:
        return 127, "", "ssh is not installed on this host"
    out = proc.stdout or ""
    for marker in ("#< CLIXML", "<Objs"):
        if marker in out:
            out = out.split(marker)[0]
    lines = [l for l in out.splitlines()
             if "post-quantum key exchange" not in l]
    return proc.returncode, "\n".join(lines).strip(), (proc.stderr or "").strip()


def reachable(peer: Peer, timeout: int = 20) -> tuple[bool, str]:
    """Can the peer be talked to at all?

    A peer that cannot be reached is a different fact from a peer whose
    service is down, and the difference decides what to do about it. An
    unreachable peer cannot be healed by anyone, so it is not a gate
    failure - it is the machine being away. A reachable peer with a dead
    service CAN be healed, so it is.
    """
    rc, out, err = ssh_script(peer, "Write-Output 'here'", timeout=timeout)
    if rc == 0 and "here" in out:
        return True, "reachable"
    detail = (err or out or "no answer").strip()
    if "timed out" in detail or "Connection refused" in detail or "No route" in detail:
        return False, "the peer is unreachable"
    return False, detail[:140] or "no answer"


def wake_peer(peer: Peer) -> tuple[bool, str]:
    """Bring a stopped peer into existence, if it knows how.

    A rented node is a peer that is switched off when it is idle, and
    that is the whole point: you pay for the GPU only while the work
    is happening. The wake command runs here, on THRONE, because the
    provider's control plane is what starts it - and a peer that is
    simply switched off cannot run its own wake command.
    """
    if not peer.wake:
        return False, "the peer has no wake command"
    try:
        result = subprocess.run(peer.wake, capture_output=True, text=True,
                                timeout=peer.wake_timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "the wake command did not finish in %ds" % peer.wake_timeout
    except FileNotFoundError as exc:
        return False, "the wake command is not installed: %s" % exc
    out = (result.stdout or "").strip()
    if result.returncode != 0:
        return False, ((result.stderr or out or "the wake command failed").strip()[:140])
    return True, (out[:140] or "waking")


def wait_for_peer(peer: Peer, timeout: int = 240) -> tuple[bool, str]:
    """Wait for a woken peer to answer on the tailnet."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, why = reachable(peer, timeout=15)
        if ok:
            return True, "the peer answered"
        time.sleep(10)
    return False, "the peer did not answer within %ds" % timeout


def probe(peer: Peer, service: PeerService, timeout: int = 45) -> tuple[str, str]:
    """Ask the peer whether its own service is healthy.

    The peer answers for itself. A probe from here would see a closed
    port for a service bound to the peer's loopback, and would call a
    healthy service down.

    Returns a STATE, not a boolean, because there are three of them:
    "up", "down" (the peer is there and the service is not), and
    "unreachable" (the peer itself is not answering).
    """
    if not service.health:
        return "down", "no health endpoint is registered"
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "try { $r = Invoke-WebRequest -Uri '%s' -TimeoutSec 8 -UseBasicParsing;"
        " 'HTTP ' + [int]$r.StatusCode + ' ' + (($r.Content -replace '\\s+',' ').Substring(0,[Math]::Min(120,$r.Content.Length)))"
        " } catch { 'DOWN ' + $_.Exception.Message.Substring(0,[Math]::Min(90,$_.Exception.Message.Length)) }"
    ) % service.health
    rc, out, err = ssh_script(peer, script, timeout=timeout)
    if rc != 0:
        detail = (err or out or "the peer did not answer").strip()
        if "timed out" in detail or "Connection refused" in detail or "No route" in detail:
            return "unreachable", "the peer is unreachable"
        return "unreachable", detail[:140]
    if out.startswith("HTTP 200"):
        return "up", out[:140]
    return "down", out.strip()[:140] or "no answer"


def heal(peer: Peer, service: PeerService, wait_s: int = 40) -> tuple[bool, str]:
    """Start the peer's service using the PEER's own start path.

    The far side owns the start path - a scheduled task there, which
    knows the interpreter, the working directory and the log file. A
    command invented here would be a second, competing way to start the
    same service.
    """
    if not service.heal_task:
        return False, "no start path is registered on the peer"
    ok, why = reachable(peer)
    if not ok:
        return False, "cannot heal: " + why
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Start-ScheduledTask -TaskName '%s';"
        "'started task %s'"
    ) % (service.heal_task, service.heal_task)
    rc, out, err = ssh_script(peer, script, timeout=45)
    if rc != 0:
        return False, (err or "the start task could not be run").strip()[:140]

    deadline = time.time() + wait_s
    last = ""
    while time.time() < deadline:
        time.sleep(5)
        ok, detail = probe(peer, service, timeout=30)
        last = detail
        if ok:
            return True, "recovered: " + detail[:100]
    return False, "the peer did not come back within %ds (%s)" % (wait_s, last[:90])


def survey(auto_heal: bool = False) -> list[dict]:
    """Check every registered peer service, in the same shape as the
    local service survey so one consumer can read both.

    A peer that is unreachable is reported as such and is NOT healed:
    there is nobody on the far side to run the start task, and a heal
    that cannot possibly work is just a slow way to fail.
    """
    out = []
    for peer in load():
        t_peer = time.time()
        peer_up, peer_detail = reachable(peer)
        if not peer_up and auto_heal and peer.wake:
            # A peer that is stopped and knows how to be woken is not a
            # failure - it is a peer that is not being paid for right
            # now. Waking it is the heal.
            good, message = wake_peer(peer)
            if good:
                peer_detail = "waking: " + message
                peer_up, wake_detail = wait_for_peer(peer)
                if not peer_up:
                    peer_detail = "woken, but " + wake_detail
        peer_cost = time.time() - t_peer
        for service in peer.services:
            t0 = time.time() - peer_cost
            healed = ""
            if peer_up:
                state, detail = probe(peer, service)
            else:
                state, detail = "unreachable", peer_detail
            if state == "down" and auto_heal and service.heal_task:
                good, message = heal(peer, service)
                healed = message
                state = "up" if good else "down"
            out.append({
                "name": "%s/%s" % (peer.name, service.name),
                "peer": peer.name,
                "ip": peer.ip,
                "port": service.port,
                "status": state,
                "kind": "peer",
                "peer_reachable": peer_up,
                "healable": bool(service.heal_task) and peer_up,
                "critical": service.critical,
                "detail": detail[:140],
                "healed": healed,
                "elapsed": round(time.time() - t0, 2),
                "notes": service.notes[:120],
            })
    return out


def write_state(rows: list[dict] | None = None) -> str:
    """Publish the peer state where another system can read it.

    The state lives under the evolution stack's own directory because
    the evolution stack is its writer: a file read by a gate must live
    under a directory owned by whoever writes it, not in another
    system's pruning domain.

    The file carries its own age. A reader that shows a peer state from
    an hour ago as if it were current is worse than a reader that shows
    nothing, so the age travels with the data.
    """
    rows = survey() if rows is None else rows
    payload = {
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "peers": rows,
    }
    state_dir = paths.STACK / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / "peers.json"
    # written atomically: a reader must never see a half-written file
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(target)
    return str(target)


def read_state() -> dict:
    """Read the published peer state, with its age."""
    target = paths.STACK / "state" / "peers.json"
    if not target.exists():
        return {"generated_at": 0, "peers": [], "stale": True}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"generated_at": 0, "peers": [], "stale": True}
    age = time.time() - float(data.get("generated_at") or 0)
    data["age_seconds"] = round(age, 1)
    data["stale"] = age > 900  # older than a quarter of an hour is history, not state
    return data


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Probe (and optionally heal) the remote peers.")
    ap.add_argument("--heal", action="store_true",
                    help="start a peer's own start task when its service is down")
    ap.add_argument("--compact", action="store_true", help="one line per peer service")
    ap.add_argument("--no-state", action="store_true",
                    help="do not publish the peer state file")
    args = ap.parse_args()

    rows = survey(auto_heal=args.heal)
    if not args.no_state:
        write_state(rows)
    if args.compact:
        for row in rows:
            print(f"{row['status']:<12} {row['name']:<24} {row['detail'][:80]}")
    else:
        # machine-readable, so another process can act on it
        print(json.dumps(rows, indent=2))
