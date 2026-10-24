#!/usr/bin/env python
"""
throttle-audit.py - Windows process throttling audit & safe-kill
Run as: python throttle-audit.py [--kill-safe] [--json]
"""
import sys, os, json, argparse, subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict

import psutil

LOG = Path(os.environ.get("THROTTLE_AUDIT_LOG",
                          r"C:\Users\KING\AppData\Local\hermes\audit\throttle.log"))
LOG.parent.mkdir(parents=True, exist_ok=True)

# Safe-kill whitelist (autostart bloat, no user data)
SAFE_KILL = {
    "PhoneExperienceHost.exe",
    "CrossDeviceService.exe",
    "GoogleDriveFS.exe",
    "OneDrive.exe",
    "Discord.exe",
    "Update.exe",
    "CCleanerBrowserUpdateCore.exe",
    "GeminiAppLauncher.exe",
}

# Always-protected processes (NEVER kill)
PROTECTED = {
    "MsMpEng.exe",      # Windows Defender
    "taskmgr.exe",
    "explorer.exe",
    "dwm.exe",
    "csrss.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
}


def proc_info(p) -> Dict:
    try:
        with p.oneshot():
            return {
                "pid": p.pid,
                "name": p.name(),
                "cpu": round(p.cpu_percent(interval=0.05), 1),
                "mem_mb": int(p.memory_info().rss / 1024 / 1024),
                "create_h": round((datetime.now() - datetime.fromtimestamp(p.create_time())).total_seconds() / 3600, 1),
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def list_throttle_candidates(top: int = 15) -> List[Dict]:
    """Return top CPU procs with CPU% and decision flag."""
    procs = []
    for p in psutil.process_iter():
        info = proc_info(p)
        if info:
            procs.append(info)
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    out = []
    for i in procs[:top]:
        name = i["name"]
        if name in PROTECTED:
            i["decision"] = "PROTECT"
        elif name in SAFE_KILL:
            i["decision"] = "SAFE-KILL"
        elif i["mem_mb"] > 1500 and i["cpu"] < 5:
            i["decision"] = "ASK (heavy idle)"
        elif i["cpu"] > 5000 and i["create_h"] > 24:
            i["decision"] = "INVESTIGATE"
        else:
            i["decision"] = "leave"
        out.append(i)
    return out


def kill_safe():
    killed = []
    for p in psutil.process_iter():
        try:
            if p.name() in SAFE_KILL:
                p.kill()
                killed.append({"pid": p.pid, "name": p.name()})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed


def check_services():
    """List which Windows services autostart bloat we can disable."""
    targets = [
        ("PhoneExperienceHostTask",
         r"\Microsoft\Windows\PhoneLink\PhoneExperienceHostTask"),
        ("CrossDeviceServiceTask",
         r"\Microsoft\Windows\CrossDevice\CrossDeviceServiceTask"),
    ]
    out = []
    for label, path in targets:
        try:
            r = subprocess.run(
                ["schtasks", "/Query", "/TN", path, "/FO", "LIST", "/V"],
                capture_output=True, text=True, timeout=5,
            )
            enabled = "Enabled" in r.stdout.split("Status:")[-1].split("\n")[0] if "Status:" in r.stdout else None
            out.append({"task": label, "path": path, "enabled": enabled})
        except Exception as e:
            out.append({"task": label, "path": path, "error": str(e)})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kill-safe", action="store_true",
                   help="kill processes in safe whitelist")
    p.add_argument("--json", action="store_true", help="JSON only output")
    p.add_argument("--log", action="store_true", help="append to audit log")
    args = p.parse_args()

    cands = list_throttle_candidates()
    services = check_services()
    killed = kill_safe() if args.kill_safe else []

    report = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "top_cpu": cands,
        "scheduled_tasks": services,
        "killed_now": killed,
    }

    if args.log:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report) + "\n")

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    # Human-readable
    print(f"=== THROTTLE AUDIT {report['ts']} ===")
    print(f"\nTop CPU processes:")
    for c in cands[:10]:
        print(f"  {c['cpu']:>8} cpu  {c['mem_mb']:>6} MB  "
              f"{c['create_h']:>6} h  [{c['decision']:>15}]  {c['name']}")
    print(f"\nScheduled tasks:")
    for s in services:
        print(f"  [{('ENABLED' if s.get('enabled') else 'disabled'):>8}] {s['task']}")
    if killed:
        print(f"\nKilled {len(killed)} processes: {[k['name'] for k in killed]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())