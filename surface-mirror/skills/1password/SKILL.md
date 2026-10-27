---
name: 1password
description: Set up op CLI, sign in, and read or inject secrets.
version: 1.0.0
author: arceus77-7, enhanced by Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [security, secrets, 1password, op, cli]
    category: security
setup:
  help: "Create a service account at https://my.1password.com → Settings → Service Accounts"
  collect_secrets:
    - env_var: OP_SERVICE_ACCOUNT_TOKEN
      prompt: "1Password Service Account Token"
      provider_url: "https://developer.1password.com/docs/service-accounts/"
      secret: true
---

# 1Password CLI

Use this skill when the user wants secrets managed through 1Password instead of plaintext env vars or files.

## Requirements

- 1Password account
- 1Password CLI (`op`) installed
- One of: desktop app integration, service account token (`OP_SERVICE_ACCOUNT_TOKEN`), or Connect server
- `tmux` available for stable authenticated sessions during Hermes terminal calls (desktop app flow only)

## When to Use

- Install or configure 1Password CLI
- Sign in with `op signin`
- Read secret references like `op://Vault/Item/field`
- Inject secrets into config/templates using `op inject`
- Run commands with secret env vars via `op run`

## Authentication Methods

### Service Account (recommended for Hermes)

Set `OP_SERVICE_ACCOUNT_TOKEN` in `${HERMES_HOME:-~/.hermes}/.env` (the skill will prompt for this on first load).
No desktop app needed. Supports `op read`, `op inject`, `op run`.

```bash
export OP_SERVICE_ACCOUNT_TOKEN="your-token-here"
op whoami  # verify — should show Type: SERVICE_ACCOUNT
```

### Desktop App Integration (interactive)

1. Enable in 1Password desktop app: Settings → Developer → Integrate with 1Password CLI
2. Ensure app is unlocked
3. Run `op signin` and approve the biometric prompt

### Connect Server (self-hosted)

```bash
export OP_CONNECT_HOST="http://localhost:8080"
export OP_CONNECT_TOKEN="your-connect-token"
```

## Setup

1. Install CLI:

```bash
# macOS
brew install 1password-cli

# Linux (official package/install docs)
# See references/get-started.md for distro-specific links.

# Windows (winget)
winget install AgileBits.1Password.CLI
```

2. Verify:

```bash
op --version
```

3. Choose an auth method above and configure it.

## `op item create` on this build needs `--title`

op 2.30.3 here treats a POSITIONAL argument as a field assignment, not as the title. `op item create "My Item"` fails with `cannot add a field with no value My Item`, and so does every variant of the JSON template - the error names whatever it thinks is a field, which makes it look like a template problem when it is an argument-parsing problem.

```bash
op item create --title "My Item" --category "API Credential" --vault credentials \
  credential="$THE_VALUE" "notesPlain=$THE_NOTE"
```

A JSON template file also works as a positional, but ONLY with `--title` given separately - and the template's own `category` key makes op build a default field set it then cannot fill, so the category belongs on the flag and the template should carry only `title` and `fields`.

**Read a secret from its file at call time, never type it:** `KEY=$(grep -oE 'OPENAI_API_KEY=.*' "$FILE" | cut -d= -f2-)` then `credential="$KEY"`. The value never appears in the command you write or in a shell history.

**`op item get` does not reveal a concealed field.** Add `--reveal`, or the credential reads back as empty and you will think the write failed when it landed.

**`--fields` takes a FIELD NAME, never `name=value`.** `op item get HF_TOKEN --fields credential=HF_TOKEN` parses the whole string `credential=HF_TOKEN` as a field NAME, matches nothing, and returns an EMPTY STRING with exit code 0 — no error, no warning. The correct form is `--fields credential --reveal`. A zero-length result from `op item get` therefore means "you asked for the wrong field", not "the secret is unset".

**Always length-check a secret before using it.** Because `op` fails silently
here, an empty token becomes a malformed HTTP header far from its cause
(`Illegal header value b'Bearer '` looks like a network bug, not a missing
secret). Probe the value before it is used:

```bash
T=$(op item get HF_TOKEN --vault credentials --fields credential --reveal 2>/dev/null | tr -d '\r\n')
[ -n "$T" ] || { echo "empty token: wrong field name or missing --reveal" >&2; exit 1; }
```

Compare lengths, not values, when checking a secret against another copy.

**Do not destroy the old credential while adding a new one.** A new project key goes in a NEW item with its own title, scope and verdict in the note; the old item stays untouched until the user says otherwise.

