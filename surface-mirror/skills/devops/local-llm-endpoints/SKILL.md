---
name: local-llm-endpoints
description: Wiring Ollama, CyberStrike, Megatron or local models.
---

# Local LLM endpoints — verified inventory

## Ollama (verified 2026-09-25 via curl http://localhost:11434/api/tags)

Installed models include:

- `qikfox/megatron:latest`, `megatron:latest`, `megatron-fixed:latest`, `megatron-fixed-32k:latest`
- `megatron-agent:latest`, `megatron-research:latest` (per-task variants, see `mlops/ollama-modelfile-authoring` recipes)
- `qikfox/starscream:latest`, `starscream:latest`, `starscream-64k:latest`
- `starscream-vision:latest` (gemma4 chat template, 65K ctx)
- `qikfox/CYBA:latest`, `CYBA:latest`, `CYBA-64k:latest`
- `nous-hermes2:34b`, `nous-hermes2:10.7b`
- `medgemma:27b`, `muse-glimmer:30b`
- `MobiusDevelopment/Qwen3.8-27B-MTP-Q4_K_M_GGUF-Uncensored:latest`
- `hf.co/0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF:Q4_K_M`
- `hf.co/mradermacher/HERETICSEEK-7B-Ditill-GGUF:Q4_K_M`
- `hf.co/huihui-ai/Huihui-CyberStrike-OffSec-35B-abliterated-GGUF:Q6_K` (CyberStrike)
- `jeffgreen311/eve-qwen3.5-4b-S0LF0RG3:latest`
- `R4C5R/minicpm5-1b-fable5-heretic:latest`
- `Agen/gemma-4-26B-A4B-it-uncensored-heretic:latest`
- `defyma85/gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M_gguf:latest`
- `ornith-1.5:9b`, `ornith:9b`
- `nomic-embed-text:latest`, `mxbai-embed-large:latest` (embeddings, ~274 MB / 670 MB)

Per-task variant recipes and the swap-probe script live in `throne-llm-router`.

## Standing rules

- Context window must be ≥ 64K for any model the user interacts with. Starscream/CYBA/Megatron families are 64K.
- Megatron is the user's preferred model for CyberStrike-compatible local work ("Megatron is based off CyberStrike").
- Local-first: prefer Ollama over Anthropic API unless user asks for cloud.

## Endpoints

- Ollama OpenAI-compat: `http://localhost:11434/v1` (chat completions, embeddings, models)
- Ollama native API: `http://localhost:11434/api/chat`, `/api/tags`, `/api/pull`
- OpenClaw Control: `http://localhost:18789/` (web UI "OpenClaw Control"; serves SPA on every path — model listing via Ollama at :11434, not :18789 itself)
- Cradle dev server: `http://localhost:8081/` (:8081 is Cradle's claim — never assign it to another service; never move back to :8080)
- Heretik demand proxy: `http://localhost:8080/` — a stdlib Python proxy owns the contract port and lazily spawns llama-server on a non-conflicting backend port at first call (~10s cold start, ~60 tok/s warm), killing it after an idle timeout to free ~9GB RAM. Status probe: `GET :8080/__demand_status`. Clients (MCP, launchers) keep using :8080 unchanged; never point anything directly at the backend port.

## CyberStrike CLI

- Windows PowerShell CLI, version 1.1.16.
- `/connect anthropic` errors "No Anthropic subscription token available" when run without a token — it expects a real Anthropic API key.
- User confirmed it supports custom/local endpoints.
- Wire recipe: OpenAI-compatible mode pointing at `http://localhost:11434/v1` with model name `qikfox/megatron:latest`.

## Cradle (the RPG)

- Workspace: `C:\Users\KING\projects\Cradle` (NOT `/workspace` — that Linux path does not exist on Windows).
- `startup.sh` rewritten to use `$(pwd)` instead of `/workspace` so it works on Windows.
- Project is an RPG: child AI character wakes in a mini-world and learns. Caretaker (user) talks via `TalkDock`. The model becomes the child's "mind" via `SettingsPanel` (kind: `grok` | `custom`; for local Ollama set `baseUrl` + `model`).
- World expanded 2026-09-25: 8 zones (`cottage`, `garden`, `pond`, `forest`, `meadow`, `brook`, `hill`, `old shack`), new tiles (`sand`, `fence`, `bridge`, `hill`), new props (`lantern`, `flower`, `mushroom`, `acorn`, `feather`, `honey`, `stone`, `key`, `chest`, `bridge`). Zone name surfaced in HUD via `HudSnap.zone`.
- Desktop shortcut: `C:\Users\KING\Desktop\Cradle.lnk` rebuilt via `C:\Users\KING\projects\Cradle\fix_shortcut.ps1` → `cmd.exe "/c cd C:\Users\KING\projects\Cradle && npm run dev"`.
- Build verified: `npm run build` ~880ms. Entry files present: `src/router.tsx`, `src/routes/__root.tsx`, `src/routes/index.tsx`, `src/styles.css`. Build pushed to `dqikfox/CRADLE2` @ `3761697`.
- User reacted ❤️ to `ornith-1.5:9b` model pull — positive signal on the workflow.

## Lessons / pitfalls

- The `terminal` tool sometimes strips variable assignments (`$sc = ...`) from inline PowerShell commands. Workaround: write the logic to a `.ps1` file and execute it with `powershell -ExecutionPolicy Bypass -File "C:\path\to\script.ps1"`.
- Do not assume port `:8080` is free; the Heretik demand proxy owns it. The proxy's backend spawns on an unclaimed port (:8082 — NOT :8081, which is Cradle's). Probe `netstat -ano` before binding any service.
- Do not assume a model listed in memory still exists — probe `:11434/api/tags` first before wiring anything.
- `megatron-agent` is the default operator model (35.5B Q4_K_M, 32K ctx). `starscream-64k` is the active chat/vision model (gemma4 25.8B Q4_K_M, 65K ctx). One model resident at a time; evict with `keep_alive:0` before swapping — see `throne-llm-router`.
- **CPU-offload trap**: a 262K `num_ctx` on starscream-64k causes `/api/ps` to report `size_vram=3.9 GB` out of `size=17.5 GB`. Generation stalls indefinitely. Always set `num_ctx ≤ 65536` at request time for starscream-64k on RTX 3090.
- **Benchmark both sides before redirecting an inference endpoint to a mesh node.** GPU class dominates: a 4GB laptop GPU spills a 7B Q4 model to CPU (~3 tok/s) while the local 24GB card sustains 60-90 tok/s — a 30x regression invisible in a "remote model exists" check. Remote mesh nodes are for batch, embedding, and edge work, never latency-critical tool paths.
- **RAM-tight flagship host: demand-proxy resident servers instead of offloading.** Pattern (template `templates/demand_proxy.py`): a stdlib Python proxy owns the original contract port, lazily spawns the backend on first request, and kills it after an idle timeout — endpoint behavior unchanged for clients, gigabytes freed when idle. Cold start lands on the first call only (~10s for a 7B Q4).
