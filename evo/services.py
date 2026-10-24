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
import subprocess
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

    @property
    def healable(self) -> bool:
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


def status_of(s: Service) -> str:
    if s.status == "retired":
        return "retired"
    if port_open(s.port):
        return "up"
    if s.status == "optional":
        return "optional"
    return "down"


def heal(s: Service, wait_s: int = 25) -> tuple[bool, str]:
    """Launch the documented start path and wait for the port to answer."""
    if not s.healable:
        return False, "no start path"
    p = Path(s.start_path)
    if not p.exists():
        return False, f"start path missing: {p}"
    try:
        if s.start_type == "cmd":
            args = ["cmd", "/c", str(p)]
            if s.start_args:
                args.append(s.start_args)
            subprocess.Popen(args, cwd=str(p.parent),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000)  # DETACHED_PROCESS
        else:  # python script
            # Some services need a specific interpreter: NEXUS only works on
            # the uv venv that has numpy + chromadb installed, and it must
            # run under its supervisor (run_nexus.py) so a crash self-heals.
            interpreter = s.start_interpreter or "python"
            if not Path(interpreter).exists():
                return False, f"interpreter missing: {interpreter}"
            subprocess.Popen([interpreter, str(p)], cwd=str(p.parent),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000)
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
