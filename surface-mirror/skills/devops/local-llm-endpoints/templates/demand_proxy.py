"""
Demand-proxy template - keep an LLM endpoint contract always answerable while the
RAM-heavy backend exists only while in use. Verified pattern (THRONE Heretik):
~10s cold start on first inference call, unchanged warm throughput, ~9GB RAM freed
at idle.

Adapt the CONFIG block: backend executable/flags (copy from the existing launcher
script), contract port (the URL clients already use), backend port (an UNCLAIMED
port per the port map - check PORT_MAP.json/netstat first), idle timeout.
Deploy: kill the always-on backend, start this proxy in its place (background,
logon-autostart), clients need zero changes. Probe: GET /__demand_status on the
contract port.

Four rules the implementation MUST keep:
  1. /health is answered BY THE PROXY, from cached state, in milliseconds. A
     forwarded /health cold-starts the backend for a monitor's probe and keeps
     it resident forever.
  2. Only INFERENCE traffic refreshes the idle timer.
  3. A backend orphaned by a proxy restart is ADOPTED by PID (verified against
     the expected command line) so the reaper can release it.
  4. The idle reaper kills by PID, not only by the Popen handle it owns.
"""
import http.server
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import os
import sys

# ============================ CONFIG START ============================
# ADAPT THIS BLOCK: copy the flags from your existing launcher script, and
# pick a backend port that is UNCLAIMED in the port map.
PROXY_PORT = 8080            # the contract port clients already call
BACKEND_PORT = 8082          # UNCLAIMED port for the lazy backend
IDLE_TIMEOUT = 600           # seconds without inference before the backend is killed
COLD_START_WAIT = 90         # max seconds to wait for backend /health
LLAMA = r"D:\ai\llama.cpp\llama-server.exe"
MODEL = r"D:\ai\models\your-model.gguf"
START_CMD = [LLAMA, "--model", MODEL, "--alias", "your-model",
             "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
             "--ctx-size", "8192", "--n-gpu-layers", "99",
             "--batch-size", "512", "--threads", "8",
             "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
             "--flash-attn", "auto", "--jinja"]
BACKEND_LOG = r"D:\ai\llama.cpp\demand_backend.log"
PROXY_LOG = r"D:\ai\llama.cpp\demand_proxy.log"
# A path that CONTAINS one of these counts as real use of the backend.
# Health, status and model-list probes do NOT: they are how a monitor
# checks the contract, and letting them reset the idle timer means a
# health probe keeps a multi-GB backend resident forever.
USE_PATH_HINTS = ("completion", "embedding", "generate", "infer")
# ============================ CONFIG END =============================
# Overridable for testing and for a different deployment.
PROXY_PORT = int(os.environ.get("HERETIK_PROXY_PORT", PROXY_PORT))
BACKEND_PORT = int(os.environ.get("HERETIK_BACKEND_PORT", BACKEND_PORT))
IDLE_TIMEOUT = int(os.environ.get("HERETIK_IDLE_TIMEOUT", IDLE_TIMEOUT))

