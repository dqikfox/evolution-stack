"""Sync Tailnet device inventory into a Markdown summary.

It used to write throne_network_inventory.md - the same file
throne_discovery.py owns - which meant two writers for one artifact: the
fast tailnet refresh silently replaced the full inventory (LAN hosts,
USB/ADB devices, mount attempts) with a tailnet-only table, used the
wrong column headers (SMB | SSH | ADB over OS | status | last-seen), and
hardcoded the local-device and mount counts as literal 0 and 2.

Now: throne_discovery.py is the ONLY writer of
throne_network_inventory.md, and this script writes its own
tailnet_inventory.md with honest columns.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Paths configured for THRONE environment
OUT = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes" / "cron" / "output"
INV = OUT / "tailnet_inventory.json"
MD_DOC = OUT / "tailnet_inventory.md"

def main():
    if not INV.exists():
        print(f"[ERROR] Inventory file {INV} does not exist.")
        return 1
    
    try:
        with open(INV, 'r') as f:
            data = json.load(f)
        
        ts = data.get("ts", datetime.now().isoformat())
        devices = data.get("devices", [])
        # Sort for stability
        devices.sort(key=lambda x: x['name'])

        new_content = "# THRONE Network Inventory\n"
        new_content += f"_Last scan: {ts}_\n\n"
        new_content += "**Tailscale peers:** " + str(len([d for d in devices if d['name'] != 'throne'])) + " known\n"
        new_content += "**Source:** tailnet_inventory.json (tailnet only)\n"
        new_content += "**Full inventory:** throne_network_inventory.md (owned by throne_discovery.py)\n\n"
        new_content += "## Tailscale\n\n"
        # The columns are what the rows actually contain: the old header
        # claimed SMB | SSH | ADB over values that are os | status | last seen.
        new_content += "| Host | IP | OS | Status | Last seen |\n"
        new_content += "|---|---|---|---|---|\n"

        for d in devices:
            if d['name'] == 'throne': continue
            ip = d['ipv4']
            status = "Online" if d.get('online') else "Offline"
            last_seen = d.get('lastSeen', 'Unknown')
            new_content += f"| {d['name']} | {ip} | {d['os']} | {status} | {last_seen} |\n"

        MD_DOC.write_text(new_content, encoding="utf-8")
        print("[INFO] Throne inventory markdown updated.")
        return 0
    except Exception as e:
        import traceback
        with open(r"C:/Users/KING/AppData/Local/hermes/cron/logs/throne_inv_updater_errors.log", 'a', encoding='utf-8') as ef:
            ef.write('\n--- THRONE INV UPDATE FAILURE ---\n' + traceback.format_exc() + '\n------------------------------\n')
        print('[ERROR] Update failed and logged to C:/Users/KING/AppData/Local/hermes/cron/logs/throne_inv_updater_errors.log: ' + str(e))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
