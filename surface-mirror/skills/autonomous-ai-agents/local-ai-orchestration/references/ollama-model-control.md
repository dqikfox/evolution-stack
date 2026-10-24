# Ollama Model Control — load / unload / ps

Ollama has no explicit "load model" or "unload model" endpoint. The lever is `keep_alive`, set on every `generate` call. Three patterns every local AI dashboard needs.

## The keep_alive contract

| Value | Behavior |
|---|---|
| `0` | Unload immediately after the request completes |
| `"5m"`, `"30m"`, `"2h"` | Keep the model loaded for that duration after the last request |
| (omit) | Use Ollama's `OLLAMA_KEEP_ALIVE` env var, default `5m` |
| `-1` | Never unload (until process exits) |

## Force-load a model into VRAM

There's no dedicated "load" endpoint. The standard trick: issue a `generate` with a minimal prompt. If the model isn't loaded, Ollama loads it; if it is, the call is fast.

```python
import httpx
async def load_model(model: str, keep_alive: str = "10m"):
    async with httpx.AsyncClient(timeout=120) as cli:
        r = await cli.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": "hi",
                "stream": False,
                "keep_alive": keep_alive,
            },
        )
    return r.status_code == 200
```

The `200 OK` response proves the model loaded. Use a minimal prompt ("hi") to keep the request cheap — you only need to trigger the load, not generate real output.

## Unload a model from VRAM

Same endpoint, different `keep_alive`:

```python
async def unload_model(model: str):
    async with httpx.AsyncClient(timeout=60) as cli:
        await cli.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
        )
    return True
```

The empty prompt makes the call a no-op except for the unload. `keep_alive: 0` tells Ollama to drop the model from VRAM the moment the request completes.

## List currently loaded models: /api/ps

Returns the running models with their VRAM usage, context length, and expiry:

```json
{
  "models": [
    {
      "name": "megatron-fixed:latest",
      "model": "megatron-fixed:latest",
      "size": 21904742153,
      "size_vram": 21904742153,
      "details": {
        "format": "gguf",
        "family": "qwen35moe",
        "parameter_size": "35.5B",
        "quantization_level": "Q4_K_M"
      },
      "expires_at": "2026-08-28T09:16:57.820173+10:00",
      "context_length": 65536
    }
  ]
}
```

`expires_at` is the wall-clock time when Ollama will unload the model (based on `keep_alive`). To render "5m 30s remaining" in the dashboard, parse this and subtract from `time.time()`.

## Streaming pulls: backpressure-friendly NDJSON

The `/api/pull` endpoint streams NDJSON progress for each layer downloaded. To consume in an async backend:

```python
async def stream_pull(model: str):
    async with httpx.AsyncClient(timeout=600) as cli:
        async with cli.stream(
            "POST", f"{OLLAMA_BASE}/api/pull",
            json={"name": model, "stream": True},
        ) as r:
            async for line in r.aiter_lines():
                if line:
                    yield (line + "\n").encode("utf-8")
```

`aiter_lines()` is the right primitive — it yields complete lines (split on `\n`) without buffering entire chunks. Return this as a `StreamingResponse(media_type="application/x-ndjson")` so the dashboard can render progress line-by-line as the pull happens.

## Production dashboard pattern

Three named endpoints, each ~10 lines of code, that wrap the primitives above:

```
POST /api/ollama/load    {model, keep_alive?}    → {ok, model, keep_alive}
POST /api/ollama/unload  {model}                  → {ok, model, unloaded: true}
GET  /api/ollama/ps                              → {ok, loaded: [...], count: N}
```

The dashboard renders loaded models with a green pulse + "● LIVE" tag, and a "■ UNLOAD" button per loaded model. Models in the catalog but not loaded get a "▶ LOAD" button. Each button calls one of the three endpoints.

## Pitfall: don't trust `/api/ps` after a load

Ollama's `/api/ps` is eventually consistent — a `load` that just returned 200 may not show up in `/api/ps` for 100-500ms. If the dashboard polls `/api/ps` immediately after a load click, it can show "no models loaded" briefly. The fix: after a load, mark the card as "loading" locally and refresh the loaded list after 1-2 seconds, not immediately.

## Pitfall: empty `prompt` with `keep_alive: 0` returns 200 immediately

`{"model": "...", "prompt": "", "stream": false, "keep_alive": 0}` is the cheapest possible unload call. The response has `response: ""` and `done: true`. Don't read the response body to verify the unload — it doesn't tell you whether the model was actually in VRAM to begin with. Use `/api/ps` after the call to confirm it's gone.
