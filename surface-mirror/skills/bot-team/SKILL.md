---
name: bot-team
description: 6-bot cooperative Telegram team. R2, Jarvis, Ultron + 3.
---
# Bot Team — 6 Comrades

## When to use

Use this skill any time the user mentions Telegram bots, the team roster (R2 / Jarvis / Ultron / Towelle / SHADOW / sixth), or wants to send, poll, or read state from the 6-bot cooperative system. Also use before declaring a bot "stale" or "401" — always re-verify the token against `getMe` first; the user may have refreshed credentials you have not picked up.

6 Telegram bots working as a coordinated team. Arch: blackboard + bonds + personas.

## Bots (per `E:\ultron-memory\bot-team\team.json`)

| bot_id | username | name | role | status |
|---|---|---|---|---|
| r2 | @droid420bot | R2 | Companion Droid | live (2026-10-15) |
| jarvis | @Homelander420bot | Jarvis | Chief of Staff | live |
| ultron | @Ultron420bot | Ultron | Sovereign Coordinator | live |
| shadow | @shadowpc420bot | SHADOW | Shadow Operative | live (2026-10-16 via token-overrides) |
| sixth | @sixth420bot | sixth | Synthesist | live (2026-10-16 via token-overrides) |
| towelle | @Oh420bot | Megatron | Transformer | live (2026-10-16 via token-overrides) |

`@Oh420bot` had its display name renamed Towelle→Megatron via BotFather `/setname` on 2026-10-16; the **username** is still `@Oh420bot` and the **token** is bound to that username. `name` in the table reflects the BotFather display name; `bot_id` is the canonical id used in `team.json` and routing, never the display name.

## Tools (`mcp_bot-team_*`)

- `team_me` — verify all 6 tokens
- `team_status` — bots + bonds + last event + live_token per bot
- `team_send(text, bot='', chat_id='', parse_mode='')` — route + send one message
- `team_broadcast(text, parse_mode='')` — all 6 bots send to principal
- `team_route(text)` — show which bot would handle (no send)
- `team_poll(bot='all', timeout=5)` — long-poll one or all bots
- `team_capture_chat_id(bot='')` — quick poll to grab principal's chat_id
- `team_blackboard(limit=20)` — recent events
- `team_bonds()` — bond ledger (per-bot strength, interactions, mood)
- `team_persona(bot)` — read persona markdown

## Routing

`/r2 /droid /jarvis /ultron /towelle /shadow /sixth` → direct address.
`/research /analyze /explain` → towelle.
`/scan /perimeter /threat` → shadow.
`/synthesize /weave /summary` → sixth.
`/status /team` → ultron.
`/help /start` → jarvis.
default → r2.

## Blackboard

`E:\ultron-memory\bot-team\blackboard\team.json` — team roster + routing + principal chat_id.
`E:\ultron-memory\bot-team\blackboard\events.json` — append-only event log (max 200).
Every send/receive writes an event. Every message updates `bonds.json`.

## Bond ledger

`E:\ultron-memory\bot-team\bonds\bonds.json` — per-bot `strength` 0-100, auto-increments 0.05/message, mood_log[-50]. Initial values reflect the persona seed:
- ultron 100, r2 95, jarvis 85, shadow 80, sixth 78, towelle 75.

## Personas

`E:\ultron-memory\bot-team\personas\<bot_id>.md` — frontmatter + free-form character notes (archetype, alignment, element, iconography, voice samples, memory, limits).

## First-time setup

1. Hitchy messages any of the 3 live bots from his phone (e.g. /start to @droid420bot).
2. `mcp_bot-team_team_capture_chat_id` polls getUpdates and grabs the chat_id into the blackboard.
3. Now `mcp_bot-team_team_send(text, bot='r2')` works without explicit chat_id.

## Stale tokens

**As of 2026-10-16, all 6 bots are live.** SHADOW / sixth / Megatron are wired through `token-overrides.json` because 1Password was rate-limited when their tokens landed; R2 / Jarvis / Ultron stay on 1Password. See `references/token-overrides.md` for the override pattern (read overrides FIRST, fall back to 1Password; promote to 1Password when the rate limit clears).

**Where Hitchy's Telegram lives**: TDesktop (`C:\Users\KING\AppData\Roaming\Telegram Desktop\`) is the logged-in client. **Cyclone-C4 (the actual phone)** does NOT have Telegram installed by default — Hitchy's routine is to install and sign in on the phone only when the bot team is being verified locally. **S23 is offline on Tailscale (last seen 58d ago)** — don't assume an "S23 phone" is reachable; verify with `tailscale status | grep -E 's23|cyclone'` before claiming phone-side state. Do not promise to drive the phone without first checking the tailnet; the only working path to get a fresh bot token is the user re-issuing in @BotFather on TDesktop and pasting the value as **plain text** (not a screenshot). After pasting, store it in 1Password with the same title (`TELEGRAM_BOT_TOKEN_TOWELLE` etc) — config.yaml's `op://` URIs reference the title, renaming breaks the wire.

