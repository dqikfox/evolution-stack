"""Minimal THRONE health JSON emitter for cron."""
import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "cron" / "output"
OUT.mkdir(parents=True, exist_ok=True)


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200, r.read(120).decode("utf-8", "ignore")
    except Exception as e:
        return False, type(e).__name__


def main():
    ts = datetime.now(timezone.utc).isoformat()
    services = {
        "ollama": port_open(11434),
        "openclaw": port_open(18789),
        "nexus": port_open(8650),
        "tesseract": port_open(8705),
    }
    nexus_ok, nexus_snip = http_ok("http://127.0.0.1:8650/health")
    tess_ok, tess_snip = http_ok("http://127.0.0.1:8705/health") if services["tesseract"] else (False, "down")

    # Auto-heal via separate scripts (avoid packing kill logic in this process)
    heals = {}
    scripts = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "scripts"
    if not nexus_ok:
        p = scripts / "restart_nexus.py"
        try:
            out = subprocess.check_output([sys.executable, str(p)], text=True, timeout=120, stderr=subprocess.STDOUT)
            heals["nexus"] = "ok" if "result OK" in out or "health_ok" in out else "fail"
        except Exception as e:
            heals["nexus"] = f"err:{e}"
        nexus_ok, nexus_snip = http_ok("http://127.0.0.1:8650/health")
        services["nexus"] = port_open(8650)
    if not tess_ok:
        p = scripts / "start_tesseract.py"
        try:
            out = subprocess.check_output([sys.executable, str(p)], text=True, timeout=90, stderr=subprocess.STDOUT)
            heals["tesseract"] = "ok" if ("health_ok" in out or "already_healthy" in out) else "fail"
        except Exception as e:
            heals["tesseract"] = f"err:{e}"
        tess_ok, tess_snip = http_ok("http://127.0.0.1:8705/health")
        services["tesseract"] = port_open(8705)

    alerts = []
    notices = []
    if not services["ollama"]:
        alerts.append("ollama:DOWN")
    if not services["openclaw"]:
        alerts.append("openclaw:DOWN")
    if not nexus_ok:
        alerts.append("nexus:UNHEALTHY")
    if not tess_ok:
        notices.append("tesseract:UNHEALTHY")
    for k, v in heals.items():
        notices.append(f"heal_{k}:{v}")

    state = {
        "ts": ts,
        "host": socket.gethostname(),
        "services": services,
        "http": {"nexus": nexus_ok, "tesseract": tess_ok, "nexus_snip": nexus_snip, "tess_snip": tess_snip},
        "heals": heals,
        "alerts": alerts,
        "notices": notices,
        "status": "ALERT" if alerts else ("DEGRADED" if notices else "OK"),
    }
    (OUT / "health_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    with (OUT / "health.log").open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {state['status']} {services} heals={heals}\n")
    print(json.dumps(state, separators=(",", ":")))
    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
