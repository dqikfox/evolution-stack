# FastAPI + asyncio + uvicorn on Windows: runtime pitfalls

Battle-tested in a production-grade FastAPI control plane on Windows.
Each pitfall includes symptom → cause → fix → verification.

These complement `fastapi-pydantic-v2-pitfall.md` and `pythonpath-leakage-fix.md`:
those cover environment setup; this one covers runtime behavior of FastAPI,
asyncio, uvicorn, and Windows-specific quirks.

---

## 1. `asyncio.wait_for(N)` cannot cancel a running thread

**Symptom:** endpoint returns 200 with an empty body after exactly N
seconds; client times out; the work then finishes minutes later and
fills up memory or hangs the response serializer.

**Cause:** `asyncio.wait_for` cancels the await — it does NOT cancel the
function running inside `loop.run_in_executor`. The thread keeps
running, holds the GIL, and the event loop can't serialize the response
until the thread returns.

**Fix:** wrap the work in a real killable boundary:

- A `multiprocessing.spawn` subprocess — Python's `Process.terminate()`
  actually kills the child. Pair with a `Queue()` to ferry results back.
- An OS-level subprocess (`subprocess.Popen` + `proc.kill()`)
- A thread with a shared cancel flag **only if you can guarantee the
  thread checks the flag frequently**

For psutil-heavy work, I rewrote a top-processes function to spawn a
subprocess that does the work, with a hard `proc.join(timeout=3.0)` ceiling
and `terminate() → kill()` escalation. The route became 0.28s for 15
processes with real RSS data, down from a 10-second timeout that
returned empty.

**Verification:** the route must still return 200 with the data; if
the subprocess was killed before completing, return an empty list (not
an error). The caller doesn't wait on the work.

---

## 2. Win32 PSAPI via ctypes is 10,000× faster than `psutil` on Windows

**Symptom:** `psutil.process_iter(['pid', 'name', 'memory_percent'])`
on a 500-process table takes 10+ seconds and pegs a CPU core.

**Cause:** `psutil` does per-process syscalls with extra overhead per
attribute. Every extra attribute is a Win32 round-trip, and some
attributes (notably `memory_percent`) require a fresh
`virtual_memory()` lookup per process.

**Fix:** call Win32 PSAPI directly via ctypes:

```python
import ctypes
from ctypes import wintypes

psapi = ctypes.WinDLL("psapi.dll")
kernel32 = ctypes.WinDLL("kernel32")

EnumProcesses = psapi.EnumProcesses
EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD)]
EnumProcesses.restype = wintypes.BOOL

class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        # ... exact MSDN layout, 80 bytes total
    ]

pids = (wintypes.DWORD * 4096)()
cb = wintypes.DWORD(0)
EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(cb))
# 500+ processes enumerated in ~50ms instead of 10s
```

Critical: the `PROCESS_MEMORY_COUNTERS` struct **must** match MSDN exactly
or `WorkingSetSize` reads as 0. The full 80-byte struct is required.

If you only need RSS as a percentage: call `psutil.virtual_memory()` once,
then iterate with `rss_bytes = p.memory_info().rss`. Skipping the per-
process `memory_percent` attribute alone saves ~7 seconds.

---

## 3. FastAPI WebSocket route rejected with HTTP 403

**Symptom:** `websockets.exceptions.InvalidStatus: server rejected WebSocket connection: HTTP 403` (empty body, no log line in your handler)

**Cause:** Starlette 1.3+ requires the endpoint signature to have the
`WebSocket` type annotation. Without it, the route handler doesn't get
the WebSocket object injected correctly and the handshake is rejected
*before your code runs*.

**Wrong:**
```python
@app.websocket("/ws/ssh")
async def ws_terminal(ws):           # ❌ 403 Forbidden
    ...
```

**Right:**
```python
@app.websocket("/ws/ssh")
async def ws_ssh_terminal(ws: WebSocket):    # ✅ accepted
    await ws.accept()
    ...
```

The fix is invisible at the call site. The diagnostic: if `websockets`/
Postman/Playwright all return 403 and other `@app.websocket` routes on
the same app work, check for missing `: WebSocket` annotations.

