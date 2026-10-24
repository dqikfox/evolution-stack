import os
import subprocess
import time
import socket
import urllib.request
from pathlib import Path

PORT = 8650
HOST = '127.0.0.1'
LOG = "C:/Users/KING/AppData/Local/hermes/cron/output/nexus_restart.log"
import glob
NEXUS_DIR = Path("E:/ultron-memory/nexus-core")
VENV_PY = str(NEXUS_DIR / ".venv" / "Scripts" / "python.exe")

def logf(msg):
    import datetime
    with open(LOG, 'a', encoding='utf-8') as f:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{now} | {msg}\n")
    print(msg)

def free_port(port):
    print(f"[RESTART] Clearing port {port}...")
    subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
    res = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
    if res.stdout.strip():
        pid = res.stdout.split()[-1]
        print(f"[RESTART] Killing PID {pid}...")
        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, text=True)
        time.sleep(2)

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) != 0

def restart_nexus():
    logf("Starting nexus restart procedure.")
    if not (NEXUS_DIR / "server.py").exists():
        logf(f"ERROR: Missing server.py in {NEXUS_DIR}")
        return 1
    
    free_port(PORT)
    
    try:
        # Verify it is actually free
        with socket.socket() as s:
            s.bind((HOST, PORT))
        logf(f"Port {PORT} is confirmed FREE via bind test.")
    except OSError as e:
        logf(f"CRITICAL: Port {PORT} still busy after kill attempt: {e}")
        return 2

    cmd = [VENV_PY, "-m", "uvicorn", "server:app", "--host", HOST, "--port", str(PORT)]
    logf(f"Launching command: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(NEXUS_DIR)
    health_url = f"http://{HOST}:{PORT}/health"
    
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=open(LOG, 'a'),
            stderr=subprocess.STDOUT,
            creationflags=0x00000200 | 0x0800 # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        )
        logf("Launched uvicorn process ID {pid}. Checking health...".format(pid=proc.pid))
        
        for attempt in range(15):  # ~30 seconds total wait
            time.sleep(2)
            try:
                with urllib.request.urlopen(health_url, timeout=5) as response:
                    if response.getcode() == 200:
                        logf("SUCCESS: Nexus service responded with 200 OK on :8650!")
                        return 0
            except Exception:
                print(f"[RESTART] Waiting for socket to stabilize (attempt {attempt+1}/15)...")

        logf("FAILURE: Process launched but HTTP health check failed.")
        return 1
    except Exception as e:
        logf(f"ERROR during launch: {e}")
        return 3

if __name__ == "__main__":
    try:
        exit_code = restart_nexus()
        print(f"Restart script finished with code {exit_code}")
        exit(exit_code)
    except Exception as e:
        print(f"Fatal error in wrapper: {e}")
        exit(1)
