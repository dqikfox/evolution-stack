"""Service registry: health checks and autonomous healing.

E:\\ultron-memory\\infra\\SERVICES.json is the canonical start-path registry.
This module turns it into two things the evolution loop needs:

1. **Classification** - a service is either
   - `retired`        : no implementation exists (never checked, never failed)
   - `healable`       : has a start path -> gate-actionable, the loop may restart it
   - `operator`       : no start path -> reported on the host score only
2. **Healing** - `heal(name)` launches the documented start path and waits for
   the port to come up. Idempotent: a service that is already up is left alone.

Before this existed the loop could only *report* dead services. That is why
HERETIK :8080 and KRYSYS :8500 stayed down for days while the agent kept
writing notes about them instead of restarting them.
"""
from __future__ import annotations

import json
import socket
import urllib.request
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths


@dataclass
class Service:
    name: str
    port: int
    status: str            # up | down | retired | optional
    start_type: str        # cmd | script | app | none | unknown
    start_path: str | None
    start_args: str | None
    start_interpreter: str | None  # explicit interpreter for script starts
    health: str | None
    critical: bool
    notes: str
    # The registry's explicit opt-out: "start": {"heal": false} means
    # this service has a start path but must NOT be started
    # automatically. A start path is a fact; whether the house is
    # allowed to use it is a policy.
    heal: bool = True

    @property
    def healable(self) -> bool:
        """Can the house start this service on its own?

        A start path is necessary but not sufficient. The registry's
        `start.heal: false` is an explicit refusal, and it wins.

        ComfyUI is the reason. It has a start path, it is optional, and
        starting it holds about 17GB of the RTX 3090's VRAM - which
        evicts starscream-64k, the model the evolution loop is ITSELF
        running on. On 2026-10-27 the bench reported ComfyUI as a
        gate-actionable failure and the loop moved to start it, for a
        service that is SUPPOSED to be down.

        A service that is meant to be off must read as operator-level,
        not as a failure waiting to be healed.
        """
        if not self.heal:
            return False
        return self.start_type in ("cmd", "script") and bool(self.start_path)

    @property
    def kind(self) -> str:
        if self.status == "retired":
            return "retired"
        if self.healable:
            return "healable"
        return "operator"