**Other things that cause 403 (cross-check in order):**
1. Missing `: WebSocket` annotation
2. A global middleware that requires an `Origin` header (set
   `CORSMiddleware(allow_origins=["*"])` or remove the middleware)
3. The endpoint returning before `await ws.accept()`
4. Two `@app.websocket` decorators with overlapping paths

---

## 4. `multiprocessing.spawn` cannot pickle local functions

**Symptom:** `AttributeError: Can't pickle local object 'outer.<locals>._worker'`

**Cause:** `multiprocessing.spawn` pickles the target function and sends
it to a fresh Python interpreter. Local/closure functions aren't
picklable because they capture enclosing scope that can't be serialized.

**Fix:** move the worker function to module scope:

```python
# ❌ Fails: defined inside another function, can't pickle
def get_top_processes(n):
    def _worker(q, n):     # closure; not picklable
        ...
    ctx = mp.get_context("spawn")
    ctx.Process(target=_worker, args=(q, n))   # AttributeError on start()

# ✅ Works: module-scope, importable, picklable
def _psutil_top_processes_worker(q, n):
    ...
def get_top_processes(n):
    ctx = mp.get_context("spawn")
    ctx.Process(target=_psutil_top_processes_worker, args=(q, n))
```

You can also use `multiprocessing.get_context("fork")` on Linux/macOS,
which avoids the pickle step entirely — but Windows only supports
`spawn`, so this matters for cross-platform code.

---

## 5. Multicast IPs hang `socket.gethostbyaddr` for ~5s each

**Symptom:** `arp -a` returns in 100ms; parsing 100 entries through
`socket.gethostbyaddr(ip)` takes 78 seconds.

**Cause:** Tailscale's interface (and many virtual NICs) dumps ARP entries
for multicast addresses like `224.0.0.22` (IGMP), `224.0.0.251` (mDNS),
`239.255.255.250` (SSDP). Each one is valid syntactically but the OS tries
to resolve it via DNS, which times out per address.

**Fix:** filter multicast/reserved/link-local addresses BEFORE resolving,
and use a hard socket timeout plus a per-host cache:

```python
import ipaddress
import socket

def _reverse_dns(ip: str, timeout: float = 0.6) -> str:
    # Skip multicast, broadcast, link-local, loopback — these never have useful names
    try:
        addr = ipaddress.IPv4Address(ip)
        if (addr.is_multicast or addr.is_reserved or
                addr.is_link_local or addr.is_loopback):
            return "?"
    except Exception:
        return "?"
    # Cache
    if hasattr(_reverse_dns, "_cache") and ip in _reverse_dns._cache:
        return _reverse_dns._cache[ip]
    if not hasattr(_reverse_dns, "_cache"):
        _reverse_dns._cache = {}
    # Use socket with timeout
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        _reverse_dns._cache[ip] = host
        return host
    except Exception:
        _reverse_dns._cache[ip] = "?"
        return "?"
    finally:
        socket.setdefaulttimeout(old)
```

**Verification:** 12 unique devices discovered in 1.77s instead of 78s
for the same `arp -a` input.

---

## 6. `loop.run_in_executor(None, fn, *positional)` fails on kwargs-only sigs

**Symptom:** `TypeError: fn() takes from 1 to N positional arguments but N+1 were given`

**Cause:** Python can't bind keyword-only parameters through positional
arguments, even via `run_in_executor`.

**Wrong:**
```python
delete(conn, path, True)     # ❌ if delete() is (a, b, *, recursive=False)
loop.run_in_executor(None, delete, conn, body.path, True)
```

**Right:**
```python
loop.run_in_executor(None, lambda: delete(conn, body.path, recursive=True))
```

This bit me on 3 separate endpoints in one session (`/api/file/browse`,
`/api/file/delete`, `/api/remote/service/status`). When you see
`TypeError: takes from 1 to N positional but N+1 were given` and the
function definition has `*` or `*,` between args, that's the cause.

**Rule:** when calling a function with kwargs-only params via
`run_in_executor`, always wrap in `lambda:`. Even better, accept
positional params and do the kwarg binding inside the function.

---

## 7. `tcp_probe` on Windows can hang for 5–6s on "connection refused"