## Hermes Execution Pattern (desktop app flow)

Hermes terminal commands are non-interactive by default and can lose auth context between calls.
For reliable `op` use with desktop app integration, run sign-in and secret operations inside a dedicated tmux session.

Note: This is NOT needed when using `OP_SERVICE_ACCOUNT_TOKEN` — the token persists across terminal calls automatically.

```bash
SOCKET_DIR="${TMPDIR:-/tmp}/hermes-tmux-sockets"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/hermes-op.sock"
SESSION="op-auth-$(date +%Y%m%d-%H%M%S)"

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell

# Sign in (approve in desktop app when prompted)
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "eval \"\$(op signin --account my.1password.com)\"" Enter

# Verify auth
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "op whoami" Enter

# Example read
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "op read 'op://Private/Npmjs/one-time password?attribute=otp'" Enter

# Capture output when needed
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200

# Cleanup
tmux -S "$SOCKET" kill-session -t "$SESSION"
```

## Common Operations

### Read a secret

```bash
op read "op://app-prod/db/password"
```

### Get OTP

```bash
op read "op://app-prod/npm/one-time password?attribute=otp"
```

### Inject into template

```bash
echo "db_password: {{ op://app-prod/db/password }}" | op inject
```

### Run a command with secret env var

```bash
export DB_PASSWORD="op://app-prod/db/password"  # example op:// reference, resolved by `op run`
op run -- sh -c '[ -n "$DB_PASSWORD" ] && echo "DB_PASSWORD is set" || echo "DB_PASSWORD missing"'
```

## Hermes external secret sources

Hermes resolves secrets from `config.yaml` under `secrets.<source>.env`, where each value is an `op://vault/item/field` reference. The 1Password source is enabled by default and resolves the whole map at startup ("1Password: applied N secrets").

**A plaintext value in `~/.hermes/.env` SHADOWS the vault reference of the same name.** The env loader applies dotenv with `override=True` BEFORE the external sources run, and a source SKIPS a name that already exists in the environment. A literal in `.env` therefore silently wins, the vault stops being authoritative, and that secret never rotates. Conversely, a LITERAL entry inside the `secrets.onepassword.env` map is skipped by the source ("is not an op:// secret reference") and is never injected at all, so the variable is simply absent from the process.

Order of operations when adding a secret:

1. Store it in the vault with a **dedicated field**, not a note. `op://vault/Item/notesPlain` injects the entire note text, and a note that merely CONTAINS the value is worse than no reference at all.
2. Add `NAME: op://vault/Item/field` to `secrets.onepassword.env` in `config.yaml`.
3. Remove the literal from `.env` — only after proving the two are byte-identical.
4. Keep `OP_SERVICE_ACCOUNT_TOKEN` in `.env`; it is the bootstrap the source needs to authenticate at all. Every other secret belongs in the vault.

Audit with `hermes/scripts/audit_secret_shadowing.py`: it resolves every reference, compares SHA-256 digests against any `.env` literal, and reports SAFE TO STRIP / VAULT IS STALE / vault-only. Compare digests, never values.

## Guardrails

- Never print raw secrets back to user unless they explicitly request the value.
- Prefer `op run` / `op inject` instead of writing secrets into files.
- If command fails with "account is not signed in", run `op signin` again in the same tmux session.
- If desktop app integration is unavailable (headless/CI), use service account token flow.

## Pitfalls

