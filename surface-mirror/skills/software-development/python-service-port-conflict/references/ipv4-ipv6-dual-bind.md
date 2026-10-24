# IPv4/IPv6 Dual-Bind Reproduction

The trap: Windows accepts two separate sockets on the same port — one bound to `0.0.0.0` (IPv4) and one bound to `::` (IPv6). They are independent. Killing one does not free the port for the other.

## How it happens

1. Service A is already running, bound to `0.0.0.0:8080`.
2. You launch Service B which calls `app.listen(8080)` — Node/Express binds to `::` (IPv6 wildcard) by default on recent Node versions.
3. Both now "have" port 8080. `netstat` shows two LISTEN rows on port 8080 with different `OwningProcess` PIDs.

## How to detect it

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
  Select-Object LocalAddress, OwningProcess, ProcessName
```

If you see one row on `::` and one row on `127.0.0.1`/`0.0.0.0` for the same port, you're in the trap. **Both are alive simultaneously.**

```python
import urllib.request
for addr in ('localhost', '127.0.0.1'):
    try:
        r = urllib.request.urlopen(f'http://{addr}:8080/health', timeout=3)
        print(addr, r.status, r.read()[:80])
    except urllib.error.HTTPError as e:
        print(addr, 'HTTP', e.code, e.read()[:80])
```

If the two responses differ (one is your JSON, one is a foreign service's error), the dual-bind is active.

## How to fix

Three options, in order of preference:

1. **Kill the foreign PID**. Use the PID from `Get-NetTCPConnection`, not the image name. Most frameworks hide behind `node.exe` / `python.exe`.

2. **Bind the new service explicitly to IPv4** so a collision becomes a fatal `EADDRINUSE` instead of a silent IPv6 co-existence:
   ```bash
   HOST=127.0.0.1 node server.js
   # or in code:
   app.listen(8080, '127.0.0.1', ...)
   ```

3. **Move the new service to a different port**. Last resort — changes the contract for every client.

## Why `localhost` is misleading

On Windows, `getaddrinfo("localhost")` returns `[::1]` first (Happy Eyeballs prefers IPv6). So `curl http://localhost:8080/health` resolves to your IPv6-bound service, while `curl http://127.0.0.1:8080/health` resolves to the IPv4 holder. Two valid responses from the "same URL" — classic source of "but it works on my machine" debugging grief.

## Don't do this

Do NOT add `127.0.0.1` to `/etc/hosts` as an alias for `localhost` to force IPv4 — that affects DNS resolution globally for everything else. Fix the bind, not the resolver.