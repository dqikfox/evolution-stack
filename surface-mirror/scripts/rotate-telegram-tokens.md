# Rotate Telegram Bot Tokens

## Current State (after fix on 2026-10-06)

| 1Password item | Bot | Status |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_ULTRON` | @Ultron420bot (id 8746389490) | RATE-LIMITED by Telegram — long-poll 409 after rapid restarts |
| `TELEGRAM_BOT_TOKEN_DROID` | @droid420bot (id 8657231416) | ✅ ACTIVE — used by current shop-bot |

## Deleted duplicates

- `TELEGRAM_BOT_TOKEN` (was identical to ULTRON)
- `TELEGRAM_DQIKFOX_TOKEN` (was identical to ULTRON)

## How to get a fresh Ultron token

1. Open Telegram → message @BotFather
2. Send `/mybots`
3. Select **Ultron** bot
4. Tap "API Token" → "Revoke current token" → confirm
5. BotFather generates a fresh token
6. Update 1Password item `TELEGRAM_BOT_TOKEN_ULTRON` with the new token:
   ```bash
   op item edit TELEGRAM_BOT_TOKEN_ULTRON --vault credentials \
     credential=<new-token-here>
   ```
7. Verify the new token works:
   ```bash
   op item get TELEGRAM_BOT_TOKEN_ULTRON --vault credentials --reveal | \
     xargs -I{} curl -s "https://api.telegram.org/bot{}/getMe" | python -m json.tool
   ```
9. Once verified, switch shop-launcher.py back to ULTRON:
   - Edit `C:\Users\KING\AppData\Local\hermes\scripts\shop-launcher.py`
   - Change `TOKEN_REF = ...` to point to `op://credentials/TELEGRAM_BOT_TOKEN_ULTRON/credential`
   - Or: `export SHOP_BOT_TOKEN_REF=op://credentials/TELEGRAM_BOT_TOKEN_ULTRON/credential` before launch
10. Restart bot with 90-second delay:
    ```bash
    cmd /c "C:\Users\KING\AppData\Local\hermes\scripts\restart-shop-bot.cmd"
    ```

## Why the duplicates existed

3 tokens pointed to the same bot — likely from manual token rotations over time without deleting the old entries. Revoking a token doesn't delete the 1Password item that stored it, so all 3 keys remained valid for the same bot. Since @BotFather only allows ONE active token per bot, the "rotated" tokens weren't actually new — they were copies of the same canonical token.

## Long-term hygiene

- After any token rotation, delete the old 1Password entry
- Use `op item get TELEGRAM_BOT_TOKEN_ULTRON --reveal` to verify before relying on a token
- One canonical token per bot, no duplicates