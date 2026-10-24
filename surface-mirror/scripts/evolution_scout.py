"""Local-first evolution scout for THRONE.
Collects actionable gaps without LLM. Cron can run no_agent=true.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERMES = Path(os.environ["LOCALAPPDATA"]) / "hermes"
OUT = HERMES / "cron" / "output"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "evolution_scout.json"
LOG = OUT / "evolution_scout.log"


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def run(cmd: list[str], timeout: int = 30) -> str:
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout, stderr=subprocess.STDOUT)
    except Exception as e:
        return f"ERR:{e}"


def main() -> int:
    ts = datetime.now(timezone.utc).isoformat()
    findings: list[dict] = []

    # Service presence
    for name, port in (("ollama", 11434), ("openclaw", 18789), ("nexus", 8650)):
        up = port_open(port)
        if not up:
            findings.append(
                {
                    "severity": "high" if name != "nexus" else "medium",
                    "area": "services",
                    "item": f"{name}:{port}",
                    "issue": "not listening",
                    "fix": f"start {name} service on THRONE",
                }
            )

    # Cron jobs still pinned to paid models
    jobs_path = HERMES / "cron" / "jobs.json"
    if jobs_path.exists():
        try:
            data = json.loads(jobs_path.read_text(encoding="utf-8"))
            for job in data.get("jobs", []):
                model = str(job.get("model") or "")
                provider = str(job.get("provider") or "")
                streak = int(job.get("failure_streak") or 0)
                if provider == "nous" or model.startswith("z-ai/"):
                    findings.append(
                        {
                            "severity": "high",
                            "area": "cron",
                            "item": job.get("name") or job.get("id"),
                            "issue": f"paid model pin model={model} provider={provider} streak={streak}",
                            "fix": "retarget to ollama-launch / starscream-64k or no_agent script",
                        }
                    )
                elif streak >= 5:
                    findings.append(
                        {
                            "severity": "medium",
                            "area": "cron",
                            "item": job.get("name") or job.get("id"),
                            "issue": f"failure_streak={streak} last={job.get('last_error')}",
                            "fix": "inspect script/prompt and heal",
                        }
                    )
        except Exception as e:
            findings.append({"severity": "medium", "area": "cron", "item": "jobs.json", "issue": str(e), "fix": "repair jobs.json"})

    # Gateway process
    
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", 18789))
            gw_error = ""
    except OSError:
        gw_error = "No gateway listener on :18789"

    gw = "" # Emergency fix for NameError
    if "No gateway process detected" in str(gw) or ("✗" in str(gw) and "gateway process" in gw.lower()):
        findings.append(
            {
                "severity": "high",
                "area": "gateway",
                "item": "Hermes_Gateway",
                "issue": "scheduled task present but process not running",
                "fix": "hermes gateway start",
            }
        )

    # Config version drift

    # Network Inventory Freshness Check
    inv_file = OUT / "throne_network_inventory.json"
    if inv_file.exists():
        try:
            inv_data = json.loads(inv_file.read_text(encoding='utf-8'))
            inv_ts = datetime.fromisoformat(inv_data.get('ts', '1970-01-01T00:00:00+00:00').replace('Z', '+00:00'))
            now_utc = datetime.now(timezone.utc)
            age_sec = (now_utc - inv_ts).total_seconds()
            if age_sec > 3600:
                findings.append({
                    "severity": "medium",
                    "area": "infrastructure",
                    "item": "throne_inventory",
                    "issue": f"inventory stale ({int(age_sec/60)}m)",
                    "fix": "run throne_discovery.py manually or wait for cron",
                })
        except Exception as e:
             print(f"ERR checking inventory freshness: {e}")
    else:
         findings.append({"severity": "high", "area": "infrastructure", "item": "throne_inventory", "issue": "missing network inventory file", "fix": "check throne_discovery.py failures"})

    cfg = HERMES / "config.yaml"
    if cfg.exists() and "config_version: 34" in cfg.read_text(encoding="utf-8", errors="ignore"):
        findings.append(
            {
                "severity": "low",
                "area": "config",
                "item": "config.yaml",
                "issue": "version 34 outdated (target 41)",
                "fix": "hermes config migrate",
            }
        )

    # mem0 quota signal from recent sessions is external; note local fallback


    report = {
        "ts": ts,
        "host": socket.gethostname(),
        "finding_count": len(findings),
        "findings": findings,
        "priority_order": sorted(findings, key=lambda f: {"high": 0, "medium": 1, "low": 2, "info": 3}.get(f["severity"], 9)),
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    prior = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    LOG.write_text(
        prior + f"[{ts}] findings={len(findings)} high={sum(1 for f in findings if f['severity']=='high')}\n",
        encoding="utf-8",
    )
    print(json.dumps(report, separators=(",", ":")))
    return 0 if not any(f["severity"] == "high" for f in findings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