def load() -> list[Service]:
    """Read the registry. Falls back to the built-in port map if absent."""
    svc: list[Service] = []
    reg = paths.SERVICES_REGISTRY
    if reg.exists():
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            for s in data.get("services", []):
                start = s.get("start") or {}
                svc.append(Service(
                    name=s.get("name", "?"),
                    port=int(s.get("port", 0)),
                    status=s.get("status", "up"),
                    start_type=start.get("type", "none"),
                    start_path=start.get("path"),
                    start_args=start.get("args"),
                    start_interpreter=start.get("interpreter"),
                    health=s.get("health"),
                    critical=bool(s.get("critical", False)),
                    notes=s.get("notes", ""),
                    heal=bool(start.get("heal", True)),
                ))
            return svc
        except Exception:
            pass
    # fallback: built-in map, everything operator-level
    for name, port in paths.CANONICAL_SERVICES.items():
        svc.append(Service(name=name, port=port, status="up", start_type="none",
                           start_path=None, start_args=None,
                           start_interpreter=None, health=None,
                           critical=False, notes="fallback: no registry"))
    return svc


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def health_body_ok(s: Service, timeout: float = 3.0) -> bool:
    """True when the service's health route answers with a usable body.

    A TCP connect is not health. The KRYSYS SPA answers /health with its own
    shell, so a port check reports it "up" while the API behind it is dead.
    When the registry names a health URL, the body must be fetched and must
    not say the service is not ready. A route that answers with HTML is a
    static file being served, not a service reporting itself healthy.
    """
    if not s.health:
        return True  # nothing to assert beyond the port
    try:
        with urllib.request.urlopen(s.health, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read(20000).decode("utf-8", "replace")
    except Exception:
        return False
    low = body.lower()
    if "not_ready" in low or '"ok":false' in low.replace(" ", ""):
        return False
    # A JSON health payload is the real answer. HTML means the route served a
    # page instead of the health endpoint.
    stripped = body.lstrip()
    if stripped.startswith("<"):
        return False
    return True


def status_of(s: Service) -> str:
    if s.status == "retired":
        return "retired"
    if not port_open(s.port):
        return "optional" if s.status == "optional" else "down"
    if not health_body_ok(s):
        # The port answers but the service does not report itself ready.
        return "optional" if s.status == "optional" else "down"
    return "up"


def clean_env() -> dict:
    """Environment for a spawned service: the agent's own paths stripped.

    The Hermes agent runtime injects PYTHONPATH into every child it spawns,
    pointing at the agent's interpreter directories. A service that then
    starts a project virtualenv resolves the AGENT's numpy/pydantic/fastapi
    instead of the project's own, which is how a test suite ends up
    validating against dependency versions the project does not ship.

    Strip it here so every service starts on its own interpreter's packages.
    """
    env = os.environ.copy()
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(var, None)
    return env


# Windows process-creation flags. DETACHED_PROCESS is 0x00000008.
# CREATE_NO_WINDOW is 0x08000000 - a DIFFERENT thing, and the constant
# that used to be passed here under a "# DETACHED_PROCESS" comment. It
# hides the console and does nothing else: the child stays in the
# caller's process group, so a service started by a heal inside a cron
# session inherits that session's lifetime and dies when the session is
# reaped. The comment was the bug's cover story.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

SPAWNER = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "scripts" / "spawn_detached.py"


def _spawn_detached(command: list[str], cwd: str, log_path: Path) -> bool:
    """Start the launcher fully detached from THIS process.

    The house spawner gives the child its own process group, closes the
    inherited handles and redirects stdio to files. It also EXITS
    immediately, which breaks the ancestry chain: the service is no
    longer a descendant of the session that asked for the heal, so the
    session can be reaped without taking the service down with it.

    A heal that leaves the service inside a short-lived session is a heal
    that works exactly once.
    """
    if SPAWNER.is_file():
        try:
            result = subprocess.run(
                [sys.executable, str(SPAWNER),
                 "--log", str(log_path),
                 "--err", str(log_path) + ".err",
                 "--cwd", cwd, "--"] + command,
                capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace")
            return result.returncode == 0
        except Exception:
            return False
    # No house spawner: fall back to the real detached flags rather than
    # to a constant that only hides the console.
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(command, cwd=cwd,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, env=clean_env(), creationflags=flags)
    return True


def heal(s: Service, wait_s: int = 25) -> tuple[bool, str]:
    """Launch the documented start path and wait for the port to answer."""
    if not s.heal:
        # The registry refused it. Say so, and say why the refusal
        # exists - otherwise this reads as a broken start path and
        # somebody will "fix" it by making the service healable again.
        return False, "registry opt-out (start.heal=false): not started on purpose"
    if not s.healable:
        return False, "no start path"
    p = Path(s.start_path)
    if not p.exists():
        return False, f"start path missing: {p}"
    try:
        env = clean_env()
        log_path = paths.HERMES / "logs" / f"heal_{s.name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if s.start_type == "cmd":
            args = ["cmd.exe", "/c", str(p)]
            if s.start_args:
                args.append(s.start_args)
            if not _spawn_detached(args, str(p.parent), log_path):
                return False, "the launcher could not be started"
        else:  # python script
            # Some services need a specific interpreter: NEXUS only works on
            # the uv venv that has numpy + chromadb installed, and it must
            # run under its supervisor (run_nexus.py) so a crash self-heals.
            interpreter = s.start_interpreter or "python"
            if not Path(interpreter).exists():
                return False, f"interpreter missing: {interpreter}"
            if not _spawn_detached([interpreter, str(p)], str(p.parent), log_path):
                return False, "the start script could not be started"
    except Exception as e:
        return False, f"launch failed: {e}"
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if port_open(s.port):
            return True, f"recovered :{s.port}"
        time.sleep(1.0)
    return False, f"still down after {wait_s}s"


def survey(auto_heal: bool = False) -> list[dict]:
    """Check every registered service. Optionally heal the healable ones."""
    out = []
    for s in load():
        st = status_of(s)
        healed = ""
        if st == "down" and auto_heal and s.healable:
            ok, msg = heal(s)
            healed = msg
            st = "up" if ok else "down"
        out.append({
            "name": s.name, "port": s.port, "status": st, "kind": s.kind,
            "healable": s.healable, "critical": s.critical,
            "start": s.start_path, "healed": healed, "notes": s.notes[:120],
            "interpreter": s.start_interpreter,
        })
    return out


if __name__ == "__main__":
    print(json.dumps(survey(), indent=2))
