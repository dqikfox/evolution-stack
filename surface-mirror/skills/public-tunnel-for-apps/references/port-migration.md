# Port Migration Workflow

Moving a live service from one port to another on THRONE without
collisions or dangling tunnels.

## When to migrate

- Port collision with another service (e.g., llama-server already on
  `:8080`, KRYSYS needs its own port)
- Security policy separating frontend (`:8500`) from inference
  (`:8080`) from RAG (`:8650`)
- Preparing a port map registry for the THRONE infrastructure

## Procedure

1. **Discover the current state**
   ```powershell
   Get-NetTCPConnection -State Listen | Select-Object LocalPort, OwningProcess | Sort-Object LocalPort | Format-Table
   ```

2. **Kill the old service cleanly**
   ```powershell
   Stop-Process -Id <PID> -Force
   ```
   Verify port released:
   ```powershell
   Get-NetTCPConnection -LocalPort <PORT> -State Listen 2>$null
   ```

3. **Update the service's default port**
   - Edit the `app.listen()` or `server.start()` call to use the new
     default, OR set `PORT=<new>` in `.env` and ensure `dotenv` is
     loaded before the listener starts.

4. **Force dual-stack binding** (Express / Node.js)
   ```js
   app.listen(PORT, "0.0.0.0", () => { ... });
   ```
   Without `"0.0.0.0"`, Express may bind to IPv6 `::` only, causing
   `127.0.0.1` tunnel forwards to return 502.

5. **Update the tunnel script** (if any)
   - Change `serveo-tunnel-loop.bat` or the SSH `-R` flag to match the
     new port.

6. **Start the service and verify both families**
   ```python
   import urllib.request
   for addr in ['127.0.0.1', 'localhost']:
       r = urllib.request.urlopen(f'http://{addr}:{PORT}/api/health', timeout=5)
       print(r.status)
   ```

7. **Spin up the tunnel and extract the new URL**
   Parse the SSH stdout / log for `Forwarding HTTP traffic from ...`

8. **Write the port map**
   Save to `E:\ultron-memory\infra\PORT_MAP.json`.

## Pitfall: Express IPv6-only default

Express 5 on Windows may bind to IPv6 `::` when given only a port
number. A tunnel forwarding to `127.0.0.1:<port>` (IPv4) receives
502 because no IPv4 listener exists. Always pass `"0.0.0.0"` as the
bind address when a tunnel is involved.

## Pitfall: SSH log lands in wrong directory

When `ssh` is launched via `cmd /c` from MSYS bash with a redirect
like `> serveo_live.log`, the working directory may be interpreted as
`C:\Users\KING` even if the command was launched from the project
folder. The log ends up at `C:\Users\KING\C:UsersKINGserveo_live.log`
(MSYS path conversion artifact). Use an absolute path for the redirect.

## Pitfall: `set PORT=8500 && node server.js` silently ignored

Windows `set` inside a one-line `cmd /c` command does not always
persist to the child process, especially when run from MSYS bash.
Prefer hardcoding the default in the source file for reliability
(`const PORT = process.env.PORT || 8500;`) and editing the file
directly when a permanent move is needed.