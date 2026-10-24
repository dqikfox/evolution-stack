# Ollama RAG Troubleshooting

## Symptom: empty `content` field, HTTP 200

The most common RAG bug: Ollama returns `{"message": {"content": "", "role": "assistant"}, "done": true}` with HTTP 200, but the answer is blank.

Causes, in order of likelihood:

### 1. Wrong endpoint (`/api/generate` vs `/api/chat`)

Models with chat templates (Qwen, Gemma, Llama 3, Mistral) expect multi-turn messages and a system prompt. `/api/generate` ignores the messages array and applies a generic prompt template, which can produce empty output for some inputs.

**Fix:** Always use `/api/chat`:

```python
resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
    "model": model,
    "messages": messages,  # [{"role": "system", ...}, {"role": "user", ...}]
    "stream": False,
})
answer = resp.json()["message"]["content"]
```

### 2. VRAM is full

`nvidia-smi` shows >95% memory used. Ollama loads the model but cannot allocate activation memory for the context, and returns empty.

**Fix:** Switch to a smaller model or unload other models:

```bash
# List loaded models and their VRAM
ollama ps

# Unload a model
curl -X POST http://localhost:11434/api/generate -d '{"model":"<name>","keep_alive":0}'
```

### 3. Model is still loading

The first request after `ollama pull` or after a long idle period triggers model load, which can take 5-30 seconds. The request times out before the model is ready.

**Fix:** Increase timeout and warm up the model:

```python
resp = requests.post(url, json=payload, timeout=120)  # not 30
```

### 4. Context window too small for prompt

If your RAG context + system prompt + user question exceeds `num_ctx` (default 2048), the response may be empty or truncated. The default Ollama context is 2K tokens, which is too small for RAG with even 3-4 retrieved chunks.

**Fix:** Set `num_ctx` in the options:

```python
resp = requests.post(url, json={
    "model": model,
    "messages": messages,
    "options": {"num_ctx": 8192},
})
```

For Qwen3.5, 8192 is the recommended setting. For larger contexts, also set `num_batch` to control VRAM.

### 5. Modelfile has a broken template

Custom Modelfiles with a `TEMPLATE` field that doesn't match the model's tokenizer will silently produce empty output.

**Fix:** Inspect the model's template:

```bash
ollama show <model> --modelfile
```

If `TEMPLATE` is missing or wrong, re-pull the upstream model instead of using the custom one.

## Symptom: `Ollama: HTTPConnectionPool ... Read timed out`

The first request after server start takes 5-30s to load the model. The Python `requests` default timeout is None (forever), but if you've set `timeout=5` or similar, you'll see this.

**Fix:** Use a longer timeout, or pre-warm the model on startup:

```python
# Pre-warm: cheap request that forces model load
requests.post(f"{OLLAMA_URL}/api/chat", json={
    "model": DEFAULT_MODEL,
    "messages": [{"role": "user", "content": "hi"}],
}, timeout=120)
```

## Symptom: streaming connection drops mid-response

You're using `stream=True` and the connection closes after 3-4 chunks. Usually a reverse proxy or a Flask/nginx timeout in front of Ollama.

**Fix:** Either bypass the proxy, or set `keep_alive` in the Ollama request:

```python
resp = requests.post(url, json={...}, stream=True, timeout=None)
# Read chunks manually
for line in resp.iter_lines():
    if line:
        chunk = json.loads(line)
        ...
```

## Verifying a healthy RAG setup

```bash
# 1. Is Ollama running?
curl http://127.0.0.1:11434/api/tags

# 2. Is the default model loaded?
ollama ps

# 3. Does a minimal chat work?
curl -X POST http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"<your-model>","messages":[{"role":"user","content":"hi"}],"stream":false}'

# 4. Does your RAG wrapper work?
curl "http://127.0.0.1:8650/api/ask?q=hello"
```

If step 3 returns empty content, the problem is with Ollama/model, not your wrapper. If step 4 returns empty but step 3 works, the problem is in your RAG context construction (empty retrieval, prompt template, etc.).

## See also

- `references/embedding-provider-switching.md` — ChromaDB dim mismatches and silent reindex failures
- `references/unc-path-issues.md` — Q: drive venv and `pip install` problems
