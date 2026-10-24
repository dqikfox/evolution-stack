# OpenClaw + Ollama Configuration (Windows — 2026-08-21)

## Full annotated `openclaw.json` for RTX 3090 / 24GB VRAM

### Model entry template
```json
{
  "id": "megatron-fixed:latest",
  "name": "megatron-fixed:latest",
  "contextWindow": 262144,
  "maxTokens": 65536,
  "input": ["text"],
  "reasoning": true,
  "compat": {
    "supportsTools": true,
    "supportsUsageInStreaming": true
  },
  "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
}
```

### Key decisions from 2026-08-21 session
- **Default model:** switched from `Agen/gemma-4-26B-A4B-it-uncensored-heretic` → `ollama/megatron-fixed:latest`
- **maxTokens:** bumped from 8192 → 65536 (matches Ollama `num_ctx 65536`)
- **Web search:** disabled (`provider: "ollama"` → `"none"`) — Ollama is not a search engine
- **Skills enabled:** `1password`, `github`, `session-logs`, `summarize`
- **Gateway:** bound to `loopback:18789`, token auth

### Model lineup (sorted by capability, not alphabet)
| Model | VRAM | Context | Use case |
|-------|------|---------|----------|
| `megatron-fixed:latest` | 21GB | 64K | Primary agent — Qwen3.5 MoE 35.5B Q4_K_M |
| `starscream:latest` | 17GB | 8K | Secondary — Gemma-4-26B |
| `Agen/gemma-4-26B-A4B-it-uncensored-heretic:latest` | 17GB | 8K | Uncensored variant |

### VRAM math
- RTX 3090: 24GB total, ~22.4GB usable
- megatron-fixed Q4_K_M: ~21.7GB loaded
- starscream Q4_K_M: ~17GB loaded
- Running both simultaneously: ~38.7GB → NOT POSSIBLE on 24GB
- Solution: `OLLAMA_MAX_LOADED_MODELS=1` prevents double-load

### Health check
```bash
curl -s http://localhost:18789/health
# → {"ok":true,"status":"live"}
```

### Common misconfigurations found
1. **`web.search.provider: "ollama"`** — silently broken. Ollama is an inference engine, not a search engine.
2. **`tools.profile: "coding"`** — may mismatch agent role. Check.
3. **Single model in registry** — add all viable models so the agent can switch.
4. **`maxTokens` exceeding actual `num_ctx`** — Ollama will reject or truncate.
