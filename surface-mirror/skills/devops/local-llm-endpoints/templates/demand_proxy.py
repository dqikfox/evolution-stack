#!/usr/bin/env python3
"""
Demand-proxy template — keep an LLM endpoint contract always answerable while the
RAM-heavy backend exists only while in use. Verified pattern (THRONE Heretik):
~10s cold start on first call, unchanged warm throughput, ~9GB RAM freed at idle.

Adapt the CONFIG block: backend executable/flags (copy from the existing launcher
script), contract port (the URL clients already use), backend port (an UNCLAIMED
port per the port map — check PORT_MAP.json/netstat first), idle timeout.
Deploy: kill the always-on backend, start this proxy in its place (background,
logon-autostart), clients need zero changes. Probe: GET /__demand_status on the
contract port.
"""
import http.server
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import os

# ---------------- CONFIG ----------------
PROXY_PORT = 8080            # the contract port clients already call
BACKEND_PORT = 8082          # UNCLAIMED port for the lazy backend (check port map first)
IDLE_TIMEOUT = 600           # seconds without traffic before the backend is killed
COLD_START_WAIT = 90          # max seconds to wait for backend /health
BACKEND_CMD = [
    r"D:\ai\llama.cpp\llama-server.exe",
    "--model", r"D:\ai\models\Qwen2.5-7B-Instruct.Q4_K_M.gguf",
    "--alias", "qwen2.5-7b-instruct",
    "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
    "--ctx-size", "8192", "--n-gpu-layers", "99", "--batch-size", "512",
    "--threads", "8", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
    "--flash-attn", "auto", "--jinja",
]
BACKEND_LOG = r"D:\ai\llama.cpp\demand_backend.log"
PROXY_LOG = r"D:\ai\llama.cpp\demand_proxy.log"
# ----------------------------------------

state_lock = threading.Lock()
backend_proc = None
last_used = time.time()


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(PROXY_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def backend_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/health", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def start_backend() -> bool:
    global backend_proc
    with state_lock:
        if backend_proc is not None and backend_proc.poll() is None and backend_healthy():
            return True
        if backend_proc is not None and backend_proc.poll() is not None:
            log(f"backend exited rc={backend_proc.returncode}; restarting")
        log(f"cold start: spawning backend on :{BACKEND_PORT}")
        t0 = time.time()
        logf = open(BACKEND_LOG, "ab")
        try:
            backend_proc = subprocess.Popen(
                BACKEND_CMD, stdout=logf, stderr=logf,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as e:
            log(f"spawn FAILED: {e}")
            return False
        deadline = time.time() + COLD_START_WAIT
        while time.time() < deadline:
            if backend_proc.poll() is not None:
                log(f"backend died during startup rc={backend_proc.returncode}")
                return False
            if backend_healthy():
                log(f"backend ready in {time.time()-t0:.1f}s (pid {backend_proc.pid})")
                return True
            time.sleep(0.5)
        log("backend failed to become healthy in time")
        return False


def stop_backend() -> None:
    global backend_proc
    with state_lock:
        if backend_proc is None:
            return
        p = backend_proc
        log(f"idle timeout: stopping backend pid {p.pid}")
        try:
            p.terminate()
            p.wait(timeout=10)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        backend_proc = None
        log("backend stopped — RAM released")


def watchdog() -> None:
    while True:
        time.sleep(30)
        if backend_proc is not None and (time.time() - last_used) > IDLE_TIMEOUT:
            stop_backend()


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self, include_body: bool) -> None:
        global last_used
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if include_body and length else None

        if not backend_healthy():
            if not start_backend():
                msg = json.dumps({"error": "backend failed to start"}).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return
        last_used = time.time()

        url = f"http://127.0.0.1:{BACKEND_PORT}{self.path}"
        req = urllib.request.Request(url, data=body, method=self.command)
        for h in ("Content-Type", "Authorization"):
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=600) as up:
                payload = up.read()
                self.send_response(up.status)
                self.send_header("Content-Type", up.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (urllib.error.URLError, OSError) as e:
            msg = json.dumps({"error": f"backend unreachable: {e}"}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self.path == "/__demand_status":
            info = {
                "proxy": "up",
                "backend_running": backend_proc is not None and backend_proc.poll() is None,
                "backend_pid": backend_proc.pid if backend_proc else None,
                "idle_seconds_left": max(0, int(IDLE_TIMEOUT - (time.time() - last_used))),
            }
            payload = json.dumps(info).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._forward(include_body=False)

    def do_POST(self):
        self._forward(include_body=True)

    def do_OPTIONS(self):
        self._forward(include_body=False)

    def log_message(self, fmt, *args):
        pass


def main() -> None:
    log(f"demand proxy starting on 127.0.0.1:{PROXY_PORT} (backend :{BACKEND_PORT}, idle {IDLE_TIMEOUT}s)")
    threading.Thread(target=watchdog, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), Proxy)
    log("listening")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
