"""Register the Pixel character studio in the two house registries.

PORT_MAP.json  - the port map: who owns which port, how it is started,
                 and how it is checked. Its rule is CHECK_PORT_MAP_FIRST:
                 a new service must be registered before it is started.

SERVICES.json  - the canonical start-path registry. The evolution loop
                 reads it: a service with a start path here is
                 gate-actionable, so the healer can bring it back.

Idempotent: running it twice leaves one entry, not two.
"""
from __future__ import annotations

import json
from pathlib import Path

INFRA = Path(r"E:\ultron-memory\infra")
PORT_MAP = INFRA / "PORT_MAP.json"
SERVICES = INFRA / "SERVICES.json"

PORT = 8520
NAME = "pixel"
LAUNCHER = r"C:\Users\KING\AppData\Local\hermes\scripts\start_pixel.cmd"
HEALTH = "http://127.0.0.1:8520/api/state"
TODAY = "2026-10-25"

PORT_MAP_ENTRY = {
    "name": NAME,
    "port": PORT,
    "description": "Pixel character studio (portrait characters + local procedural generation)",
    "protocol": "http",
    "start": LAUNCHER,
    "health": HEALTH,
    "status": "up",
    "note": ("Supervised by pixel_supervisor.py, which restarts the studio if it "
             "dies and refuses to run a second copy (exit code 3). The launcher "
             "probes /api/state for 'activeCharacter' before it reclaims, and the "
             "reclaim refuses a port holder that is not ours. The studio reports "
             "its own supervision in /api/state."),
}

SERVICES_ENTRY = {
    "name": NAME,
    "port": PORT,
    "owner": "pixel",
    "status": "up",
    "start": {"type": "cmd", "path": LAUNCHER},
    "health": HEALTH,
    "critical": False,
    "notes": ("Character studio on the house interpreter (stdlib only; Pillow "
              "optional). Local procedural generation; GPU work happens in "
              "ComfyUI on demand, so the service itself is cheap to keep up. "
              "Supervised: pixel_supervisor.py restarts it after a crash, "
              "replaces it if it wedges, and refuses a second supervisor."),
}

CHANGELOG_ENTRY = {
    "date": TODAY,
    "action": "Pixel character studio registered on :8520 with a canonical launcher",
    "reason": ("Pixel was a full application - characters, jobs, messages, assets, "
               "local generation - running as an unsupervised orphan since 00:16 "
               "and absent from both registries, so neither the healer nor the "
               "estate could see or restart it. Port 8520 was unassigned."),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(f"  wrote {path.name}")


def upsert(items: list, entry: dict, key: str = "name") -> None:
    for i, item in enumerate(items):
        if item.get(key) == entry[key]:
            items[i] = entry
            print(f"  updated {entry[key]}")
            return
    items.append(entry)
    print(f"  added {entry[key]}")


def main() -> int:
    pm = load(PORT_MAP)
    upsert(pm["services"], PORT_MAP_ENTRY)
    ports = [s.get("port") for s in pm["services"]]
    if ports.count(PORT) > 1:
        raise SystemExit(f"port {PORT} is claimed more than once - refusing to save")
    if not any(c.get("action") == CHANGELOG_ENTRY["action"] for c in pm.get("changelog", [])):
        pm.setdefault("changelog", []).append(CHANGELOG_ENTRY)
        print("  changelog entry added")
    save(PORT_MAP, pm)

    sv = load(SERVICES)
    upsert(sv["services"], SERVICES_ENTRY)
    save(SERVICES, sv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
