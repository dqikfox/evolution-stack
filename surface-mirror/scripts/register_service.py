import sys
import json
import os
from pathlib import Path

def main():
    """
    Registers a service in the Hermes discovery registry to ensure it has 
    a documented start path (L13), making it 'healable' by the supervisor.
    Usage: python register_service.py <port> <name> <start_cmd>
    """
    if len(sys.argv) != 4:
        print("Usage: register_service.py <port> <name> <start_cmd>")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
        name = sys.argv[2]
        cmd = sys.argv[3]
    except ValueError:
        print("Error: Port must be an integer.")
        sys.exit(1)

    # Ensure registry directory exists within the local app data scope
    reg_dir = Path(os.getenv('LOCALAPPDATA')) / 'hermes' / 'registry'
    reg_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": name,
        "port": port,
        "start_cmd": cmd,
        "status": "stopped",
        "registered_at": os.path.getmtime(sys.argv[0]) if os.path.exists(sys.argv[0]) else 0,
        "description": f"Service {name} registered to provide a documented start path for discovery."
    }

    target_file = reg_dir / f"{port}.json"
    with open(target_file, 'w') as f:
        json.dump(payload, f, indent=4)

    print(f"[SUCCESS] Registered '{name}' on port {port}. Registry entry: {target_file}")

if __name__ == "__main__":
    main()