## Per-bot commands (set on all 6 live bots)

- **Jarvis** (Homelander420bot): /start /help /status /route /recall /yes
- **R2** (droid420bot): /start /status /mood /companion /loved
- **Ultron** (Ultron420bot): /start /sovereign /directive /consensus /manifesto /seat /endorse
- **SHADOW** (shadowpc420bot): /start /scan /perimeter /threat /ack /watch
- **sixth** (sixth420bot): /start /synthesize /weave /summary /pattern /hold
- **Megatron** (Oh420bot, formerly Towelle): /start /tess /recon /manifest /forge /attune

All six bots also have `setMyDescription` + `setMyShortDescription` set. Re-run all three on any bot whose token is refreshed.

## Don'ts

- Don't send messages from a bot to another bot (use the blackboard, not Telegram DMs).
- Don't delete bonds.json without an explicit /reset command.
- Don't expose tokens in any user-facing message — they're already in 1Password (or in the override file, see `references/token-overrides.md`).
- Don't change the 1Password item title (op:// URIs in config.yaml depend on the name).
- Don't use `team_me` results as a stand-in for `getMe`. The MCP probe goes through the same token path your outbound calls use, so if `team_me` says live and `send` says 401, the token changed under you (BotFather revoke) — re-read the token, don't trust cached state.

## Pitfalls

- **Never declare a bot stale from a 401 alone.** The user pastes tokens from a screenshot, message, or live @BotFather reply expecting them to be the most-recent issued. A 401 can also mean the SAC pulled a stale cached item, the field-id was wrong (LOGIN items use `password`, not `credential`), or the token was revoked between creation and your test call. Always (a) re-read the token from 1Password, (b) re-call `getMe`, (c) re-state the failure with the exact `error_code` and timestamp before asking the user to fetch a fresh one. Default to "I tested, here's the 401" rather than "the tokens you gave me are wrong."

- **Stop looping after the second 401 on the same bot.** If the user re-pastes a fresh token from @BotFather and it still 401s, do not keep re-testing on your own initiative or generate more character-variant guesses — that is repetition the user already saw. State once, in one short message, that the new token also 401'd, point at the most likely cause (auto-revoked between BotFather generation and storage; screenshot may be from a stale message), and ask the user to **paste the raw token as plain text** or to verify the screenshot's timestamp is from "just now". Do not produce more analysis without new information; the user knows what they saw better than any heuristic you can apply to the token string.

- **A screenshot of an @BotFather reply with a 2:45 PM timestamp and the same `DF` reaction across multiple uploads is a stale paste, not a new token.** The user is forwarding the same Telegram message from TDesktop chat history, possibly because it was the only screenshot they could find. Don't keep "re-revoking and re-trying" on a 401 loop — the real action is to confirm with the user that the screenshot is fresh, or to ask for the raw text of the latest `/token` reply they can see in @BotFather.

- **On a stuck token wire, the user prefers a one-line status table over a paragraph.** When a single bot is stuck on 401 across multiple turns, present a 6-row table of all 6 bots with status, token source, and "next step" — the user immediately sees which bots are live and which need action. This compresses the diagnostic and gets a faster correct answer than another round of analysis.
- **Token field-id is per-item, not per-vault.** `TELEGRAM_BOT_TOKEN` is a `LOGIN` item (field `password`); the per-bot `TELEGRAM_BOT_TOKEN_<NAME>` items are `API_CREDENTIAL` (field `credential`). When wiring new bots, read the item with `op item get --format=json` and branch on the `category` to pick the right field. Hardcoding `credential` for all returns the right value for API_CREDENTIAL items and `ERR: could not read secret` for LOGIN ones.
- **Bot HTTP API tokens are flat strings with no embedded user identity.** The token `1234567890:AAGxxxxx` is the entire credential — no separate secret, no signing. `getMe` is the universal probe: returns 200 with `{ok:true,result:{id,username,first_name}}` on success, 401 on revoke/expiry. Always re-verify after any 1Password write; a screenshot token can be hours old by the time it lands in the vault, and @BotFather's "Revoke current token" button invalidates the prior value silently. Never conclude "the user gave me a bad token" — conclude "I tested and got 401; please re-issue."
- **Programmatic user-session access via tdata/telethon does not work on a live TDesktop.** tdata is locked while the app runs (`opentele.TFileNotFound: Could not open key_data`); the legacy `~/.ultron/telegram.session` is partially-bound (auth_key present, no user entity, `is_user_authorized()=False`); re-auth requires an SMS code to Hitchy's AU phone. The only working path for fresh bot tokens is the user re-issuing in @BotFather on TDesktop and pasting the value. Do not invent alternate paths; the user is faster than the workarounds.
- **Per-bot `setMyCommands`/`setMyDescription`/`setMyShortDescription` are required for the bot to present itself in chat lists.** Without them, the bot looks blank in Telegram search. After refreshing a stale token, re-run the menu + description calls (see Per-bot commands section) so the bot reflects the team identity, not the default BotFather stub.
- **Principal chat_id is captured lazily on first inbound message.** A bot cannot initiate a conversation; outbound `team_send` fails with `ERR: no principal chat_id` until the user sends the bot anything. `team_capture_chat_id` calls `getUpdates` with a short timeout and persists the chat_id into the blackboard the moment the principal's first message is seen. Do not loop calling it in the same session — the loop cannot produce a chat_id without an inbound message; the only fix is for the user to send a real message.
- **The screenshot-OCR token misread is real and not worth brute-forcing.** Telegram bot tokens are `<digits>:<base64url>` — the digits portion (the bot id) is reliable to OCR but the ~35-char `AAG...` body is not. `I` and `l`, `0` and `O`, `c` and `C` are interchangeable to vision_analyze. Six variants tested (l/I, 0/O, c/C) all returned 401 on one bot. The right move after one confirmed 401 is to ask the user to **paste the raw token as plain text** — the value is already in the user's chat from BotFather, no re-screenshot needed. Don't burn more time on character variants.

