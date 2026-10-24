---
name: elevenlabs-personal-voice
description: Personal ElevenLabs TTS via mcp_elevenlabs_synthesize.
---

# Personal ElevenLabs TTS — Hitchy's voice

**Standing preference:** the user's TTS voice is the professional voice
named "Hitch" (`e3mik6xHn4Sl51poljxK`). Do not silently switch to the
older cloned "Hitch" (`0iuMR9ISp6Q7mg6H70yo`), the THRONE-named
"Ultron" clone, or any other voice. When the user says "use Hitch" or
"Hitchy" they mean the professional voice. When the user wants the
THRONE/Ultron persona voice for system output, that is a separate
explicit request — assume personal unless told otherwise.

Use `mcp_elevenlabs_synthesize(text="...")`. Voice ID auto-resolved from ELEVENLABS_VOICE_ID env (1Password `ELEVENLABS_VOICE_ID` → `e3mik6xHn4Sl51poljxK`, voice name "Hitch" category professional; account also has 5 cloned voices including `0iuMR9ISp6Q7mg6H70yo` old Hitch and `d102SALPLnph2KSq7ejd` Ultron).

## Quick call
- `mcp_elevenlabs_synthesize(text="...")` — saves to ELEVENLABS_OUT (default `C:\Users\KING\AppData\Local\hermes\audio_cache\el_<ts>.mp3`)
- Models: `eleven_multilingual_v2` (default, best for AU English), `eleven_turbo_v2_5` (faster, lower quality)

## Voice settings cheatsheet
- Stability 0.5 (default) — balanced
- Similarity boost 0.75 (default) — natural Hitchy
- Style 0.0 — neutral
- Use speaker boost True — clearer

## When NOT to use
- Long-form content (>5000 chars per call) — split into chunks of <5K chars each. A 60-second voice memo (≈600 chars of dense text) fits in one call; a 5-minute essay does not.
- Real-time voice — use agent_id (ElevenLabs Agent ID `agent_01jzwkf7dkfdvt5810x1vgrcjs` = "Ultron2") instead. 26 agents in account; "Ultron2" is the THRONE-aligned one.

## Spell out acronyms as spoken text

ElevenLabs `eleven_multilingual_v2` reads hyphens as hyphens. "M-C-P" becomes "em-cee-pee" (correct, but slow); "8 new M-C-P servers" reads as "eight new em-cee-pee servers" which is what you want. For one-letter letters, "T-H-R-O-N-E" reads as a slow but correct letter-by-letter. For multi-word, hyphenating the acronym is faster than spelling it. Reserve letter-spelling for deliberate emphasis (status codes, IDs).

## Voice ID source

The env `ELEVENLABS_VOICE_ID` comes from a 1Password SECURE_NOTE field whose `notesPlain` is a header line: `ELEVENLABS_VOICE_ID: 0iuMR9ISp6Q7mg6H70yo\nSource: ...`. The bare voice ID is on the first line, after the colon-space. The MCP server reads the env value as-is — if the env is set to the full notesPlain blob, the synth call will fail with HTTP 400. The op:// URI for this item uses `notesPlain` field (not `credential`) and the runtime should strip the `KEY: ` prefix before exposing the value.

## Verification (2026-10-15)
End-to-end test: 78KB MP3 generated for "THRONE online. ElevenLabs pipeline verified." with the personal voice. Works.

## Verification (2026-10-16)
Switched to professional "Hitch" voice (e3mik6xHn4Sl51poljxK) + Ultron2 agent. 53KB MP3 test passed. Account inventory: 44 voices (5 cloned), 26 agents, key length 51. Voice ID resolution found 2 issues: user gave 30-char voice ID truncated from 21-char actual; user gave non-existent agent ID, used Ultron2 (only THRONE-named agent) instead.

## Verify user-supplied IDs against the live account before storing

