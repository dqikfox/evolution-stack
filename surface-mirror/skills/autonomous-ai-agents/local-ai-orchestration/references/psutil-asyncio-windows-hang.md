# psutil + asyncio + Windows: full debugging transcript

**Symptom (TESSERACT `/api/stats/processes`):** endpoint times out at 8s with empty body. The route was wrapped in `asyncio.wait_for(5.0)` + `loop.run_in_executor(None, get_top_processes)`, so the `wait_for` was supposed to fire at 5s. It did — but the response took 11.7s anyway, with a 52-byte body `{"error":"processes query timed out","processes":[]}`.

## Phase 1: Reproduce the exact symptom

```python
import urllib.request, time
t0 = time.monotonic()
with urllib.request.urlopen("http://127.0.0.1:8705/api/stats/processes", timeout=10) as r:
    body = r.read()
print(f"code={r.status} size={len(body)} time={time.monotonic()-t0:.2f}s body={body[:100]}")
# → code=200 size=52 time=11.72s body=b'{"error":"processes query timed out","processes":[]}'
```

11.7s for a 52-byte response. The `wait_for(5.0)` clearly fired (5s ceiling, error JSON present), but the response still took 6.7s more to arrive.

## Phase 2: Read the function

```python
def get_top_processes(n: int = 10) -> list:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            procs.append(p.info)
        except Exception:
            pass
    return sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:n]
```

The two `psutil` attributes that aren't just `pid`/`name`/`status` are `cpu_percent` and `memory_percent`. **Either of these is the trigger** — they each do a per-process handshake that costs 10-30ms on Windows, and on a 500-process table that's 5-15s.

## Phase 3: Minimize the repro

```bash
# Bare iter (pid, name only) — fast
$ python -c "import psutil, time; t=time.monotonic(); n=sum(1 for _ in psutil.process_iter(['pid','name'])); print(f'{n} procs in {time.monotonic()-t:.2f}s')"
# → 502 procs in 0.47s

# With memory_percent — slow
$ python -c "import psutil, time; t=time.monotonic(); n=sum(1 for _ in psutil.process_iter(['pid','name','memory_percent'])); print(f'{n} procs in {time.monotonic()-t:.2f}s')"
# → 490 procs in 10.78s
```

`memory_percent` is the slow one. 10.78s for a 490-process table. `cpu_percent` is similar.

## Phase 4: Verify it's a thread-pool problem, not a library problem

```python
# In a clean subprocess (true killable handle)
import multiprocessing as mp, time
def worker(q, n):
    import psutil
    t = time.monotonic()
    for p in psutil.process_iter(['pid', 'name', 'status']):
        try: p.memory_info().rss  # the slow call
        except: pass
    q.put(f'iter done in {time.monotonic()-t:.2f}s')

if __name__ == '__main__':
    q = mp.Queue()
    proc = mp.Process(target=worker, args=(q, 5))
    proc.start()
    proc.join(5)
    print('alive after 5s:', proc.is_alive())  # True
    proc.kill()
```

Yes — even in a clean subprocess, `memory_info()` blocks past 5s. So the issue is real psutil slowness on this host, not an event-loop problem.

## Why `asyncio.wait_for` didn't help

```python
# The trap:
async def handler():
    return await asyncio.wait_for(
        loop.run_in_executor(None, slow_sync_fn),  # takes 10s
        timeout=5.0,
    )
# asyncio.wait_for cancels the *awaitable* at 5s. The Future wrapping
# run_in_executor receives the cancellation. The Future is marked cancelled.
# BUT the executor thread (ThreadPoolExecutor worker) is unkillable on
# Python's default executor. The thread holds the GIL and runs to completion.
# The event loop can't process any other I/O until the thread releases GIL.
# When the thread finally finishes, the cancelled Future returns its result
# (which asyncio.wait_for discards) and the handler proceeds to serialize the
# return value — which takes another ~1s.
# Net wall-clock: 10s of work + 1s of response serialization = 11s.
```

## The fix that worked (production)

Three layers, in order of preference:

### Layer A: bypass psutil entirely with Win32 PSAPI via ctypes

```python
import ctypes
from ctypes import wintypes

psapi = ctypes.WinDLL("psapi.dll")
kernel32 = ctypes.WinDLL("kernel32")
EnumProcesses = psapi.EnumProcesses
EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD)]
EnumProcesses.restype = wintypes.BOOL
# ... etc, see core/system.py in TESSERACT

pids = (wintypes.DWORD * 4096)()
cb = wintypes.DWORD(0)
EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(cb))
# → returns in 0.000s with 320+ PIDs

# Per-pid:
class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]
# 80 bytes on x64 — get the layout wrong and WorkingSetSize reads as 0.
```

`EnumProcesses` + `OpenProcess` + `GetProcessMemoryInfo` + `GetProcessImageFileNameW` enumerates 500 processes with RSS in ~250ms. That replaces the 10s psutil path entirely.

### Layer B: spawn the worker in a real subprocess

```python
import multiprocessing as mp
ctx = mp.get_context("spawn")  # spawn, not fork — fresh interpreter, clean state
q = ctx.Queue()
# Worker MUST be module-level for spawn pickle to work
proc = ctx.Process(target=module_level_worker, args=(q, n), daemon=True)
proc.start()
proc.join(timeout=3.0)  # hard wall-clock ceiling
if proc.is_alive():
    proc.terminate()
    proc.join(timeout=0.5)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=0.5)
    return []  # graceful fallback
result = q.get_nowait()
```

Subprocess is a real OS process. `terminate()` works. The parent never blocks past 3.5s.

### Layer C: asyncio.wait_for with return_exceptions (for the gather case)

```python
async def check_all_services():
    results = await asyncio.wait_for(
        asyncio.gather(*[check_service(s) for s in SERVICES], return_exceptions=True),
        timeout=6.0,
    )
    return {svc["key"]: r if not isinstance(r, Exception) else _offline(svc, str(r)[:80], 6.0)
            for svc, r in zip(SERVICES, results)}
```

Bounds the wait, but does NOT bound the work. One slow service can still consume a worker thread for the full 6s. Use only when the slow service is rare or its data is droppable.

## Final result (TESSERACT, post-fix)

```
GET    /api/stats/processes  200  time=0.281s  size=803
len=15
  {'pid': 16076, 'name': 'PhoneExperienceHost.exe', 'rss_mb': 1423.7}
  {'pid': 21736, 'name': 'Hermes.exe',             'rss_mb': 869.5}
  {'pid': 207808,'name': 'cyberstrike.exe',         'rss_mb': 664.4}
  {'pid': 199916,'name': 'Desktop Commander.exe',  'rss_mb': 403.3}
  {'pid': 7216,  'name': 'explorer.exe',           'rss_mb': 374.6}
```

Real RSS data, 0.28s wall clock, no thread pool involvement.

## When to use which layer

- **Always wrap the slow call in Layer A first** if you can target Windows specifically and the data is for a real-time dashboard.
- **Layer B is the right answer** if you must use a slow third-party library AND you can put the call in a function whose return value is small (a list, a dict — not a 10MB blob you have to transfer back).
- **Layer C alone** is fine for "fire and forget" probes where dropping one slow result is acceptable.
- **You generally need A or B + a hard ceiling in the route itself** (Layer C). The 6s ceiling in `asyncio.wait_for` won't stop the work but it stops the response wait, which is what the user actually sees.
