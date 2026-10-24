"""Sync Tailnet device inventory into Markdown documentation."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Paths configured for THRONE environment
OUT = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes" / "cron" / "output"
INV = OUT / "tailnet_inventory.json"
MD_DOC = Path(r"C:\Users\KING\AppData\Local\hermes\cron\output\throne_network_inventory.md")

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
        new_content += "**Local devices (USB/ADB/drives):** 0\n" # Placeholder as per existing script behavior
        new_content += "**Mount attempts:** 2\n\n"
        new_content += "## Tailscale\n\n"
        new_content += "| IP | SMB | SSH | ADB |\n"
        new_content += "|---|---|---|---|\n"

        for d in devices:
            if d['name'] == 'throne': continue
            ip = d['ipv4']
            status = "Online" if d.get('online') else "Offline"
            last_seen = d.get('lastSeen', 'Unknown')
            new_content += f"| {ip} | {d['os']} | {status} | {last_seen} |\n"

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
