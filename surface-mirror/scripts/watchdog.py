"""THRONE system health scout + auto-heal for wedged NEXUS.
Emits stable JSON for cron no_agent delivery. Exit 1 only on critical alerts.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "cron" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = OUT_DIR / "health_state.json"
LOG_PATH = OUT_DIR / "health.log"
RESTART_NEXUS = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "scripts" / "restart_nexus.py"

PORTS = {
    "ollama": 11434,
    "openclaw": 18789,
    "nexus": 8650,
    "tesseract": 8705,
    "heretik": 8080,
}

CRITICAL_UP = {"ollama", "openclaw", "heretik"}

# Default model Ollama should keep warm at all times
OLLAMA_HOT_MODEL = os.environ.get("OLLAMA_HOT_MODEL", "starscream-64k:latest")


def _ps(cmd: str) -> str:
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            timeout=20,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception as e:
        return f"ERR:{e}"


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(240).decode("utf-8", errors="ignore")
            return r.status == 200, body[:180]
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"


def disk_free_pct(drive: str) -> float | None:
    try:
        import shutil

        usage = shutil.disk_usage(f"{drive}:\\")
        return round(100.0 * usage.free / usage.total, 1)
    except Exception:
        return None


def heal_nexus() -> dict:
    if not RESTART_NEXUS.exists():
        return {"attempted": False, "error": "restart_nexus.py missing"}
    try:
        out = subprocess.check_output(
            [sys.executable, str(RESTART_NEXUS)],
            text=True,
            timeout=120,
            stderr=subprocess.STDOUT,
        )
        ok = "result OK" in out or "health_ok" in out
        return {"attempted": True, "ok": ok, "tail": out[-500:]}
    except Exception as e:
        return {"attempted": True, "ok": False, "error": str(e)}




def throne_inventory_health() -> dict:
    """Check THRONE discovery inventory for healthy state."""
    inv_path = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "cron" / "output" / "throne_network_inventory.json"
    if not inv_path.exists():
        return {"ok": False, "reason": "inventory file missing"}
    try:
        age = time.time() - inv_path.stat().st_mtime
        if age > 3600:  # >60 min stale
            return {"ok": False, "reason": f"inventory stale ({int(age/60)}m)"}
        data = json.loads(inv_path.read_text(encoding="utf-8"))
        mounts_ok = sum(1 for m in data.get("mounts", []) if m.get("mounted"))
        mounts_failed = sum(1 for m in data.get("mounts", []) if not m.get("mounted") and not m.get("skipped"))
        return {
            "ok": True,
            "age_sec": int(age),
            "lan": len(data.get("lan", [])),
            "tailnet": len(data.get("tailnet", [])),
            "mounts_ok": mounts_ok,
            "mounts_failed": mounts_failed,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}

def main() -> int:
    ts = datetime.now(timezone.utc).isoformat()
    cpu = _ps(
        "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"
    )
    mem = _ps(
        "$o=Get-CimInstance Win32_OperatingSystem; "
        "[math]::Round((($o.TotalVisibleMemorySize-$o.FreePhysicalMemory)/$o.TotalVisibleMemorySize)*100,1)"
    )
    try:
        cpu_f = float(cpu)
    except Exception:
        cpu_f = -1.0
    try:
        mem_f = float(mem)
    except Exception:
        mem_f = -1.0

    services = {name: port_open(port) for name, port in PORTS.items()}
    disks = {d: disk_free_pct(d) for d in ("C", "D", "Q", "U")}

    nexus_health_ok, nexus_health_body = http_ok("http://127.0.0.1:8650/health", timeout=5.0)
    tess_health_ok, tess_health_body = (False, "skip")
    if services.get("tesseract"):
        tess_health_ok, tess_health_body = http_ok("http://127.0.0.1:8705/health", timeout=4.0)

    # Heretik base URL must actually serve a /v1/models payload — open port isn't enough
    heretik_models_ok, heretik_models_body = (False, "skip")
    if services.get("heretik"):
        heretik_models_ok, heretik_models_body = http_ok(
            "http://127.0.0.1:8080/v1/models", timeout=4.0
        )

    # Auto-warm the default hot model so first user turn doesn't pay 5-15s load.
    # BUT only if nothing else is currently loaded — we only have 24GB VRAM and
    # thrashing the user's active model every 5 min is worse than a one-time load.
    starscream_warm = False
    starscream_skipped_busy = False
    if services.get("ollama"):
        try:
            # What's currently resident in VRAM?
            with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/ps", timeout=4.0
            ) as r:
                ps_payload = json.loads(r.read().decode())
            loaded = {m.get("name", "") for m in ps_payload.get("models", [])}
            if OLLAMA_HOT_MODEL in loaded:
                starscream_warm = True
            elif loaded:
                starscream_skipped_busy = True
            else:
                req = urllib.request.Request(
                    "http://127.0.0.1:11434/api/chat",
                    data=json.dumps({
                        "model": OLLAMA_HOT_MODEL,
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_predict": 1},
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120.0) as r:
                    starscream_warm = r.status == 200
        except Exception:
            starscream_warm = False

    throne_inv = throne_inventory_health()

    heal = None
    # TCP up but HTTP dead = classic NEXUS wedge; TCP down also heal
    if (not nexus_health_ok) or (not services.get("nexus")):
        heal = heal_nexus()
        time.sleep(1)
        services["nexus"] = port_open(PORTS["nexus"])
        nexus_health_ok, nexus_health_body = http_ok("http://127.0.0.1:8650/health", timeout=6.0)

    alerts: list[str] = []
    notices: list[str] = []

    if cpu_f >= 80:
        alerts.append(f"CPU {cpu_f}%")
    if mem_f >= 90:
        alerts.append(f"MEM {mem_f}%")
        print("[REFLEX] High memory detected. Checking for orphan llama-servers...")
        orphan_check = subprocess.run(["tasklist", "/FI", "IMAGENSAME eq llama-server.exe", "/FO", "LIST"], capture_output=True, text=True)
        if "No tasks are running" not in orphan_check.stdout:
            print(f"[REFLEX] Found active llama-servers:\\n{orphan_check.stdout}")
            for line in orphan_check.stdout.splitlines():
                if "PID" in line:
                    try:
                        pid = line.split()[2]
                        print(f"[WATCHDOG] Terminating orphan/extra llama-server (PID {pid}) for system stability...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, text=True)
                    except Exception as e:
                        print(f"[WATCHDOG] Failed to kill PID error: {e}")
            notices.append("memory_pressure_mitigation_triggered")
    for d, free in disks.items():
        if free is not None and free < 10:
            alerts.append(f"DISK {d}: free {free}%")

    for name in CRITICAL_UP:
        if not services.get(name):
            alerts.append(f"{name}:DOWN")

    if not nexus_health_ok:
        alerts.append("nexus:UNHEALTHY")
    elif not services.get("nexus"):
        notices.append("nexus:port_down")

    if not services.get("tesseract"):
        notices.append("tesseract:DOWN")
    elif not tess_health_ok:
        notices.append("tesseract:UNHEALTHY")

    if services.get("heretik") and not heretik_models_ok:
        notices.append("heretik:PORT_UP_BUT_API_DEAD")
    if not services.get("heretik"):
        notices.append("heretik:DOWN")
    if throne_inv.get("ok"):
        if throne_inv.get("mounts_failed", 0) > 0:
            notices.append(f"throne_mounts:{throne_inv['mounts_failed']}_FAILED")
        if throne_inv.get("age_sec", 0) > 900:
            notices.append(f"throne_inventory:{int(throne_inv['age_sec']/60)}m_stale")
    else:
        notices.append(f"throne_inventory:UNHEALTHY ({throne_inv.get('reason','?')})")

    if not starscream_warm:
        if starscream_skipped_busy:
            notices.append(f"starscream_warm:SKIPPED ({OLLAMA_HOT_MODEL} — other model in VRAM)")
        else:
            notices.append(f"starscream_warm:FAILED ({OLLAMA_HOT_MODEL})")


    if heal and heal.get("attempted"):
        notices.append("nexus_heal:" + ("ok" if heal.get("ok") else "fail"))

    state = {
        "ts": ts,
        "host": socket.gethostname(),
        "cpu_pct": cpu_f,
        "mem_pct": mem_f,
        "disks_free_pct": disks,
        "services": services,
        "throne_inv": throne_inv,
        "http": {
            "nexus_health": nexus_health_ok,
            "nexus_snip": nexus_health_body[:120],
            "tesseract_health": tess_health_ok,
            "heretik_models": heretik_models_ok,
            "heretik_snip": heretik_models_body[:120],
            "starscream_warm": starscream_warm,
        },
        "heal": heal,
        "alerts": alerts,
        "notices": notices,
        "status": "ALERT" if alerts else ("DEGRADED" if notices else "OK"),
    }

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    svc_bits = ",".join(f"{k}:{'up' if v else 'down'}" for k, v in services.items())
    alert_bits = "; ".join(alerts) if alerts else "none"
    notice_bits = "; ".join(notices) if notices else "none"
    line = (
        f"[{ts}] status={state['status']} cpu={cpu_f}% mem={mem_f}% "
        f"svc={{{svc_bits}}} alerts={alert_bits} notices={notice_bits}\n"
    )
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)

    print(json.dumps(state, separators=(",", ":")))
    if notices:
        print("NOTICES:", "; ".join(notices), file=sys.stderr)
    if alerts:
        print("ALERTS:", "; ".join(alerts), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
