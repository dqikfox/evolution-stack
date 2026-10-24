
import subprocess
import time
import socket

def clean_and_check(port):
    try:
        output = subprocess.check_output(['cmd', '/c', f'netstat -ano | findstr :{port}'], stderr=subprocess.STDOUT).decode()
        lines = output.strip().split('\n')
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[4]
                print(f"Found PID {pid} on port {int(port)}. Killing...")
                subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
        return True
    except Exception as e:
        print(f"No process found or error during cleanup: {e}")
        return False

def run_test():
    port = 8650
    print("--- STEP 1: CLEANUP ---")
    clean_and_check(port)

    time.sleep(3) # Extra time for Windows kernel to release TCP state

    print("\n--- STEP 2: VERIFY FREE ---")
    res = subprocess.run(['cmd', '/c', f'netstat -ano | findstr :{port}'], capture_output=True, text=True)
    if not res.stdout.strip():
        print(f"Port {port} is confirmed FREE.")
    else:
        print(f"PORT STILL BUSY:\n{res.stdout}")
        return False

    print("\n--- STEP 3: ATTEMPT RESTART VIA VENV DIRECTLY (NO WRAPPER) ---")
    # Using forward slashes to avoid unicodeescape error in the script itself
    cmd_to_run = "C:/Users/KING/.cache/nexus-venv/Scripts/python.exe -m uvicorn server:app --host 127.0.0.1 --port 8650"
    try:
        proc = subprocess.Popen(['cmd', '/c', f'cd Q:/ultron-memory/nexus-core && {cmd_to_run}'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(f"Started process with PID {proc.pid}. Monitoring for 15s...")
        for _ in range(15):
            time.sleep(1)
            # Check if the port is listening now
            check_res = subprocess.run(['cmd', '/c', f'netstat -ano | findstr :{port}'], capture_output=True, text=True)
            if "LISTENING" in check_res.stdout:
                print("\n[SUCCESS] Nexus IS LISTENING on 8650!")
                return True
            else:
                print(".", end="", flush=True)
        
        print("\n[FAILURE] Port still not listening after 15 seconds.")
        return False
    except Exception as e:
        print(f"\nError during manual start attempt: {e}")
        return False

if __name__ == '__main__':
    run_test()
