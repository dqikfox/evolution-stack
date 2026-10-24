# Vision: keeping model defaults in lockstep

When Vision's chat says one model but the dashboard shows another, the cause is almost always that **the model name is hard-coded in multiple places that drifted apart**. Vision has at least four places where the active model is named:

| File | What it controls | Variable / line |
|---|---|---|
| `live_chat_app.py:416` | `current_model` (local Ollama chat default) | module-level assignment |
| `nexus_bridge.py:24` | `DEFAULT_MODEL` (NEXUS-routed model) | env-overridable since 2026-08 |
| `live_chat_ui.html:321` | Welcome toast text `"Model: <name>."` | static HTML string |
| `live_chat_ui.html:375` | `<div id="nexusModel">` static placeholder | static HTML string |

When these disagree, the user sees something like: "I'm using megatron, but the status bar says starscream." Both are technically true (the chat is using megatron, the bridge defaults to starscream), but the user can't tell that from a single screen.

## Diagnosis recipe

1. Find every reference to a model name in Vision's source. Grep for the candidate names (`grep -rn 'megatron\|starscream\|current_model\|DEFAULT_MODEL' C:/Users/KING/Projects/vision/`) excluding `node_modules` and `__pycache__`.
2. For each match, note the variable name, file, and what it controls. Build the table above for your copy of the repo.
3. Pick the model that **actually exists in NEXUS** as the canonical default. Validate:
   ```bash
   curl -s -X POST http://127.0.0.1:8650/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"<candidate>","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
   ```
   Non-empty `choices[0].message.content` proves the model is reachable through NEXUS.
4. Make every default env-overridable so a single env-var change can point Vision at a different model without code edits:
   ```python
   # live_chat_app.py
   current_model = os.getenv("VISION_DEFAULT_MODEL", "megatron-fixed:latest")

   # nexus_bridge.py
   DEFAULT_MODEL = os.getenv("NEXUS_CORE_MODEL", "megatron-fixed:latest")
   ```
5. Update the static strings in `live_chat_ui.html` to match the new default. Restart Vision and reload the UI in the browser.

## Verified example (2026-08-28 on THRONE)

Before fix:
- `live_chat_app.py:416` → `current_model = "megatron-fixed:latest"`
- `nexus_bridge.py:24` → `DEFAULT_MODEL = ..., "starscream"` (model doesn't exist in NEXUS!)
- `live_chat_ui.html:321` → `"Model: starscream."`
- `live_chat_ui.html:375` → `<div id="nexusModel">starscream</div>`

User reported "Vision says megatron, dashboard says starscream." Truth: chat was using megatron-fixed (correct), but the NEXUS bridge default and both static UI labels pointed at starscream. The NEXUS bridge path would 404 if it ever fell through to a starscream request.

After fix:
- `live_chat_app.py:416` → `current_model = os.getenv("VISION_DEFAULT_MODEL", "megatron-fixed:latest")`
- `nexus_bridge.py:24` → `DEFAULT_MODEL = os.getenv("NEXUS_CORE_MODEL", "megatron-fixed:latest")`
- `live_chat_ui.html:321` → `"Model: megatron-fixed:latest. NEXUS CORE connected (327 notes)."`
- `live_chat_ui.html:375` → `<div id="nexusModel">megatron-fixed:latest</div>`

End-to-end test:
```bash
curl -s -X POST http://127.0.0.1:8650/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"megatron-fixed:latest","messages":[{"role":"user","content":"say hi in 3 words"}],"max_tokens":20}'
# → "Hi there! How can I assist you today?" (model used: megatron-fixed:latest)
```

## Why this happens (root cause)

When you migrate Vision across hosts or upgrade Ollama, the active model changes but the static strings in the HTML don't get re-rendered. The HTML is hand-edited once and forgotten; the Python defaults drift naturally as you swap models. The fix isn't to never hard-code — it's to **centralize the default in a single env-var** and have every other reference fall back to a consistent value. The static HTML strings are the only ones that need manual update; everything else reads from `os.getenv` at startup.

## Anti-pattern: editing static HTML to match a runtime value

It's tempting to put `{{ model_name }}` in `live_chat_ui.html` and have the server render the page. That works for SSR but Vision is a single-page FastAPI app where the static HTML is served once and the JS updates the DOM. The right pattern is:
1. Default lives in Python (env-var with sensible fallback).
2. Static HTML shows the fallback (so the initial render before JS fires is correct).
3. JS calls `/api/models` (or whatever the current-model endpoint is) and updates the static placeholder.

The pattern fails open: if the JS is broken or slow, the user still sees the right name (just the fallback). If the JS is fast, the user sees the real name. Either way, the static string and the runtime value agree because the runtime falls back to the same constant.
