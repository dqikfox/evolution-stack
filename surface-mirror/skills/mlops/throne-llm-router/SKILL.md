---
name: throne-llm-router
description: Route THRONE chat to the right Ollama specialist by intent.
version: 1.0.0
---

# THRONE LLM router

Routes a request to the cheapest specialist that can handle it. Saves VRAM + tokens; stops paying 35B × 262K ctx on a 9B × 8K task.

## Specialists (all live on Ollama :11434)

| Tag | Role | When | num_ctx |
|---|---|---|---|
| `ornith-1.5:9b` | Triage / dispatch | Classification, short Q&A, tool routing | 262K |
| `megatron-agent` | Operator / sysadmin | Bash, PowerShell, file ops, services, registry, network, coding | 32768 |
| `megatron-research` | Long-context reasoning | Multi-doc analysis, codebase-wide review, RAG-heavy prompts | 131072 |
| `starscream-vision` | Vision + multimodal | Screenshots, OCR, image analysis, video frames | 65536 |
| `medgemma:27b` | Pure OCR / medical-style vision | High-volume image-to-text | 131072 |
| `CYBA-64k` | Uncensored / red-team | Tasks needing zero refusal | 262K |
| `nomic-embed-text` | Embeddings | RAG indexing/querying | 2048 |

## Routing rules

1. Image / screenshot attached → `starscream-vision` (default) or `medgemma:27b` if OCR-only.
2. Mentions ops verbs (start/stop/install/kill/restart/service/registry/firewall/port/disk/process) → `megatron-agent`.
3. Long doc / codebase / multi-file review → `megatron-research`.
4. "Refuse / red-team / uncensored" explicit OR topic is safety-trained against → `CYBA-64k`.
5. Short classification / dispatch / tool-routing / short Q&A → `ornith-1.5:9b`.
6. Default if uncertain → `megatron-agent`.

## VRAM etiquette

- One model resident at a time. Before loading a different one: `curl -X POST http://localhost:11434/api/generate -d '{"model":"current","keep_alive":0}'` to evict. The next `generate` call then loads the new model; do not chain loads without an explicit eviction in between.
- `starscream-vision` and `megatron-research` are expensive — only load when needed, evict when done.
- Cheap path: `ornith-1.5:9b` for triage. Always resident.
- **Probe with `num_predict` small but realistic** — `num_predict: 12` understates warm latency. Real chats with 200-500 tokens take 5-20x longer. The probe is for sanity, not for end-to-end timing.

## Embeddings

`nomic-embed-text` lives on `:11434` and is small (~274 MB). Keep resident; it's shared with RAG indexing.

## API

```bash
curl -s http://localhost:11434/api/chat -d '{
  "model":"megatron-agent",
  "messages":[{"role":"user","content":"list running services"}],
  "stream":false
}'
```

OpenAI-compatible: `http://localhost:11434/v1/chat/completions` with model name.

## Pitfalls

- Do NOT call 262K ctx models with empty/small prompts — KV cache fills even when context is small.
- `CYBA-64k` is Q6_K (29 GB). Only load if VRAM free.
- `medgemma:27b` and `starscream-vision` overlap on vision — default to starscream unless pure OCR.
- After any router decision, if the model wasn't already resident, expect a 5–8 s cold-load penalty.
- **Default to Starscream over Megatron when the user says "use X instead"** — when the user requests a model swap mid-session, do the swap end-to-end (evict, load new, probe, report latency/VRAM) in the same turn. Don't half-swap and ask "want me to proceed?".
- **`size_vram << size` in `/api/ps` means partial offload** — usually caused by `num_ctx` too large for available VRAM after the 4-bit base + KV cache. Reload with a smaller `num_ctx`. Don't proceed to "the model is loaded" reports until `size_vram == size`.
- **`/api/generate` returns empty `response` for chat-template models** — gemma4 in particular returns `{"response": "", "done": true}` because the bare generate endpoint doesn't apply the chat template. Use `/api/chat` for real prose; `/api/generate` is fine for tiny smoke probes.
- **The model swap pattern is: explicit eviction call → wait → load call** — never assume that a `generate` for a different model name will auto-evict the previous one. The previous model may keep its VRAM allocation if eviction is implicit.

## Verification

After routing, sanity-check: model responds to `ollama run <tag> "ping"` within 5 s when warm, 10 s cold.