The user gives a voice_id or agent_id from memory, a screenshot, or a chat message. The value may be wrong for three reasons: (a) a stale one from before a re-issue, (b) a screenshot-OCR character misread (`0`/`O`, `l`/`I`, `c`/`C`), or (c) a clean string but the wrong account's ID. Don't store-and-pray; the live API is the source of truth and a single `GET /v1/voices/{id}` call tells you in 200ms whether the ID is real.

Workflow before storing any new voice_id or agent_id:

1. `GET /v1/voices/{id}` with `xi-api-key`. If 200, the ID is real — store it. If 400 with `voice_not_found`, the ID is wrong; do not store it as a default.
2. If 400, run `GET /v1/voices` (no params) and look for the same voice by name substring. The user almost always means a specific named voice; matching by name resolves the three failure modes above in one step.
3. Same for `GET /v1/convai/agents` for agent_id. List all agents and pick the one whose name matches the user's intent. For THRONE, the agent named `Ultron2` is the only matching agent regardless of what ID the user provides.
4. If the name doesn't match anything, ask the user to pick from the inventory (return `name` + `voice_id`/`agent_id` + category, max 5 rows). Do not invent a substitute.

The Hitch case in 2026-10-16: user supplied `e3mik6xHn4Sl51poljxKebf0aca38239` (30 chars), but the live inventory returned `e3mik6xHn4Sl51poljxK` (21 chars) for the same voice name "Hitch". The string was suffix-extended by the source the user copied from. The fix was trimming the user's input by listing the inventory and matching on name; storing the inventory ID, not the user-supplied one.

## Account inventory reference

Account at the time of writing (verify with `GET /v1/voices` and `GET /v1/convai/agents` when in doubt):

- **Voices (44 total)**: 17 premade voices (Adam, Alice, Bella, Brian, Callum, Charlie, Daniel, Eric, George, Harry, Jessica, Laura, Liam, Lily, Matilda, River, Roger, Sarah, Will) + 22 professional + 5 cloned.
- **Cloned voices (the ones that matter)**: `0iuMR9ISp6Q7mg6H70yo` Hitch (old, superseded), `e3mik6xHn4Sl51poljxK` Hitch (current professional), `d102SALPLnph2KSq7ejd` Ultron (THRONE-named — the persona voice), `d4iFYT2A7IZQeV7BiAOZ` Ck, `EeeBePAEDHEcPOqlGA6N` Charney, `kLv3swM5l1M7goHhzfH5` Cinny's & delilah.
- **Agents (26 total)**: only one THRONE-named — `agent_01jzwkf7dkfdvt5810x1vgrcjs` Ultron2. Others are Sesh, Pip, Pablo, Vision, Alpha, Ace, KRYSYS Coach, KRYSYS Crystal Concierge, Gizmo, Luna, Lava, Buddy, X, Auth, Prof kaos, Joe Kar, Shannos, Eleven, Billing & Account Support, Theropist, Nyx, QAZY Studio Forge Familiar, Photo Shop Director.
- **API key length**: 51 chars, format `sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (the API key prefix is the literal `sk_`, not the long form).

If the inventory changes, update the in-line totals here and re-write the account snapshot to `E:\ultron-memory\elevenlabs\account.json`. The skill should match the live account, not the user's memory of it.

## On-disk cache files (not 1Password)

Two files on disk hold operational secrets that did not make it into 1Password and never should:

- `C:\Users\KING\.ultron\.elevenlabs_key` — the API key, 51 chars. The op:// URI `ELEVENLABS_API_KEY: op://credentials/ELEVENLABS_API_KEY/credential` in config.yaml also points at this value; both resolve to the same string. The on-disk copy is the fallback when 1Password SAC is rate-limited.
- `C:\Users\KING\.ultron\elevenlabs_voice.txt` — current default voice_id (single line, no header). Update this file whenever the active voice changes so the next session that runs before 1Password clears starts on the right voice.

`ELEVENLABS_API_KEY` is NOT in Windows user or machine env vars; do not assume `powershell [Environment]::GetEnvironmentVariable('ELEVENLABS_API_KEY', 'User')` will return anything.
