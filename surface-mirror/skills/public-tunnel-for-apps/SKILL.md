---
name: public-tunnel-for-apps
description: Expose local apps via serveo SSH tunnel or Netlify drop.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tunnel, public-url, serveo, cloudflare, netlify, vercel-bypass, deployment, local-app]
    related_skills: [throne-network-discovery, continuous-feature-development]
---

# Public Tunneling for Local Apps

Expose a locally-served app (running on `127.0.0.1:<port>` or
`0.0.0.0:<port>` on THRONE) to the public internet when the normal
deploy pipeline is broken, laggy, or auth-walled.

## When to Use

- Vercel custom domain alias is serving 1+ week-old content and fresh
  deploys come back `● Blocked`
- Vercel free-tier team URLs (`<random>-<team>-projects.vercel.app`)
  show "Login – Vercel" instead of the build
- GitHub Pages is serving stale content and you need a URL in 5 minutes
- Stripe webhook / PayID redirect needs a public origin the user's bank
  can reach (Stripe rejects `127.0.0.1` and `192.168.x.x`)
- The user says "give me a real URL I can share" or "launch it from
  this host"

Don't use this for: production deployments (use a paid tunnel or static
host with a real domain). The free tunnels below are for getting
something live in hours, not years.

## Quick Decision Table

| Need                                | Use                                | Why                                |
| ----------------------------------- | ---------------------------------- | ---------------------------------- |
| URL in 60 seconds, no install       | `serveo` SSH                       | Zero account, zero install         |
| Stable URL across reconnects        | serveo + add SSH key at console    | Reserves the subdomain             |
| Static site, no backend, want HTTPS | `netlify deploy --allow-anonymous` | Free deploy with a password        |
| Long-running HTTPS, custom domain   | Cloudflare Quick Tunnel + DNS      | Persistent, but needs `cloudflared` binary |

The rest of this skill is a recipe. The pitfall-class details are in
`references/serveo-recipes.md` (Windows .bat loop, MSYS quoting, the
"Continue to Site" warning page, when Vercel custom domains lag, when
serveo's idle window kicks the tunnel).

## Recipe 1 — serveo SSH (zero-install, fastest)

Prereqs: any SSH client. `C:\Windows\System32\OpenSSH\ssh.exe` is on
all modern Windows; macOS and Linux have OpenSSH out of the box. Local
app bound to `0.0.0.0:<port>` (or `127.0.0.1:<port>` — serveo forwards
to localhost on the tunnel side).

```bash
ssh -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ExitOnForwardFailure=yes \
    -R 80:127.0.0.1:8080 serveo.net
```

The output line `Forwarding HTTP traffic from https://<random>.serveousercontent.com`
IS the public URL. Reconnect = new URL (unless you add your SSH key at
https://console.serveo.net/settings to reserve a subdomain).

Verify: `curl -sI https://<random>.serveousercontent.com/ | head -3`
should show the response headers from the local app, NOT serveo's
landing page (the warning page only shows in a browser, not in
`curl`).

## Recipe 2 — keep the tunnel alive across reconnects

Serveo's idle window is ~30 min; remote-host closes drop the session.
Wrap the tunnel in a `.bat` loop that re-spawns on exit:

```bat
@echo off
setlocal
:loop
echo [%date% %time%] Starting serveo tunnel...
set "SSH=C:\Windows\System32\OpenSSH\ssh.exe"
if not exist "%SSH%" set "SSH=ssh"
"%SSH%" -o StrictHostKeyChecking=no -o ServerAliveInterval=30 ^
    -o ExitOnForwardFailure=yes -R 80:127.0.0.1:8080 serveo.net
echo [%date% %time%] Tunnel died, restarting in 5s...
ping -n 6 127.0.0.1 >nul
goto loop
```

Run with `cmd /c "<file> > C:\path\to\serveo-loop.log 2>&1"` as a
background process. After every reconnect, parse the log to extract the
new random URL prefix.

**If you moved the app to a new port**, change the `-R 80:127.0.0.1:PORT`
line before starting the tunnel. The tunnel script and the app must
agree on the same port — a mismatch produces 502 even when both
processes are individually healthy.

## Recipe 3 — Netlify anonymous drop (static only, no backend)

When the deliverable is a pure static site (no `/api/*` calls), Netlify
accepts a one-shot deploy with no account:

```bash
netlify deploy --allow-anonymous --dir=. --alias=<sitename>
```

Output includes `Site URL: http://<sitename>.netlify.app` and a
`Password:` line (printed once, copy it). Netlify gives 60 min to claim
the site via `netlify claim --site <id> --token <token>` or
`https://app.netlify.com/drop/<id>` before the URL deactivates.

This works for static storefronts, marketing pages, docs sites. It
does NOT work for any backend the local app depends on (PayID redirect,
Stripe webhook, etc.).

## Verification

Every tunnel has one verification that always works:

```python
import urllib.request
r = urllib.request.urlopen('<url>', timeout=10)
print(r.status, r.read().decode()[:200])
```

If `r.status` is 502/503, the tunnel is up but the local app isn't
listening. If the response body is `Expose local servers to the
internet | Serveo`, the tunnel IS up and the URL is right but you
landed on the warning page in a browser — `curl` bypasses it. If you
visited in a browser and still see serveo's warning page, click
`Continue to Site` (the page only shows once per URL per browser
session for new visitors).

### Why 502 happens when the app IS running

If the local app shows `:::<port>` in `Get-NetTCPConnection` (IPv6
only) but the tunnel forwards to `127.0.0.1:<port>` (IPv4), the
tunnel receives the request but the app rejects the IPv4 connection.
The fix is to bind the app to `0.0.0.0` explicitly so it accepts
both IPv4 and IPv6:

```js
// server.js — force dual-stack binding
app.listen(PORT, "0.0.0.0", () => { ... });
```

Verify both families before declaring the tunnel working:
```python
for addr in ['127.0.0.1', 'localhost']:
    r = urllib.request.urlopen(f'http://{addr}:{PORT}/...', timeout=5)
```

## When NOT to do this

- **Production deployment.** Free serveo URLs change on every reconnect.
  For a customer-facing storefront, point a real domain at a static
  host or pay for Cloudflare Quick Tunnel with named DNS.
- **Long-lived webhook URLs.** Stripe and PayID accept the dynamic
  serveo URL but if you restart the SSH session and the URL changes,
  the webhook deliveries stop. Pin the URL via SSH key registration.
- **WebSocket endpoints.** Serveo proxies HTTP only; long-poll /
  WebSocket / Server-Sent Events don't survive the tunnel.

## Related Skills

- `throne-network-discovery` — for the THRONE-side port/mount
  discovery that complements this skill's public-side exposure
- `continuous-feature-development` — for the verify-before-shipping
  cadence to apply to anything served through one of these tunnels

## Reference files

- `references/serveo-recipes.md` — pitfall-class details for MSYS
  quoting, the browser warning page, Vercel auth walls, and tunnel
  cleanup.
- `references/port-migration.md` — full workflow for moving a live
  service to a new port, including Express dual-stack binding, SSH
  log pathing, and the port map registry.