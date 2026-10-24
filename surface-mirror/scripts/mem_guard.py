import psutil
import requests
import time
import subprocess

THRESHOLD = 90.0  # Percent
CHECK_INTERVAL = 60 # Seconds
OLLAMA_URL = "http://localhost:11434/api/tags"

def get_mem():
    return psutil.virtual_memory().percent

    print("[MEM_GUARD] High memory detected! Requesting Ollama model unload...")
    try:
        import requests
        import subprocess
        print("[MEM_GUARD] Checking running models via 'ollama ps'...")
        ps_res = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
        if ps_res.returncode == 0:
            lines = ps_res.stdout.strip().split('\n')
            if len(lines) > 1: # more than header
                for line in lines[1:]:
                    parts = line.split()
                    model_name = parts[0]
                    print(f"[MEM_GUARD] Found active model: {model_name}. Sending unload request (keep_alive=0)...")
                    post_res = requests.post("http://localhost:11434/api/generate", 
                                            json={"model": model_name, "keep_alive": 0},
                                            timeout=5)
                    if post_res.status_code == 200:
                        print(f"[MEM_GUARD] Unload signal sent for {model_name} (Status: {post_res.status_code})")
                    else:
                        print(f"[MEM_GUARD] Failed to unload {model_name}. Status: {post_res.status_code}")
            else:
                print("[MEM_GUARD] No models found in 'ollama ps' output.")
        else:
            err_msg = getattr(ps_res, 'stderr', 'Unknown error')
            print(f"[MEM_GUARD] Error running ollama ps: {err_msg}")
    except Exception as e:
        print(f"[MEM_GARD] Error during scale_down execution: {e}")
    try:
        # Try to see what's running
        res = requests.get(OLLAMA_URL, timeout=5)
        if res.status_code == 200:
            models = res.json().get('models', [])
            for m in models:
                print(f"[MEM_GUARD] Found model: {m['name']}. Requesting unloading (simulated via API if supported/possible)...")
                # Note: Currently Ollama doesn't have a direct 'unload' endpoint via REST for all versions, 
                # but we can trigger a process restart or use a custom management script to clear the cache.
    except Exception as e:
        print(f"[MEM_GUARD] Error checking Ollama: {e}")

def main():
    print("[MEM_GUARD] Started monitoring memory...")
    while True:
        current_mem = get_mem()
        if current_mem > THRESHOLD:
            print(f"[ALERT] Memory at {current_mem}%!")
            scale_down()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()