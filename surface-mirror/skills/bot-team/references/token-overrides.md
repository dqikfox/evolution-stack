# Token Overrides — runtime fallback for 1Password rate limits and 401s

## The problem

The 1Password Service Account (SAC) hits `429 Too Many Requests` after bursts of token writes (e.g. 5+ bot tokens saved within minutes). When that happens, **all** `op item get` / `op item create` calls return errors and the bots that read tokens through 1Password go 401.

Worse: a token pasted from a screenshot can be revoked between capture and storage (BotFather's "Revoke current token" invalidates the prior value silently). The user hands you a screenshot they took minutes ago, you store it, the bot 401s. Without a fallback, the loop becomes "re-paste → store → 401 → re-paste".

## The pattern: overrides file at known path

For each integration that needs hot-swap of a token (Telegram bots, n8n API keys, anything callable at runtime), maintain a small JSON file that the integration's MCP server reads **first** and falls back to 1Password only if the override is missing.

**Location:** `E:\ultron-memory\bot-team\token-overrides.json` (bot-team specifically). For other integrations, pick a stable per-app path under the same `E:\ultron-memory\<app>\` tree.

**Shape:** Two equivalent encodings are in use across the project; the integration code reads either.

*Nested (preferred for new code):*
```json
{
  "bots": {
    "shadow": {
      "token": "1234567890:AAGxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "set_at": "2026-10-16T03:11:00Z",
      "source": "screenshot paste",
      "promote_to_1p": true
    },
    "sixth": {
      "token": "1234567890:AAGyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
      "set_at": "2026-10-16T03:14:00Z",
      "source": "BotFather /token via TDesktop",
      "promote_to_1p": true
    }
  }
}
```

*Flat (what bot-team actually uses, because the env-var-name is the natural key):*
```json
{
  "TELEGRAM_BOT_TOKEN_SIXTH": "1234567890:AAGxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "TELEGRAM_BOT_TOKEN_SHADOW": "1234567890:AAGyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
  "TELEGRAM_BOT_TOKEN_TOWELLE": "1234567890:AAGzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
}
```

The flat shape is direct-drop-into-`os.environ`: the server reads `overrides[env_var_name]` and the value is the token string, no field extraction. The nested shape gives per-bot metadata (set_at, source, promote_to_1p) that the flat shape loses — the flat shape in `bot-team` was chosen for speed (no extra parsing layer) and the metadata is mirrored into `blackboard/team.json` instead.

- `promote_to_1p: true` is the next-action reminder. When the SAC rate limit clears, write the override value into the 1Password item with the same title the `op://` URI references, then flip this to `false`.
- The `set_at` ISO timestamp is the freshness check: if a token has been sitting in overrides for >24h and not yet in 1Password, surface it in the daily check.
- The file is plaintext on disk — set NTFS ACL so only the THRONE\KING account reads it, and never commit to git.

## Read order in the MCP server

```python
def get_bot_token(bot_id: str) -> str:
    # 1. Override file (rate-limit / 401 escape hatch)
    overrides = read_json(OVERRIDES_PATH)  # cached for 30s
    if overrides and overrides.get("bots", {}).get(bot_id, {}).get("token"):
        return overrides["bots"][bot_id]["token"]

    # 2. 1Password via the configured item title
    item_title = BOT_TO_1P_TITLE[bot_id]  # e.g. "shadow" -> "TELEGRAM_BOT_TOKEN_SHADOW"
    return read_op_item_field(item_title, vault="credentials", field=auto_field(item_title))
```

`auto_field()` is the LOGIN-vs-API_CREDENTIAL branch: read the item with `--format=json`, look at `category`, and pick `password` (LOGIN) or `credential` (API_CREDENTIAL). Hardcoding `credential` works for fresh-bot API_CREDENTIAL items but returns `ERR: could not read secret` for the legacy `TELEGRAM_BOT_TOKEN` which is a LOGIN item.

## When to use this vs. just retrying 1Password

| Situation | Use overrides? |
|---|---|
| SAC returns 429 / "Too many requests" | yes — write to overrides, don't keep retrying op |
| New token paste, not yet promoted | yes — overrides is the wire path until promoted |
| Stale 1Password value but user already pasted fresh | yes — overrides has the live value, 1P doesn't |
| 1Password is healthy, no recent paste | no — read directly from 1P |
| User explicitly says "store in 1Password" | no — write to 1P directly, skip overrides |

## Promotion workflow (when 1Password recovers)

Once `op whoami` succeeds again and `op item get` returns the existing title without 429:

```bash
# 1. Read the override value
TOKEN=$(jq -r '.bots.<id>.token' /e/ultron-memory/bot-team/token-overrides.json)

# 2. Decide field (LOGIN or API_CREDENTIAL)
ITEM=TELEGRAM_BOT_TOKEN_<NAME>
CATEGORY=$(op item get "$ITEM" --vault credentials --format json | jq -r '.category')
FIELD=$([ "$CATEGORY" = "API_CREDENTIAL" ] && echo credential || echo password)

# 3. Write
op item edit "$ITEM" --vault credentials "$FIELD=$TOKEN"

# 4. Flip the override
jq '.bots.<id>.promote_to_1p = false' /e/ultron-memory/bot-team/token-overrides.json > /tmp/x && mv /tmp/x /e/ultron-memory/bot-team/token-overrides.json
```

Then call `getMe` against the bot to confirm the 1P value matches.

## What this is NOT

- Not a replacement for 1Password. The vault remains the source of truth; overrides are a hot cache.
- Not a secret scanner. NTFS ACL keeps it private; do not echo contents in chat.
- Not a per-bot multi-region failover. One override entry per bot, last-write-wins.
- Not safe to commit. Add `E:/ultron-memory/**/token-overrides.json` to every repo's `.gitignore`.

## Pitfalls

- **Treat overrides like 1P — never echo the token value back in chat.** A user's "show me the token" request should pull the masked value from `op item get --format=json` (`fields[].value` only when the user explicitly requests reveal), not the plaintext in overrides.
- **Always verify the override with `getMe` before reporting a bot as live.** A user pastes a token, you write to overrides, the bot 401s because the screenshot OCR misread a character. The override file says "live" but the wire says no — only the wire is truth. The `team_me` MCP tool exists for exactly this probe.
- **Don't keep writing to overrides when 1Password is healthy.** It becomes a write-only log that drifts from the vault. The `promote_to_1p: true` flag is the audit hook; if it sits for >24h, raise it to the user.
- **Override file is per-app, not global.** Don't add `E:\ultron-memory\bot-team\token-overrides.json` paths to other integrations. Each integration that needs hot-swap has its own file under its own dir (`E:\ultron-memory\<app>\overrides.json` or similar). Sharing one file across integrations means a stray field name change breaks two things at once.
