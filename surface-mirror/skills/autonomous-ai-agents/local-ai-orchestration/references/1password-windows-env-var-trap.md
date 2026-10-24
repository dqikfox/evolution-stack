# 1Password Windows Env-Var Trap

## The trap

Windows users frequently put a credential in a user-level env var named `1PASSWORD_API_KEY`, expecting `op` to find it there. **`op` ignores that name entirely.** It only reads `OP_SERVICE_ACCOUNT_TOKEN`.

When the value in `1PASSWORD_API_KEY` happens to be a Tailscale pre-auth key (a Tailscale key starts with `A3-XXXX-XXXX-XXXX-XXXX-XXXX`, and users sometimes put them anywhere that looks like a vault), the result is:

```
$ export OP_SERVICE_ACCOUNT_TOKEN="A3-XXXX-XXXX-..."
$ op whoami
[ERROR] failed to DecodeSACredentials: failed to parseToken, format is invalid
```

The error is misleading — it sounds like a vault access problem, but it's actually the *token string itself* being unparseable as a SAC.

## How to diagnose fast

| Prefix / shape on the value | What it really is | What `op` does |
|---|---|---|
| `ops_eyJ...` (~700-900 chars, JWT-shaped) | Real 1Password Service Account credential | Works |
| `A3-XXXX-XXXX-XXXX-XXXX-XXXX` | Tailscale pre-auth key | Rejects |
| `sk-ant-...`, `sk-...` | OpenAI / Anthropic / ElevenLabs API key | Rejects |
| `ghp_...` | GitHub PAT | Rejects |
| Anything else | Probably wrong tool / wrong vault | Rejects |

**Three-line diagnostic for any "1Password doesn't work" complaint on Windows:**

```powershell
# 1. What does the env var actually hold?
[System.Environment]::GetEnvironmentVariable('1PASSWORD_API_KEY', 'User') | Select-Object -First 30
# 2. Does the user have a real SAC file?
Test-Path "$HOME\.ultron\.op_service_account"
# 3. Is OP_SERVICE_ACCOUNT_TOKEN set?
$env:OP_SERVICE_ACCOUNT_TOKEN | Select-Object -First 30
```

## The fix

1. **If the real token lives at `~/.ultron/.op_service_account`**, source it for the current shell:
   ```bash
   export OP_SERVICE_ACCOUNT_TOKEN="$(cat ~/.ultron/.op_service_account)"
   op whoami   # should print URL + Integration ID + User Type: SERVICE_ACCOUNT
   ```

2. **Make it survive across shells.** Add to the project's `.env` (or `${HERMES_HOME:-~/.hermes}/.env`):
   ```bash
   # Real, durable SAC — `op` reads this, not 1PASSWORD_API_KEY
   OP_SERVICE_ACCOUNT_TOKEN=*** ~/.ultron/.op_service_account)
   ```

3. **Clean up the misleading env var.** Either delete `1PASSWORD_API_KEY` or rename it to something that signals what it actually holds (e.g. `TAILSCALE_AUTH_KEY=***`), so future agents don't repeat the mistake.

## When the chained `hermes verify` hangs

The chained `hermes verify` (without `--phase`) loops over every `op://` reference in the env to resolve it before launching each phase. If the user has configured an `op://` reference for a secret that lives in a vault the service account **cannot access**, `op read` blocks for 30s per reference and the verifier appears to hang at `1Password: applied 1 secret`.

**Workarounds:**

1. **Proper wiring (preferred):** `hermes secrets op set ELEVENLABS_API_KEY "op://credentials/ELEVENLABS_API_KEY/ELEVENLABS_API_KEY"` + `hermes secrets op setup` + `hermes secrets op sync`. This only registers references that resolve, so the verifier doesn't loop on unreachable secrets.
2. **Run phases individually:** `hermes verify --phase bootstrap --json` returns a verdict in ~3s; same for `--phase test` and `--phase start`. Each skips the full chained pre-flight.
3. **`--skip-start`** when a server is already running on the target port (verifier would otherwise try to start a conflicting instance).

## Why `OP_SERVICE_ACCOUNT_TOKEN` is the durable answer

- It's the official env var name (`op` checks it on every invocation)
- It works in any shell, any container, any CI
- No biometric prompt, no `tmux` dance, no timeout drama
- The token is **scoped** — when you create the SAC, you grant access only to specific vaults, so a leak doesn't compromise the whole account
- Tokens can be rotated and revoked from `https://my.1password.com/developer`

See `local-ai-orchestration` §1 and §6b for the canonical setup.
