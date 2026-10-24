---
name: telegram-3bot-blast
description: Telegram bots default/droid/ultron via mcp_telegram_send.
---

# Telegram 3-Bot Blast

3 bots via `mcp_telegram_send(bot=<name>, chat_id=<id>, text="...")`:
- `default` — `TELEGRAM_BOT_TOKEN` (id 8399750561)
- `droid` — `TELEGRAM_BOT_TOKEN_DROID` (id 8657231416, @droid420bot / R2) — verified live 2026-10-15
- `ultron` — `TELEGRAM_BOT_TOKEN_ULTRON` (id 8746389490)

## Tools
- `mcp_telegram_bots` — show which bots have tokens
- `mcp_telegram_send(bot, chat_id, text, parse_mode='')` — send message
- `mcp_telegram_get_updates(bot, offset=0, limit=20, timeout=0)` — long-poll
- `mcp_telegram_me(bot)` — bot info (username, capabilities)
- `mcp_telegram_chat_info(bot, chat_id)` — chat info

## Chat ID discovery
- Send a message to the bot, then `mcp_telegram_get_updates(bot, limit=1)` returns your chat_id
- Group chats have negative IDs; channels use `@channelname`

## Parse modes
- `''` (default) — plain text
- `HTML` — `<b>bold</b>`, `<i>italic</i>`, `<a href="...">link</a>`
- `MarkdownV2` — `*bold*`, `_italic_`, escape special chars

## Verification
- `mcp_telegram_me('droid')` → `{"id":8657231416,"username":"droid420bot","first_name":"R2"}` (all 3 bots loaded)
- Wire confirmed via fake chat_id: `send` returns `HTTP 400: Bad Request: chat not found` for non-existent chat — proves the server is talking to Telegram, not failing on credentials.
- **Token field-id is per-item, not per-vault.** `TELEGRAM_BOT_TOKEN` is a `LOGIN` 1Password item (read field `password`); `TELEGRAM_BOT_TOKEN_DROID` and `TELEGRAM_BOT_TOKEN_ULTRON` are `API_CREDENTIAL` items (read field `credential`). When the bot-team orchestrator or a new integration needs to read a token, branch on `item.category`, not on title. See the 1password skill pitfall on the same topic.

## Chat ID acquisition (the hard part)

A bot cannot initiate a conversation. To get a chat_id for outbound messages, the user (or channel) must send the bot at least one message first. Then `getUpdates` returns the chat_id in `result[].message.chat.id`.

For Hitchy: message `@droid420bot` once from his S23 (or any Telegram client), then `mcp_telegram_get_updates('droid', limit=1)` returns his user_id. Save the chat_id once in memory and reuse — it doesn't change unless the user deletes the chat with the bot.

**Don't try common chat_ids** (e.g. guessing Hitchy's user_id) — Telegram returns 400 for each and there's no shortcut.

## Long-poll behaviour

`get_updates` with `timeout=N` (max 50) blocks server-side for N seconds waiting for new updates. Use `timeout=5` for a quick poll, `timeout=30` for a real listen. Already-seen updates keep their `update_id`; pass `offset=<last_update_id + 1>` on the next call to mark them consumed.
