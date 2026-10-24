"""
LOCAL video generation pipeline — THRONE 2026-10-14
Local-first replacement for cloud video gen (xAI was the stopgap).

Flow:
 1. Evict starscream from VRAM (Ollama keep_alive=0 unload) — the flex pattern
 2. Launch ComfyUI headless (--listen 127.0.0.1:8188) from the portable install
 3. POST the LTX-Video t2v workflow (API format) to /prompt
 4. Poll history until done, fetch output (webp)
 5. ffmpeg webp frames -> mp4
 6. Reload starscream (warm /api/generate), stop ComfyUI

Usage: python local_video_gen.py "<prompt>" [output_name] [--keep]  (--keep = leave starscream unloaded)
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

COMFY_DIR = r"D:\ai\ComfyUI_windows_portable"
COMFY_PY = os.path.join(COMFY_DIR, "embedded_python", "python.exe") if os.path.exists(
    os.path.join(COMFY_DIR, "embedded_python")) else os.path.join(COMFY_DIR, "python", "python.exe")
COMFY_MAIN = os.path.join(COMFY_DIR, "ComfyUI", "main.py")
WORKFLOW = r"C:\Users\KING\AppData\Local\hermes\heretik\ltx_t2v_api.json"
OUT_DIR = None  # resolved after server start via /object_info? no — ComfyUI/output
MP4_DIR = r"C:\Users\KING\Videos\local-gen"
OLLAMA = "http://127.0.0.1:11434"
COMFY = "http://127.0.0.1:8188"


def http_json(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def unload_starscream():
    try:
        ps = http_json(f"{OLLAMA}/api/ps", timeout=5)
        loaded = [m["name"] for m in ps.get("models", [])]
        for name in loaded:
            print(f"[flex] unloading {name}")
            http_json(f"{OLLAMA}/api/generate", {
                "model": name, "keep_alive": 0,
                "prompt": "", "stream": False,
            }, timeout=120)
        return loaded
    except Exception as e:
        print(f"[flex] unload failed: {e}")
        return []


def reload_starscream(names):
    for name in names:
        print(f"[flex] reloading {name} (warm)")
        try:
            http_json(f"{OLLAMA}/api/generate", {
                "model": name, "prompt": "", "stream": False,
                "keep_alive": "24h",
            }, timeout=600)
        except Exception as e:
            print(f"[flex] reload {name} failed: {e}")


def wait_comfy(seconds=120):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            urllib.request.urlopen(f"{COMFY}/system_stats", timeout=3)
            print(f"[comfy] up in {time.time()-t0:.1f}s")
            return True
        except OSError:
            time.sleep(2)
    return False


def main():
    keep_unloaded = "--keep" in sys.argv
    prompt = sys.argv[1] if len(sys.argv) > 1 else None
    out_name = sys.argv[2] if len(sys.argv) > 2 else f"local_gen_{int(time.time())}"
    if not prompt:
        print("usage: local_video_gen.py \"<prompt>\" [output_name] [--keep]")
        sys.exit(2)

    os.makedirs(MP4_DIR, exist_ok=True)
    wf = json.load(open(WORKFLOW, encoding="utf-8"))
    wf["6"]["inputs"]["text"] = prompt  # positive CLIPTextEncode

    evicted = [] if keep_unloaded else unload_starscream()

    comfy = subprocess.Popen(
        [COMFY_PY, COMFY_MAIN, "--listen", "127.0.0.1", "--port", "8188",
         "--output-directory", MP4_DIR],
        cwd=os.path.dirname(COMFY_MAIN),
        stdout=open(r"D:\ai\comfy_run.log", "ab"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        if not wait_comfy():
            print("[comfy] FAILED to start — see D:\\ai\\comfy_run.log")
            sys.exit(1)
        print("[comfy] queueing workflow")
        resp = http_json(f"{COMFY}/prompt", {"prompt": wf, "client_id": "throne-local"}, timeout=60)
        pid = resp["prompt_id"]
        print(f"[comfy] prompt_id={pid}")
        t0 = time.time()
        while time.time() - t0 < 3600:
            time.sleep(5)
            h = http_json(f"{COMFY}/history/{pid}", timeout=15)
            if pid in h:
                status = h[pid].get("status", {})
                if status.get("completed"):
                    outputs = h[pid]["outputs"]
                    for node_out in outputs.values():
                        for img in node_out.get("images", []):
                            fname = img["filename"]
                            src = os.path.join(MP4_DIR, fname)
                            base, _ = os.path.splitext(fname)
                            dst = os.path.join(MP4_DIR, out_name + ".mp4")
                            print(f"[ffmpeg] {src} -> {dst}")
                            rc = subprocess.run([
                                "ffmpeg", "-y", "-i", src,
                                "-vf", "fps=24,format=yuv420p",
                                "-c:v", "libx264", "-crf", "18", dst,
                            ], capture_output=True)
                            if rc.returncode == 0:
                                print(f"[done] {dst}")
                                print(f"MP4_PATH={dst}")
                            else:
                                print(f"[ffmpeg] failed rc={rc.returncode}: {rc.stderr.decode()[-500:]}")
                            break
                    return
                if status.get("status_str") == "error":
                    print(f"[comfy] ERROR: {json.dumps(status)[:500]}")
                    sys.exit(1)
            print(f"[comfy] {int(time.time()-t0)}s…")
        print("[comfy] timed out after 1h")
        sys.exit(1)
    finally:
        comfy.terminate()
        if evicted:
            reload_starscream(evicted)


if __name__ == "__main__":
    main()