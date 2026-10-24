import os
import socket
import time
from pathlib import Path
import sys

def main():
    """
    Verifies service health by combining port probing with supervisor status checks.
    Implements L24 (consecutive probes) and L13 (status file awareness).
    """
    if len(sys.argv) < 3:
        print("Usage: verify_tesseract_liveness.py <port> <service_name>")
        sys.exit(1)

    target_port = int(sys.argv[1])
    service_name = sys.argv[2]
    
    # L24: A single failed probe must be confirmed by consecutive probes before announcing outage
    is_port_open = False
    for attempt in range(3):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', target_port)) == 0:
                is_port_open = True
                break
        # Small sleep between retries to allow for transient network/OS jitter.
        # This must sit OUTSIDE the `with` block: a `with` statement has no
        # `else` clause, so pairing it there is a SyntaxError.
        time.sleep(0.2)

    if is_port_open:
        sys.exit(0)

    # L13: If port is closed, check if the supervisor is currently in a 'restarting' loop.
    # This prevents reporting 'down' during the brief window when a process has died 
    # but the supervisor (which manages it) hasn't finished spawning the new instance.
    appdata = os.getenv('LOCALAPPDATA')
    status_file = Path(appdata) / "hermes" / "services" / f"{service_name}.status"
    
    if status_file.exists():
        try:
            with open(status_file, 'r') as f:
                state = f.read().strip()
                if state == "restarting":
                    print(f"[INFO] {service_name} port closed, but supervisor reports 'restarting'. Skipping outage alert.")
                    sys.exit(0)
        except Exception:
            pass # If the file is locked or unreadable, default to safety (fail).

    # If no evidence of a managed restart exists and the port is dead, it's an actual failure.
    print(f"[ERROR] Service {service_name} on port {target_port} is unreachable and not in recovery.")
    sys.exit(1)

if __name__ == "__main__":
    main()