- **Service-account `whoami` succeeds ≠ service-account can see every vault.** A service account is a separate identity from the human account — it only sees the vaults it was explicitly granted access to in 1Password admin (Settings → Service Accounts → grant vaults). A token whose `whoami` reports `Type: SERVICE_ACCOUNT` will still return a single vault from `op vault list` if that's all it was given. Personal SSH keys, app logins, and other human-account items live in the user's Personal / Private vault, which is only reachable through the desktop-app unlock path (interactive master password). When a secret is not findable by the service-account token, do not loop on `op item list` and `op item get` against different titles — confirm the vault boundary first with `op vault list`, and surface the gap to the user instead of guessing.
- **`OP_SERVICE_ACCOUNT_TOKEN` empty string = silent fallback to desktop app.** If the env var is set to `""` (or unset), `op` falls back to the desktop-app IPC bridge. When the desktop app is running but locked, commands fail with `authorization timeout` rather than an obvious auth error — that means the master password needs unlocking, not the service account.
- **Don't `taskkill /F 1Password.exe` to "restart" the app.** It kills the agent IPC pipe and leaves the rest of the system in a half-unlocked state until the user relaunches from Start Menu. Use the desktop app's own UI (`--quick-access`, `--silent`) to interact, or just wait for the user to unlock.
- **SSH keys read with `op read` still need `IdentityAgent` set in `~/.ssh/config`** to be picked up by OpenSSH. Reading the key into a file is not enough; on Windows, set `IdentityAgent \\.\pipe\openssh-ssh-agent` (1Password's named pipe) so SSH consults the unlocked vault instead of file-based keys.
- **Always prove a token works against its service before declaring it stored.** After `op item create --category=API_CREDENTIAL credential=<token>` (or any secret write), call the service's cheap read endpoint (Telegram `getMe`, GitHub `user`, Stripe `balance/retrieve`, etc.) and confirm a 200/identity response before reporting the wiring as complete. A token copied wrong, revoked early, or pasted with a stray character fails silently and only surfaces hours later when a real call returns 401. This is a cheap probe — fail loud, fail early.
- **`op item edit <title> notesPlain=<multi-line>` hangs >15s.** Long multi-line `notesPlain` values via the CLI flag hit a 1Password desktop prompt and the SAC stays blocked. Use `op item edit` only for short scalar fields. For multi-line notes, use the **JSON-template stdin form** of `op item create`/`op item get` and then post-process with `jq` or a Python script that round-trips through `op read`. Alternatively, write the note to a local file in the vault's working area and reference it from `notesPlain` as a one-liner with a file path.
- **`API_CREDENTIAL` items store the value in field `id=credential`; `LOGIN` items store the value in field `id=password`.** A token for a Telegram bot can live in either category depending on how the human entered it via the desktop app. `op read 'op://vault/TITLE/credential'` returns an error on a LOGIN item; `op item get TITLE --format=json` shows the real field id, and the script must branch on it instead of hardcoding `credential`.
- **`op item create --template file.json` fails with "cannot create an item from template and stdin at the same time" when stdin is a pipe or heredoc.** `op` treats any non-TTY stdin as a template source and rejects the combination. From Python pass `stdin=subprocess.DEVNULL`; from bash append `< /dev/null`.
- **You cannot import an existing private key into an `SSH_KEY` item via the CLI.** Assigning `private key=...` is refused ("cannot assign the reserved field") and a template with `private_key` creates an item the CLI then cannot read back. Store imported SSH keys as a `SECURE_NOTE` via template JSON (`notesPlain` = private key + public key + where it lives on disk); `--generate-key` is only for op-created keys.
- **`op item get --format json` redacts values that look like private keys** (`[REDACTED PRIVATE KEY]`) in its output, so round-trip verification of stored key material silently fails. Add `--reveal` when comparing a stored key against the on-disk original.
- **Invoke `op` through bash, not a Python `subprocess` call, on Windows.** The same argument list that works in bash can fail from Python with `invalid JSON provided` on `op item edit`; run `op` as a terminal/bash command (or via a bash `-c` wrapper) and only use Python for JSON parsing of stdout.
- **Compare a plaintext secret against the vault without echoing either side.** Read both into shell variables and print only `MATCH`/`DIFFER` plus character counts; a length mismatch alone tells you the vault copy is stale without leaking a character. Probe the live service on ANY mismatch — an identical-but-revoked token still needs flagging, not archiving.
- **A vault field can hold a placeholder instead of a credential.** An 11-character `sk-ant-…` value is a placeholder, not a revoked key. Before declaring a credential revoked, check its length and shape and probe the live service — the failing provider is often NOT the one you assumed, and "401" gets blamed on the wrong vendor.
- **`op item edit <title> "label=value" --vault <v>` can work from a Python `subprocess` on Windows**, but always read the item back and compare the field value before trusting the write. The bash-first guidance remains the safe default; verified read-back is what actually proves the edit landed.
- **Wipe plaintext secret files by overwriting before deleting** (`head -c N /dev/urandom > file && rm file`), and only after the vault copy round-trips clean. Deleting without the overwrite leaves the value recoverable on the filesystem.

## CI / Headless note

For non-interactive use, authenticate with `OP_SERVICE_ACCOUNT_TOKEN` and avoid interactive `op signin`.
Service accounts require CLI v2.18.0+.

## References

- `references/get-started.md`
- `references/cli-examples.md`
- https://developer.1password.com/docs/cli/
- https://developer.1password.com/docs/service-accounts/