- **The single character that breaks a token is most often `0` (zero) vs `O` (capital letter) in the base64url portion.** A `0` from a Telegram screenshot rendered as `0` on a phone dark theme, but a freshly typed `O` in the same position flips the second character from digit to letter. The bot id prefix `8213434544:` matches either way; only the body distinguishes. After 1+ confirmed 401 on a screenshot token, the right move is **not** "try more character variants" but "ask the user to type the token, not screenshot it." Worked example: Megatron / @Oh420bot was 401 on four screenshot attempts with `0` in the body; the user-pasted text had `O` (letter) at the same position, and the very first typed variant returned 200 ok=true. Vision can misread one character; a 35-char base64url body has ~35 single-character failure points.

- **A 401 on a freshly re-typed token (not screenshot) means the token itself is auto-revoked or wrong, not OCR.** After the user pastes a token as plain text, the only remaining 401 causes are: (a) BotFather auto-revoked the token between issue and paste (each `/token` reply is single-use and rotates if a new one is generated), (b) the user pasted the wrong bot's token (e.g. SHADOW's token into the towelle/Megatron slot), (c) the SAC cached an old item in 1Password. Verify by listing the override file keys vs the slot the token is being written to, and re-reading the SAC value via `op read op://.../credential` if 1P is not rate-limited. Don't loop on character variants past the second typed attempt.

- **Cyclone-C4 is the phone. S23 is offline.** Tailnet device identities do not map to "which is the phone Hitchy is reading" without an explicit `tailscale status` check. Cyclone-C4 (`100.71.239.65`, `192.168.4.241`) is the live Android — rooted, Magisk, Termux, no SIM. S23 (`100.118.95.91`) has been offline 58d+. **Do not assume "the phone" without verifying the tailnet peer is online.** Same applies to MSI (`100.83.120.56`, online intermittently via WoL) and any other named device. When the user says "send it to my phone", ask: which one, or verify before claiming delivery.

- **Login codes for Telegram Mobile on a SIM-less device go to "the other signed-in device", which is TDesktop on THRONE.** The 5-digit code arrives as a service message in the user's "Telegram" chat in TDesktop, not as an SMS, not as an email. To extract the code: bring TDesktop to the foreground, navigate to the Telegram service chat, and read the 5-digit string. Driving TDesktop while Hitchy is using it is destructive — prefer the TDesktop auto-notification (it pops a small toast with the code on screen) over programmatic window manipulation. If TDesktop is rendering as a black screen, force-quit and re-launch; the code is still good for ~5 minutes from issue.
- **Bot display name ≠ username ≠ token binding.** BotFather `/setname` changes only the display name shown in chat lists and `first_name` in `getMe`. The `@username` (and the token bound to it) stay the same. When a user says "I renamed Towelle to Megatron," that means `display_name_history: ['Towelle', 'Megatron']` in `team.json`; the `bot_id` key stays `towelle` (or whatever was used at creation). Wire routing by username, not display name.
- **Token overrides are a hot cache, not a replacement for 1Password.** The bot-team `E:\ultron-memory\bot-team\token-overrides.json` exists because 1Password SAC was rate-limited when fresh tokens landed. After 24h of overrides-only, surface the `promote_to_1p: true` items to the user; do not let them silently rot. See `references/token-overrides.md` for the full workflow.
