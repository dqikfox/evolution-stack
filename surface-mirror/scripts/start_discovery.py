import subprocess
import sys
import os

def main():
    """
    Implements L13: A service launcher that ensures no orphaned processes 
    are clinging to the port before starting a new instance.
    """
    port = 8660
    print(f"[*] Initializing discovery service on port {port}...")

    # L13 - Take the port back from any orphaned previous instances
    try:
        # Windows-specific taskkill for the specific TCP port
        subprocess.run(["taskkill", "/F", "/FI", f"tcpport eq {port}"], 
                        capture_output=True, check=False)
    except Exception as e:
        print(f"[!] Error cleaning up orphan: {e}")

    # Launching via module to ensure environment consistency (L09/L13 compliance)
    # We use a new process group so it can survive if this launcher exits.
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "discovery_service"],
            stdout=None,
            stderr=None,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print(f"[+] Discovery service started successfully (PID: {process.pid}).")
        print("[!] Monitoring active... press Ctrl+C to stop the launcher.")
        
        # Keep the launcher alive as a simple supervisor loop
        while process.poll() is None:
            import time
            time.sleep(2)
            if process.returncode != 0 and process.returncode is not None:
                print(f"[!] Service died with exit code {process.returncode}. Check logs.")
                break
    except Exception as e:
        print(f"[-] Failed to launch discovery service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()