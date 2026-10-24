# Verify user-supplied credentials and IDs before storing

Every external service THRONE talks to (ElevenLabs, Telegram, Notion, HuggingFace, GitHub, Tailscale, Twilio, Stripe, n8n, Ollama, IBM) accepts opaque string IDs that the user may provide from memory, a screenshot, a chat paste, or a copy-paste from another tool. Storing an unverified ID as a default means the next session that boots on the unverified value will fail loudly at first use — and the failure may not surface until hours later when the real call finally runs.

The right pattern: verify against the live API the moment the value lands, before writing to config.yaml / 1Password / override file.

## The recipe

1. **Probe with the live API first.** A single `GET` to the service's resource-by-id endpoint returns 200/404 in 100-300ms. If 200, the ID is real; store it. If 404/400/`not_found`, do not store — proceed to step 2.

   ```python
   import urllib.request, json
   req = urllib.request.Request(
       f"https://api.{service}/v1/{resource}/{user_id}",
       headers={"Authorization": f"Bearer {api_key}"}
   )
   try:
       urllib.request.urlopen(req, timeout=10)
       # ID is real
   except urllib.error.HTTPError as e:
       if e.code == 404:
           # ID is wrong, list inventory
   ```

2. **On 404, list the inventory and match by name.** The user almost always means a specific named resource. The "user gave a wrong ID" rate is high; the "user gave a correct ID for a resource they don't remember the name of" rate is low. Pick the inventory row whose name contains the substring the user used in their message.

   Example (ElevenLabs): user said "the Hitch voice", supplied ID `e3mik6xHn4Sl51poljxKebf0aca38239`. Listing `/v1/voices` returned 44 rows; substring-matching on "Hitch" found `e3mik6xHn4Sl51poljxK` (the actual ID, 21 chars not 30 — the user's value had a stray suffix). Store the inventory ID, not the user-supplied one.

3. **Apply THRONE-name priority for canonical resources.** When the user wants "the THRONE voice" or "the THRONE agent" and the inventory contains an obvious THRONE-named resource, prefer it regardless of what ID the user typed:
   - **ElevenLabs voice** named `Ultron` (`d102SALPLnph2KSq7ejd`) is the persona voice. Prefer over `Hitch` (the user's personal voice) when the context is THRONE, not Hitchy.
   - **ElevenLabs agent** named `Ultron2` (`agent_01jzwkf7dkfdvt5810x1vgrcjs`) is the canonical THRONE agent. The only one in the inventory.
   - **Telegram bot** named `Ultron` is the canonical THRONE bot in the bot team.
   - **Notion page** named `ULTRON HQ` is the ops canon (page id resolved by Notion search, not memory).

4. **If the inventory match is ambiguous or empty, ask the user.** Return a short list (max 5 rows of name + id + category) and let them pick. Do not invent a substitute; do not pick "the closest one" if the closest is wrong context.

5. **Cache the verified ID in three places** (in this order, so the next session sees it):
   1. The op:// URI in `config.yaml` (1Password-bound — survives reboots)
   2. The on-disk cache file for the service (e.g. `~/.ultron/elevenlabs_voice.txt`)
   3. The skill's `SKILL.md` inventory reference, so future agents read the verified ID before checking 1Password

6. **Re-verify on every load.** 1Password SAC is rate-limited; the on-disk cache may be older than the inventory. On session start, when the skill is loaded and any ID is read, run the live `GET` once to confirm the ID is still alive (and the API key still works) before depending on it. A 30-second re-probe beats a 30-minute failure at first use.

## Failure modes covered

- **Screenshot-OCR misread** (`0`/`O`, `l`/`I`, `1`/`l`, `c`/`C`): inventory match by name wins.
- **Stale token / rotated secret**: live API returns 401. Treat as a credentials rotation event, not a config bug.
- **Suffix-extended ID** (user copy-paste got an extra string appended): inventory length comparison catches it.
- **Wrong account's ID** (user typed from a screenshot of a different org's resource): inventory match by name disambiguates by service.
- **Truncated ID** (user copy-paste lost the last few chars): `GET` with the partial ID returns 404, then listing finds the full ID via name match.

## Services where this pattern applies

- **ElevenLabs**: `GET /v1/voices/{voice_id}` and `GET /v1/convai/agents` (with `xi-api-key`).
- **Telegram**: `GET /bot{token}/getMe` (no auth header — the token IS the auth). 200 = live, 401 = revoked.
- **Notion**: `POST /v1/pages/{page_id}` or `POST /v1/search` with the title substring. 200 = page exists, 404 = wrong id.
- **HuggingFace**: `GET https://huggingface.co/api/models/{repo_id}` returns the model card or 404.
- **GitHub**: `gh repo view {owner}/{repo}` works through the gh CLI which is already authed.
- **Tailscale**: `GET /api/v2/tailnet/{tn}/devices/{device_id}` (Bearer auth) — note the `online` field is unreliable, use `lastSeen`.
- **Ollama**: `GET http://localhost:11434/api/show` with `{"name": "<model>"}` returns the manifest or 404.
- **n8n**: `GET {base}/rest/workflows/{id}` with `X-N8N-API-KEY` header.

## Anti-pattern: storing on faith

What you should NOT do:
- Copy the user's string verbatim into `config.yaml` and trust it.
- Trust a 1Password value that was written N hours ago without re-reading.
- Set the default in code to `os.environ.get("X", user_value)` and assume `user_value` is correct because the user typed it.

What the right side looks like:
- Config has the verified value (from inventory match) as a literal default.
- 1Password op:// URI resolves to the same value (cross-checked at gateway start).
- On-disk cache mirrors the verified value.
- Skill's inventory section names the ID explicitly so the next agent reads the verified string, not a possibly-stale op:// resolution.
