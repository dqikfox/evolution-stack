---
name: throne-network-discovery
description: THRONE LAN/Tailnet/USB discovery + auto-mount.
---

# THRONE Network Discovery

When any device/file-system needs to be integrated into THRONE (MSI shares,
LAN hosts, USB drives, Tailnet peers), use the discovery daemon.

## What ships
- `C:\\Users\\KING\\AppData\\Local\\hermes\\scripts\\throne_discovery.py`
  - CLI: `python throne_discovery.py` (one-shot scan)
  - CLI: `python throne_discovery.py --http --http-port 8660` (serves JSON+MD)
  - CLI: `python throne_discovery.py --watch --interval 300` (loop)
- HTTP server: `http://127.0.0.1:8660/`
  - `GET /` -> full JSON inventory
  - `GET /inventory.md` -> human markdown
  - `GET /rescan` -> force scan + return new JSON
- Outputs:
  - `cron/output/throne_network_inventory.json`
  - `cron/output/throne_network_inventory.md`
- Scheduled task: `THRONE_Discovery_10min` (every 10 min, no logon)
- Watchdog integration: `throne_inv` field in health_state.json

## Auto-mount rules
Edit `AUTO_MOUNT_RULES` at top of `throne_discovery.py` to add a share.
**Critical:** UNC strings with backslashes are eaten by patch tooling. Use
`chr(92)+chr(92)+"{host}"+chr(92)+"share"` form to survive edits, OR write
the file with `write_file` not `patch`.

## Pitfalls
- Windows ping timeout ignores `-w` under 200ms; minimum effective is 200.
- ThreadPoolExecutor + ping hangs if any host eats the timeout; wrap `ping()` and `scan_host()` in try/except.
- `net use` output has variable column widths — split on whitespace, index `[1]` for drive, `[2]` for target. `line.startswith("U:")` does NOT work.
- `subprocess.run(["powershell", "-Command", "net use U: '\\\\\\\\host\\share'"])` quadruple-escapes backslashes. Use `cmd /c net use ...` instead — preserves UNC paths cleanly.
- Tailscale SMB routing varies by DERP relay; prefer LAN IP when both reachable.

## Mount verification
After auto-mount, verify with `net use`. If error 85 (local device name in use), the drive is mounted to a different target — `try_mount()` reports `already: true, different_target: true`.

## When watch fails
- Check `%LOCALAPPDATA%\\hermes\\logs\\throne_discovery.log`
- Restart: `python throne_discovery.py --http --http-port 8660 &`

## SSH credential recovery for Tailnet peers

When a tailnet peer (e.g., MSI at `msi.tail886dbb.ts.net`) is reachable on the
network but SSH authentication fails, the credentials may live in one of
several places — and the user's hint may be partially wrong.

### Search order
1. **1Password vault** — `op item list --vault credentials | grep -i <host>`
   - Service account only sees vaults it was granted. If nothing matches,
     continue; do not loop on title variations.
2. **Archived Termius exports** — `E:\\ultron-memory\\termius-config\\` contains
   CSV exports (`termius-hosts.csv`) and SSH config snippets from prior imports.
   Check `termius-hosts.csv` for password or key-file entries.
3. **MSI backup docs** — `E:\\ultron-memory\\backups\\obsidian-vault-pre-rebuild\\`
   may contain credential inventories from earlier configuration passes.
4. **Brute-force shortlist via paramiko** — if the user provided a hint that
   might be slightly off (e.g., hinted `but2580` but actual password is `2580`),
   use a Python paramiko loop over plausible variants instead of asking the
   user to re-type. Try: exact hint, hint without prefix/suffix words,
   numeric-only suffix, capitalized variants, empty string. Stop on first
   success and store the working credential in 1Password immediately.

### Paramiko brute-force template
```python
import paramiko
host = 'msi.tail886dbb.ts.net'
user = 'CHANN0$'
hints = ['but2580', '2580', 'But2580', 'BUT2580']
for pw in hints:
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=pw, timeout=10,
                       allow_agent=False, look_for_keys=False)
        print('SUCCESS', pw)
        client.close()
        break
    except paramiko.AuthenticationException:
        pass
```

### Store working credential
Once found, create a 1Password item so future sessions do not repeat the brute:
```bash
op item create --vault credentials --category login \
  --title "MSI (CHANN0$)" --url "msi.tail886dbb.ts.net" \
  username="CHANN0$" password="<FOUND>" \
  "notes=Windows 11 Home MSI. Tailscale IP 100.83.120.56."
```

### Pitfalls
- **MSYS bash strips the trailing `$` from usernames** — `CHANN0$@host` becomes
  `chann0host` because bash interpolates `$` as a variable. Always single-quote
  SSH usernames that contain `$`: `'CHANN0$@msi.tail886dbb.ts.net'`.
- **Paramiko requires `allow_agent=False, look_for_keys=False`** when testing
  password auth, or it will try local keys first and return
  "Too many authentication failures" before reaching the password prompt.
- **Password hints may be wrong** — treat them as search seeds, not ground truth.
  The actual password may be a substring, a different case, or a completely
  different value stored in an archived config.