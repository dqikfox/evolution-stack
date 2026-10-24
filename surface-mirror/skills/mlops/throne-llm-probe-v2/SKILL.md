---
name: throne-llm-probe
description: Smoke-test THRONE's active Ollama model with a timed probe.
version: 1.0.0
---

# THRONE LLM probe

Quick sanity check: confirms the active Ollama model is resident, responsive, and within VRAM budget.

## When to use

- After any model swap, env-var change, or Ollama restart.
- When `/api/ps` returns empty or stale.
- Before claiming "model is ready" in a release/announcement.

## Procedure

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File "C:/Users/KING/AppData/Local/hermes/scripts/probe_starscream.ps1"
```

Adjust the script's `model` field to point at the specialist you want to probe:
- `starscream-64k:latest` — vision + long-context default
- `megatron-agent:latest` — sysadmin/coding
- `ornith-1.5:9b` — cheap triage

## What the script returns

- HTTP status + wall-clock latency
- Token count + total generation duration (seconds)
- `/api/ps` snapshot — model, size_vram, ctx, expires_at
- VRAM used / free / GPU util

## Healthy state — what to look for

| Signal | Healthy | Bad |
|---|---|---|
| HTTP | 200 | non-200 or timeout |
| Wall-clock (cold) | < 30 s for first token | > 60 s |
| Wall-clock (warm) | < 5 s first token | > 15 s |
| size_vram == size | model fully on GPU | model partially offloaded |
| VRAM free after load | ≥ 2 GB | < 500 MB |
| /api/ps expires_at | > now + 1 h | < now + 1 min |

## If unhealthy

1. Cold start slow → check VRAM pressure, mxbai/nomic pulls still running.
2. `size_vram << size` → num_ctx too large, GPU ran out, layers offloaded to CPU. Reduce `num_ctx`.
3. Timeout → model crashed during load; check `ollama logs` (Windows event log: Application → Ollama).
4. Empty /api/ps → model was unloaded; re-trigger with explicit `keep_alive`.
5. **`response` field empty but `done: true`** → you hit `/api/generate` against a chat-template model (gemma4, qwen, llama 3). Switch to `/api/chat` for real prose; `/api/generate` only works for base models or tiny smoke probes.

## Cold vs warm latency

| Stage | Expected wall-clock | Why |
|---|---|---|
| Cold first token | 8-30 s | Model + KV cache + weights load from disk |
| Warm first token | < 5 s | KV cache retained, weights resident |
| Cold `num_predict: 12` | 10-15 s | Same as cold first-token |
| Warm `num_predict: 12` | < 1 s | Already loaded, fast |
| Real chat (300 tokens, warm) | 5-20 s | Generation cost dominates |

The probe script measures `num_predict: 12` — multiply by 5-20x to estimate real-chat latency.

## Pitfalls

- The probe uses `num_predict = 12` so the wall-clock reflects a small chunk. Real chats with 200–500 tokens will take 5–20× longer.
- gemma4 returns a near-empty `response` field on the bare `/api/generate` endpoint because the chat template wraps user prompts. Use `/api/chat` for real prose.
- If you swap models while another is resident, the eviction is implicit on the next generate. Explicit eviction: `curl -X POST http://localhost:11434/api/generate -d '{"model":"<old>","keep_alive":0}'`.
