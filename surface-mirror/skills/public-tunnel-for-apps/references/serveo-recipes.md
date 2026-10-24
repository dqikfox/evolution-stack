# serveo.net Recipes and Pitfalls

This file holds the pitfall-class details for using serveo.net as an
SSH tunnel to expose local THRONE apps to the public internet. Kept
separate from SKILL.md because every pitfall here only matters when
something goes wrong; the recipe in SKILL.md is the happy path.

## The "Forwarding HTTP traffic from ..." line IS the public URL

serveo's first `Forwarding HTTP traffic from https://<random>.serveousercontent.com`
line in the SSH stdout is the public URL. There is no API call to make,
no DNS to configure. The URL rotates on every reconnect unless you
add your SSH public key at https://console.serveo.net/settings (then
you can reserve a subdomain with `--subdomain=<name>`).

## MSYS bash quoting eats Windows paths in `.bat` files

When a `.bat` script that contains `"C:\Users\KING\..."` paths is
launched via `cmd /c "<file>"` from MSYS bash (the Hermes `terminal`
backend), the outer quotes from `cmd /c` and the inner quotes from
the path combine in unexpected ways. The path appears in the .bat as
`""C:\Users\KING...""` (double-quoted) which `cmd.exe` parses as a
literal `"C:\Users\KING...` followed by junk.

Two reliable workarounds:

- Use a path with no spaces: `C:\Windows\System32\OpenSSH\ssh.exe`
  works without any quotes around it.
- Set `set SSH=<path>` first, then call `"%SSH%" ...` — the variable
  expansion handles the path string and the outer's `""` operator is
  separate from any path quoting.

Symptoms to watch for: the .bat script reports `'<path>' is not
recognized as an internal or external command` from bash, or in some
cases silently runs the wrong executable. Test the .bat file by running
it directly in `cmd.exe` before launching it via MSYS bash.

## GNU `timeout` is not in MSYS bash by default

`timeout /t 5 /nobreak` is a Windows cmd.exe builtin — but the
`timeout` binary in MSYS PATH is the GNU coreutils one, which has
different syntax. When a `.bat` containing `timeout /t N` is launched
from MSYS bash, bash finds the GNU binary first and dies with
`timeout: invalid time interval '/t'`.

Workaround: `ping -n 6 127.0.0.1 >nul` — same ~5s wait, no GNU-vs-Windows
mismatch, and Windows shell builtin that works under both cmd.exe and
any bash that intercepts `cmd /c` calls.

## The serveo browser warning page

First-time visitors to a fresh `*.serveousercontent.com` URL see a
"Serveo Browser Warning" splash with one button: "Continue to Site".
This appears once per URL per browser session. `curl` skips it entirely
— only browsers see the splash. Browser-vision QA checks that try to
read the page right after navigating will report the warning's
"Continue to Site" button as the page content.

Workaround in browser-vision QA:
```javascript
// First navigation lands on the warning page; click Continue and reload:
document.querySelector('button')?.click();
// then re-navigate to your actual path
```

If you want zero-warning URLs, register your SSH public key at
https://console.serveo.net/settings — the warning disappears for any
tunnel opened by a registered key.

## Vercel free-tier team URLs are auth-walled even on Ready builds

When you log into Vercel via `vercel login` and the CLI links to a
`dqikfoxs-projects` (or any non-personal) team, every preview URL
(`https://<random>-<team>-projects.vercel.app`) returns a "Login –
Vercel" auth page instead of the build. This applies even to builds
showing `● Ready` in `vercel ls <project>`. Personal accounts don't
have this — only team namespaces.

If you see `● Blocked` for every fresh build of a project, Vercel has
flagged the account for abuse heuristics (often: too many same-project
builds in a short window, or large deploys). `vercel redeploy <old-ready-url>`
re-uses the old build's artifacts and bypasses the Block; the resulting
deployment only updates the team-URL alias, never the custom domain.
Treat the custom domain as a deployment cache that lags reality and
verify the live URL with `curl -I` after waiting ~10s, not as the
source of truth.

## Netlify anonymous drop site gets a password

`netlify deploy --allow-anonymous --dir=. --alias=<sitename>` prints
both the public URL and the password on first deploy — copy the password
immediately because it isn't shown again in `vercel ls`-equivalent
output. The drop URL deactivates after 60 min unless someone claims it
via `netlify claim --site <id> --token <token>` or
`https://app.netlify.com/drop/<id>`.

Anonymous drops are static-only — no `/api/*` from the local backend
will reach THRONE. Use serveo when the local app has any backend, use
Netlify when it's pure static.

## When the SSH tunnel connection silently dies

Three failure shapes are common:

1. **`Connection to serveo.net closed by remote host`** — serveo's
   idle window expired (no traffic on the tunnel for ~30 min). The
   `ping -n` loop in the .bat restart script handles this automatically.
2. **`Warning: Permanently added 'serveo.net' (ED25519) to the list of known hosts.`**
   followed by a clean forward line — this is fine, it's just the first
   time the SSH client has connected to serveo. Add `-o StrictHostKeyChecking=no`
   to skip the prompt.
3. **`Bad permissions on SSH config / .ssh/id_*`** — only happens if
   you point serveo at a custom key file. Fix with `chmod 600` on the
   key (or, from Windows, use the GUI by either Windows or `icacls <key> /inheritance:r /grant:r "$USERNAME":R`).

## Cleanup on shutdown

To kill the running tunnel:

```bash
tasklist | grep -i ssh   # find the PID
taskkill /F /PID <pid>
```

Or from `cmd /c`:
```cmd
taskkill /F /IM ssh.exe
```

The `.bat` loop does NOT clean itself up on Ctrl-C — Ctrl-C kills the
loop only. To stop the tunnel permanently, find the bash process
holding the `.bat` file open and kill that too.