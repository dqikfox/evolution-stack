import os
import subprocess
from datetime import datetime

def check_system():
    print(f"[{datetime.now()}] [WATCHDOG] Starting health audit...")
    
    # Check critical services using Windows sc query
    services = ['ollama', 'Tailscale']
    for svc in services:
        try:
            res = subprocess.run(['sc', 'query', svc], capture_output=True, text=True)
            if "RUNNING" in res.stdout:
                print(f"[OK] {svc} is active.")
            else:
                print(f"[!] ALERT: {svc} is DOWN or not found! Attempting restart...")
                subprocess.run(['cmd', '/c', f'net start {svc}'], check=False)
        except Exception as e:
            print(f"[!] Error checking service {svc}: {e}")

    # Check Disk Pressure on C: and D: (as defined in SOUL.md)
    for drive in ['C:', 'D:']:
        if os.path.exists(drive):
            try:
                import psutil 
                usage = psutil.disk_usage(drive)
                if usage.percent > 85:
                    print(f"[ALERT] High disk pressure on {drive}: {usage.percent}% used!")
            except Exception:
                pass # Fallback if psutil is not available/installed

    with open(r"C:\Users\KING\AppData\Local\hermes\scripts\throne_audit.log", "a") as log:
        log.write(f"[{datetime.now()}] Audit complete.\n")

if __name__ == '__main__':
    check_system()