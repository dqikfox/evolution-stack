# Ollama Environment Variables — Defaults & Best Practices

## Actual defaults (per Ollama docs)

| Variable | Default | What it does |
|----------|---------|--------------|
| `OLLAMA_NUM_PARALLEL` | `1` | Max concurrent requests per loaded model. Each parallel slot consumes its own KV-cache VRAM. |
| `OLLAMA_MAX_LOADED_MODELS` | `3 × GPU count` | How many distinct models can sit in VRAM concurrently. For a single-GPU RTX 3090, default is 3. For CPU-only, default is 3. |
| `OLLAMA_KEEP_ALIVE` | `5m` | How long a model stays loaded in VRAM after the last request. |
| `OLLAMA_FLASH_ATTENTION` | `0` (off) | Enables flash attention for ~30-50% faster prompt processing on Ampere+ GPUs. |
| `OLLAMA_CONTEXT_LENGTH` | `2048` | Default context window if the model's Modelfile doesn't specify `PARAMETER num_ctx`. Not auto-derived from the model's native context — must be set explicitly. |

## Footgun — DO NOT set `OLLAMA_LLM_LIBRARY=cpu_avx2`

`OLLAMA_LLM_LIBRARY` selects which llama.cpp library variant Ollama loads. Values like `cpu_avx2`, `cpu_avx`, `cpu` force CPU-only inference — the GPU sits idle and every token takes hundreds of milliseconds instead of tens. The "fix" looks plausible (you saw `avx2` in the system info, set it to use AVX2) but it disables CUDA entirely. There is no recovery without removing the env var and restarting Ollama; the symptoms look like the model is broken or VRAM is full.

If you see `llama-server` running but inference is suddenly 10–50× slower and the GPU shows 0% util, check `HKCU\Environment` and `HKLM\SYSTEM\CurrentControlSet\Services\Ollama` (if installed as a service) for `OLLAMA_LLM_LIBRARY`. Leave it unset unless Ollama's own diagnostic tells you to override it.

## These are TUNING KNOBS, not required settings

Ollama works perfectly without any of them. The defaults are sensible for single-user local use. Only increase when you have a genuine need:

- **NUM_PARALLEL > 1**: Only useful when you make multiple concurrent API calls to the same model. Each parallel slot needs its own KV-cache VRAM.
- **MAX_LOADED_MODELS > 1**: Only useful when you frequently switch between models and want them all hot in VRAM.

## Practical limits on THRONE (24GB RTX 3090)

With megatron-fixed (35.5B Q4_K_M, ~20GB VRAM) loaded:
- NUM_PARALLEL=4 leaves ~4GB for KV-cache across 4 slots (~1GB each) — tight but workable for short contexts
- MAX_LOADED_MODELS=2 with two 35B models would need ~40GB — exceeds 24GB. Only practical with one 35B + one smaller model (e.g., starscream 25.8B Q4_K_M ~17GB = 37GB total — still exceeds)
- Realistic: MAX_LOADED_MODELS=1 for 35B models, or 2 for smaller models only

## Modelfile overrides

`PARAMETER num_ctx` in a Modelfile OVERRIDES `OLLAMA_CONTEXT_LENGTH`. If a model was created with `PARAMETER num_ctx 8192`, setting `OLLAMA_CONTEXT_LENGTH=65536` does nothing for that model. Check with:
```bash
curl -s http://localhost:11434/api/show -d '{"name":"<model>:latest"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(l.strip()) for l in d.get('parameters','').split(chr(10)) if 'num_ctx' in l]"
```
If this prints `num_ctx 8192`, the Modelfile parameter is blocking your env var. Fix by rebuilding the model (see `ollama-modelfile-authoring` skill).