state_lock = threading.Lock()
backend_proc = None
backend_pid = None        # PID of a backend we did not spawn but have adopted
last_used = time.time()
cold_starting = False


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(PROXY_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


# The last known state of the backend, maintained by the proxy itself.
# /health reports THIS instead of probing: on a host whose firewall DROPs
# packets to unbound ports (rather than refusing them), a probe of an absent
# backend blocks for the full socket timeout, and a health endpoint that
# takes two seconds is a health endpoint that breaks every waiter with a
# shorter per-attempt timeout.
backend_state = {"running": False, "pid": None, "checked": 0.0}


def backend_healthy(timeout: float = 0.5) -> bool:
    """Is the backend up? Short timeout on purpose - see backend_state."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/health", timeout=timeout) as r:
            ok = r.status == 200
    except (urllib.error.URLError, OSError):
        ok = False
    backend_state["running"] = ok
    backend_state["checked"] = time.time()
    return ok


def _port_owner_pid(port: int):
    """PID listening on a loopback port, or None."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port:
                return c.pid
    except (psutil.AccessDenied, psutil.Error, OSError):
        return None
    return None


def _is_our_backend(pid: int) -> bool:
    """True only for a llama-server launched with OUR executable and port.

    The reaper terminates processes, so it must never kill an unrelated
    service that happens to hold the backend port.
    """
    try:
        import psutil
    except ImportError:
        return False
    try:
        p = psutil.Process(pid)
        cmd = " ".join(p.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, OSError):
        return False
    if "llama-server" not in cmd.lower():
        return False
    if f"--port {BACKEND_PORT}" not in cmd and f'"--port" "{BACKEND_PORT}"' not in cmd:
        return False
    return True


def adopt_backend() -> int | None:
    """Adopt a backend left behind by a previous proxy instance.

    A proxy restart orphans its child: the new instance finds a healthy
    backend on the port, forwards to it, and never reaps it - so the
    multi-GB backend stays resident indefinitely. Adopting it by PID (and
    verifying it really is ours) restores the idle contract.
    """
    global backend_pid
    pid = _port_owner_pid(BACKEND_PORT)
    if pid is None or not _is_our_backend(pid):
        return None
    if backend_proc is not None and backend_proc.poll() is None:
        return None                      # we own it; nothing to adopt
    if backend_pid != pid:
        log(f"adopting orphaned backend pid {pid} on :{BACKEND_PORT}")
    backend_pid = pid
    return pid


def start_backend() -> bool:
    """Spawn llama-server and wait for /health. Returns True when ready."""
    global backend_proc, backend_pid, last_used
    with state_lock:
        if backend_proc is not None and backend_proc.poll() is None and backend_healthy():
            return True
        if adopt_backend() is not None and backend_healthy():
            return True
        if backend_proc is not None and backend_proc.poll() is not None:
            log(f"backend exited rc={backend_proc.returncode}; restarting")
        log("cold start: spawning llama-server on :%d" % BACKEND_PORT)
        t0 = time.time()
        logf = open(BACKEND_LOG, "ab")
        try:
            backend_proc = subprocess.Popen(
                START_CMD, stdout=logf, stderr=logf,
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
                backend_pid = backend_proc.pid
                backend_state["running"] = True
                backend_state["pid"] = backend_proc.pid
                # A cold start is activity: the request that triggered it is
                # still in flight, so the idle clock restarts here. Otherwise
                # a backend started just before the deadline is reaped while
                # its first caller is still waiting on it.
                last_used = time.time()
                log(f"backend ready in {time.time()-t0:.1f}s (pid {backend_proc.pid})")
                return True
            time.sleep(0.5)
        log("backend failed to become healthy in time")
        return False


def _terminate_pid(pid: int) -> bool:
    try:
        import psutil
    except ImportError:
        return False
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=10)
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception:
        try:
            p.kill()
            return True
        except Exception:
            return False


def _stop_backend_locked() -> None:
    """Release the backend's RAM. The caller MUST hold state_lock.

    Two things this must not do:
      * stop the same pid twice (a spawned backend is also backend_pid);
      * clear the globals for a backend that is NOT the one being stopped.
        A request can arrive while the reaper is working and start a new
        backend; wiping the handle to it would orphan it - a live multi-GB
        process that nothing can ever reap.
    """
    global backend_proc, backend_pid
    proc = backend_proc
    adopted = backend_pid
    # the same process can be both spawned and adopted - stop it once
    spawned_pid = proc.pid if proc is not None else None
    target_pids = {p for p in (spawned_pid, adopted) if p}
    if proc is not None:
        log(f"idle timeout: stopping backend pid {spawned_pid}")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if adopted is not None and adopted != spawned_pid:
        if _is_our_backend(adopted):
            log(f"idle timeout: stopping adopted backend pid {adopted}")
            _terminate_pid(adopted)
    # only clear the handles that still refer to what we just stopped
    if proc is not None and backend_proc is proc:
        backend_proc = None
    if adopted is not None and backend_pid == adopted:
        backend_pid = None
    # only clear the state if it still describes a backend we stopped
    if backend_state.get("pid") in target_pids or backend_state.get("pid") is None:
        backend_state["running"] = False
        backend_state["pid"] = None
    log("backend stopped - RAM released")


def stop_backend() -> None:
    """Public entry point: take the lock, then release the backend."""
    with state_lock:
        _stop_backend_locked()


def watchdog() -> None:
    """Reap an idle backend.

    The idle check and the kill happen under ONE lock acquisition. If they
    were separate, a request could arrive between them, cold-start a new
    backend, and the reaper would then kill that new backend (or clear its
    handle) - leaving a multi-GB process nothing can ever reap.
    """
    while True:
        time.sleep(30)
        with state_lock:
            if (time.time() - last_used) <= IDLE_TIMEOUT:
                continue
            if backend_proc is None and backend_pid is None:
                continue
            _stop_backend_locked()


def _is_use(path: str) -> bool:
    p = path.lower()
    return any(h in p for h in USE_PATH_HINTS)


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _health(self) -> None:
        """Answer the contract's health check WITHOUT touching the backend.

        Forwarding /health would cold-start the multi-GB backend just to
        answer a monitor's probe, and would refresh the idle timer so the
        backend could never be released.
        """
        # Cached state, not a live probe: this endpoint must answer in
        # milliseconds and must never start anything.
        self._json(200, {
            "status": "ok",
            "proxy": "up",
            "backend_running": bool(backend_state["running"]),
            "backend_pid": backend_state.get("pid") or backend_pid or (backend_proc.pid if backend_proc else None),
            "idle_seconds_left": max(0, int(IDLE_TIMEOUT - (time.time() - last_used))),
        })

    def _forward(self, include_body: bool) -> None:
        global last_used
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if include_body and length else None

        if not backend_healthy():
            ok = start_backend()
            if not ok:
                self._json(503, {"error": "heretik backend failed to start"})
                return
        if _is_use(self.path):
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
                ct = up.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ct)
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
            self._json(502, {"error": f"backend unreachable: {e}"})

    def do_GET(self):
        if self.path == "/__demand_status":
            self._json(200, {
                "proxy": "up",
                "backend_running": bool(backend_state["running"]),
                "backend_pid": backend_state.get("pid") or backend_pid or (backend_proc.pid if backend_proc else None),
                "idle_seconds_left": max(0, int(IDLE_TIMEOUT - (time.time() - last_used))),
            })
            return
        if self.path.split("?")[0] in ("/health", "/healthz", "/ready"):
            self._health()
            return
        self._forward(include_body=False)

    def do_POST(self):
        self._forward(include_body=True)

    def do_OPTIONS(self):
        self._forward(include_body=False)

    def log_message(self, fmt, *args):  # quiet
        pass


def main() -> None:
    log(f"demand proxy starting on 127.0.0.1:{PROXY_PORT} (backend :{BACKEND_PORT}, idle {IDLE_TIMEOUT}s)")
    adopt_backend()
    threading.Thread(target=watchdog, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), Proxy)
    log("listening")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