**Symptom:** a test that does `tcp_probe("127.0.0.1", 22)` takes 5 seconds
even though there's no SSH server listening.

**Cause:** Windows TCP stack retries SYN before giving up; default
retry behavior is OS-level and not bound by Python's socket timeout.

**Fix:** when writing integration tests that probe unreachable hosts:
- Mark them `@pytest.mark.skipif(sys.platform.startswith("win"))` for
  strict parallel-timing assertions
- Assert time bounds with generous headroom (e.g. `<25s` for 3
  unreachable hosts) for general correctness
- For production code, prefer `socket.create_connection(host, port,
  timeout=0.6)` — short timeout is honored on Linux but Windows still
  retries underneath

**Verification:** a `test_inventory_parallelism` test was passing on
Linux but timing out on Windows; the skip-if-Windows approach is the
right answer for CI portability.

---

## 8. uvicorn's `tee` log buffer hides errors during background runs

**Symptom:** endpoint returns 500 but `/tmp/tesseract.log` shows nothing
about the error (or shows it minutes later).

**Cause:** when you start uvicorn as `python start.py 2>&1 | tee /tmp/log`,
the tee/pipe buffer can delay stderr writes by 4KB blocks. The error
happens but never reaches the log until the buffer fills or the process
exits.

**Fix:** either:

- Use `python -u` (unbuffered) for the start command:
  ```bash
  cd "C:/Projects/tesseract" && python -u start.py 2>&1 | tee /tmp/log
  ```
- Or have the route handler explicitly log errors to a dedicated file:
  ```python
  @app.exception_handler(Exception)
  async def log_all(request, exc):
      with open("/tmp/tesseract_errors.log", "a") as f:
          f.write(traceback.format_exc())
      return JSONResponse({"detail": "internal"}, status_code=500)
  ```

I lost ~30 minutes to this exact issue before adding `-u` to the
start command.

---

## 9. FastAPI Jinja2Templates expects `(request, name, context)` in Pydantic v2

**Symptom:** `TypeError: unhashable type: 'dict'` from inside jinja2
when serving an HTML page.

**Cause:** in Pydantic v2 + FastAPI 0.115+, the deprecated signature
`templates.TemplateResponse("index.html", {"request": request, ...})`
raises during the `self._mapping[key]` access where the second argument
is now expected to be a `dict`, but the new signature is
`(request, name, context)`.

**Right (FastAPI 0.115+):**
```python
return templates.TemplateResponse(
    request, "index.html",
    {"title": TITLE, "version": VERSION, "...": ...}
)
```

**Wrong (deprecated):**
```python
return templates.TemplateResponse(
    "index.html",
    {"request": request, "title": TITLE, ...}
)
```

---

## 10. `python -c` blocks don't inherit Hermes' `sys.path`

**Symptom:** `execute_code` sandbox blocks raise
`ModuleNotFoundError: No module named 'core'` even though
`C:/Projects/tesseract/core/` exists.

**Cause:** the `execute_code` "sandbox" python doesn't share cwd or
sys.path with the project venv. It runs with whatever python interpreter
the agent has access to, which doesn't know about project packages.

**Fix:** for project-internal tests, run via `terminal` with the
project's venv python:

```bash
"C:/Projects/tesseract/.venv/Scripts/python.exe" -c "from core.x import y; ..."
```

Or use the dedicated test harness:
```bash
"C:/Projects/tesseract/.venv/Scripts/python.exe" -m pytest tests/test_foo.py
```

The `execute_code` sandbox is for stdlib + isolated experiments, not
for hitting project modules.

---

## Putting it all together

When building a production FastAPI control plane on Windows, the
biggest non-obvious risks are:

1. Long-running work inside `run_in_executor` → use a spawned subprocess
2. Heavy use of psutil on Windows → Win32 PSAPI via ctypes
3. Multicast IPs in ARP/Tailscale dumps → filter before reverse DNS
4. FastAPI WebSocket routes → `: WebSocket` annotation is mandatory
5. Kwargs-only signatures → wrap in lambda before `run_in_executor`
6. Buffered logs → `python -u`

Together these account for most of the "works on my Mac, broken on
Windows" failures in Python web services.
