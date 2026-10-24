---
type: skill
name: local-knowledge-engine
description: Build local RAG systems with Ollama, ChromaDB, SQLite.
---

# Local Knowledge Engine

Use when building or maintaining a local-first knowledge management system — a persistent, queryable brain for local LLMs that syncs with Obsidian vaults, indexes documents, and serves answers via API.

## When to use

- Building a local RAG pipeline (Ollama + vector DB + FTS5)
- Syncing Obsidian vault notes into a searchable knowledge base
- Creating a FastAPI server that answers questions from vault context
- Debugging empty LLM responses, embedding dimension mismatches, or missing note bodies
- Adding voice/TTS interfaces to local knowledge queries
- Building offline-capable agent memory systems

## When NOT to use

- Cloud-based vector stores (Pinecone, Weaviate) — use provider-specific skills
- Raw llama.cpp without Ollama — see `llama-cpp` skill
- Hermes Agent plugin issues — see `hermes-obsidian-integration` skill

## Architecture Overview

```
Obsidian Vault (markdown notes)
    ↓ sync_vault.py
SQLite + FTS5 (canonical notes)
    ↓ index_note()
ChromaDB (vector embeddings)
    ↓ hybrid_search()
FastAPI Server (RAG endpoint)
    ↓ POST /api/ask
Ollama (local LLM inference)
```

## Core Components

### 1. Database Layer (SQLite + FTS5)

```python
import sqlite3

conn = sqlite3.connect("nexus.db")
conn.execute("CREATE VIRTUAL TABLE notes_fts USING fts5(slug, title, body)")
conn.execute("""
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        slug TEXT UNIQUE,
        title TEXT,
        body TEXT,
        tags TEXT,
        source TEXT,
        created_at TEXT,
        updated_at TEXT
    )
""")
```

**Pitfall:** `list_notes()` often omits `body` for performance. If building graph links or indexing vectors, query `SELECT ... body FROM notes` directly.

**Pitfall:** `get_note()` takes a `slug` string, not a numeric `id`.

### 2. Vector Index (ChromaDB)

```python
import chromadb
client = chromadb.PersistentClient(path="./chroma")
collection = client.get_or_create_collection("nexus")

# Embed and upsert
collection.upsert(
    ids=[note["slug"]],
    embeddings=[embedding],
    documents=[note["body"]],
    metadatas=[{"title": note["title"], "source": note["source"]}]
)
```

**Pitfall — Dimension mismatch:** Changing embedding provider (e.g., Ollama nomic-embed-text → chroma-default) changes vector dimensions. Old collections retain the old dimension. Always clear ChromaDB before switching providers:

```python
import shutil
shutil.rmtree(CHROMA_DIR)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
```

### 3. Similar-Notes Lookup (Chroma `query` + SQLite hydration)

Find notes semantically related to a given note by querying Chroma with the note's body and hydrating results from SQLite:

```python
from core.db import get_note, get_note_by_id
from core.search import get_collection

def find_similar(slug: str, limit: int = 8):
    note = get_note(slug)
    if not note:
        return []
    coll = get_collection()
    query = (note.get("title", "") + " " + (note.get("body") or "")[:1000]).strip()
    if not query or coll.count() == 0:
        return []
    results = coll.query(query_texts=[query], n_results=limit + 2)
    ids = results.get("ids", [[]])[0]
    dists = results.get("distances", [[]])[0]
    out = []
    for nid, dist in zip(ids, dists):
        if nid == note["id"] or nid == slug:
            continue
        # Chroma stores docs by the note's id, not its slug — see Pitfall below
        target = get_note(nid) or get_note_by_id(nid)
        if target and target["slug"] != slug:
            out.append({
                "slug": target["slug"],
                "title": target["title"],
                "source": target.get("source"),
                "score": max(0, 1 - dist) if dist is not None else 0,
            })
        if len(out) >= limit:
            break
    return out
```

**Pitfall — Chroma id is the SQLite `id`, not the `slug`.** When the indexer uses `note["id"]` (numeric primary key) and the lookup tries `get_note(nid)` first, it returns `None` because `get_note` queries by `slug`. Always fall back to `get_note_by_id(nid)`. This is the most common bug in similar-note implementations.

**Pitfall — Cosine distance, not similarity.** Chroma's `distances` field is *distance* (0 = identical, 2 = opposite). Convert with `score = 1 - dist` before exposing to users.

### 3a. OpenAI-Compatible Bridge

Expose the brain as a drop-in OpenAI endpoint so any client (OpenClaw, LM Studio, Continue.dev, Cursor, Aider) can use it as a backend with zero custom code:

```python
@app.post("/v1/chat/completions")
async def openai_chat(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    model = data.get("model", DEFAULT_MODEL)
    use_rag = data.get("nexus_rag", True)  # inject brain context by default

    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if use_rag and user_msg:
        context = build_context(user_msg)  # hybrid_search → top_k chunks
        messages = [{"role": "system", "content": f"Use the context to answer:\n{context}"}] + messages

    # Delegate to Ollama /api/chat (NOT /api/generate — see Pitfall below)
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
        "model": model, "messages": messages, "stream": False,
    })
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": resp.json()["message"]["content"]},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

@app.get("/v1/models")
async def list_models():
    r = requests.get(f"{OLLAMA_URL}/api/tags")
    return {
        "object": "list",
        "data": [{"id": m["name"], "object": "model"} for m in r.json().get("models", [])],
    }
```

**Pitfall — Use `/api/chat`, not `/api/generate`.** Models with chat templates (Qwen, Gemma, Llama 3) return empty content or apply the wrong prompt format if you hit `/api/generate`. The chat endpoint applies the model's template correctly. If you see `{"response": "", "done": true}` with HTTP 200, you hit the wrong endpoint.

**Pitfall — CORS for browser clients.** OpenClaw is a browser SPA, so enable CORS on the v1 routes:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "app://*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Client configuration:** In OpenClaw's settings, point the API base URL at `http://127.0.0.1:8650/v1` (instead of Ollama's default `http://127.0.0.1:11434/v1`). The client now gets RAG-augmented answers and episodic memory recording for free.

### 3. Hybrid Search (BM25 + Vector)

```python
def hybrid_search(query: str, limit: int = 20):
    # FTS5 keyword results
    keyword_results = keyword_search(query, limit=limit)
    
    # Vector similarity results
    vector_results = vector_search(query, limit=limit)
    
    # Merge and deduplicate with score weighting
    merged = {}
    for r in keyword_results:
        merged[r["slug"]] = {"score": r["score"] * 1.5, **r}
    for r in vector_results:
        if r["slug"] in merged:
            merged[r["slug"]]["score"] += r["score"]
        else:
            merged[r["slug"]] = {"score": r["score"], **r}
    
    return sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:limit]
```

### 4. RAG Pipeline

**Prefer `/api/chat` over `/api/generate`** for models with chat templates (Gemma, Qwen, Llama 3):

```python
messages = [
    {"role": "system", "content": "You are a local knowledge assistant."},
    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
]
resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
    "model": model,
    "messages": messages,
    "stream": False
})
answer = resp.json()["message"]["content"]
```

**Pitfall — Empty responses with full VRAM:** Ollama returns `{"response": "", "done": true}` when the model loads but cannot allocate activation memory. Check `nvidia-smi` — if VRAM is >95%, switch to a smaller model or free GPU memory.

### 5. Vault Sync

```python
def sync_vault(vault_path: Path):
    for md_file in vault_path.rglob("*.md"):
        body = md_file.read_text()
        slug = slugify(md_file.stem)
        note = create_note(slug=slug, title=md_file.stem, body=body, source="obsidian")
        index_note(note)
```

**Pitfall:** Slug collisions. Two notes with the same title in different folders will collide. Include folder path in slug: `folder--filename`.

**Pitfall:** Interactive prompts in sync scripts block automation. For `sync_vault.py --full` in CI or headless mode, replace `input("Press Enter...")` with command-line flags.

See [`references/vault-sync-patterns.md`](references/vault-sync-patterns.md) for incremental sync, slugify rules, and ChromaDB rebuild procedures.

### 6. Venv Isolation (Windows)

Hermes Agent's Python leaks into subprocesses, causing `ModuleNotFoundError` even after successful `pip install` in a project venv.

See [`references/venv-isolation-windows.md`](references/venv-isolation-windows.md) for the full isolation pattern using absolute paths and `launch.py` wrappers.

### Credential Management (1Password + ElevenLabs)

For TTS and other third-party APIs, store credentials locally after one-shot extraction:

```python
from pathlib import Path

# Load once, use forever
ELEVENLABS_KEY = (Path.home() / ".ultron" / "elevenlabs_key.txt").read_text().strip()
ELEVENLABS_VOICE = (Path.home() / ".ultron" / "elevenlabs_voice.txt").read_text().strip()
```

**The ONLY reliable method for headless 1Password auth on Windows is a Service Account.** See [`references/1password-windows-credential-extraction.md`](references/1password-windows-credential-extraction.md) for the full saga and Service Account setup.

**Token-format trap.** `op` reads `OP_SERVICE_ACCOUNT_TOKEN` (not `1PASSWORD_API_KEY`). If a user points you at a Windows env var named `1PASSWORD_API_KEY`, the value there is usually **not** a real service-account credential — most often a Tailscale pre-auth key (`A3-XXXX-XXXX-...`) accidentally stored in that slot. `op whoami` will reject it with `failed to DecodeSACredentials: failed to parseToken, format is invalid`. The fix is to **rename the env var** (so future agents stop looking there) and store the real SAC, sourced from `~/.ultron/.op_service_account` if you already have one, in `OP_SERVICE_ACCOUNT_TOKEN`. See [`references/1password-windows-credential-extraction.md`](references/1password-windows-credential-extraction.md) for the full saga and Service Account setup.
See [`references/elevenlabs-tts-integration.md`](references/elevenlabs-tts-integration.md) for wiring ElevenLabs into response loops.
See [`references/vision-integration.md`](references/vision-integration.md) for integrating Vision (accessibility operator) with NEXUS CORE.

### 7. Integrating with Vision (Windows Accessibility Operator)

Vision is a voice-first Windows operator (`github.com/dqikfox/vision`) that can query NEXUS CORE via a bridge module:

```python
# nexus_bridge.py — add to Vision project root
from vision_nexus_tools import nexus_ask_sync

# Query vault knowledge
result = nexus_ask_sync("What is my Tailscale IP?", model="starscream")
```

Vision runs its own FastAPI server on port 8765. To avoid Python path pollution from Hermes, launch it with an isolated wrapper:

```python
# launch_elite_isolated.py
import sys
PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_SITE = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"

# Remove Hermes paths, add venv first
sys.path = [str(VENV_SITE)] + [
    p for p in sys.path 
    if "hermes" not in p.lower() and "hermes-agent" not in p.lower()
]

import uvicorn
uvicorn.run("live_chat_app:app", host="0.0.0.0", port=8765)
```

**Pitfall — FastAPI union return types**: Vision's `live_chat_app.py` uses `-> FileResponse | JSONResponse` on route handlers. Under Pydantic v2, this causes `FastAPIError: Invalid args for response field!` at startup. Fix by adding `response_model=None` to the decorator:

```python
# BEFORE (crashes)
@app.get("/api/export/trace")
async def api_export_trace() -> FileResponse | JSONResponse:

# AFTER (works)
@app.get("/api/export/trace", response_model=None)
async def api_export_trace():
```

## Common Failure Modes

| Symptom | Root Cause | Fix |
|---|---|---|
| Empty LLM answers | VRAM 100% full | Use smaller model; check `nvidia-smi` |
| ChromaDB dimension error | Changed embedding provider | `shutil.rmtree(CHROMA_DIR)` and reindex |
| Graph nodes have size=0 | `list_notes()` omits body | Query `SELECT ... body FROM notes` directly |
| Zero links in vault graph | Body text missing from nodes | Same as above |
| `get_note(id)` returns None | Function takes slug, not id | Pass `note["slug"]` instead of `note["id"]` |
| Indexing silently skips notes | `index_note()` passes id to `get_note()` | Fetch by slug: `get_note(note["slug"])` |

## Voice Integration

For TTS with ElevenLabs (or other providers), store credentials locally in encrypted form:

```python
from cryptography.fernet import Fernet
from pathlib import Path

SECRETS_FILE = Path.home() / ".ultron" / "secrets.enc"

def encrypt_creds(api_key: str, voice_id: str) -> bytes:
    key = Fernet.generate_key()
    cipher = Fernet(key)
    payload = json.dumps({"elevenlabs_api_key": api_key, "voice_id": voice_id})
    return key + cipher.encrypt(payload.encode())

def decrypt_creds(data: bytes) -> dict:
    key, encrypted = data[:44], data[44:]
    return json.loads(Fernet(key).decrypt(encrypted).decode())
```

**Why:** Avoids interactive credential prompts. Users with "full trust, no guardrails" preference want autonomous access without manual steps each session.

## FastAPI Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | DB count, Chroma status, Ollama models |
| `POST /api/ask` | RAG query with model selection |
| `GET /api/vault-graph` | D3.js graph data (nodes + links) |
| `GET /api/notes/{slug}` | Full note body |
| `WS /ws/chat` | Streaming chat WebSocket |

## FastAPI Server with WebSocket Streaming

NEXUS CORE runs as a FastAPI application with these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /health` | GET | DB count, Chroma status, Ollama models, memory layers |
| `POST /api/ask` | POST | RAG query with `query`, `model`, `top_k` form data |
| `GET /api/vault-graph` | GET | D3.js graph data (nodes + wikilink links) |
| `GET /api/notes/{slug}` | GET | Full note body by slug |
| `GET /api/models` | GET | Enumerate available Ollama models |
| `WS /ws/chat` | WS | Streaming chat WebSocket |

### Server Startup

```python
# launch.py — isolates from Hermes Python
import sys
hermes_paths = [p for p in sys.path if "hermes-agent" in p.lower()]
for p in hermes_paths:
    sys.path.remove(p)

import uvicorn
from server import app
uvicorn.run("server:app", host="127.0.0.1", port=8650)
```

**Pitfall:** Using `uvicorn.run(app, ...)` directly with string module reference fails if `sys.path` is polluted. Use `uvicorn.run("server:app", ...)` with import-string syntax.

### In-process launcher for env-inherited secrets

When the long-running service needs secrets injected at startup (from 1Password, Vault, etc.), the launcher must `os.execvp` itself into the real server process — otherwise the secrets stay in the launcher's subprocess and never reach uvicorn:

```python
# start.py — load secrets, then replace this process with uvicorn
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
from load_secrets import ensure_env_refs, load_secrets  # op run wrapper

ensure_env_refs()
load_secrets()  # resolves op:// refs into os.environ

# Replace this Python with uvicorn — secrets stay in the new process's env
os.chdir(Path(__file__).parent)
os.execvp(sys.executable, [sys.executable, "-m", "uvicorn",
                            "server:app", "--host", "127.0.0.1", "--port", "8650"])
```

A `.bat` / `.sh` wrapper that calls `load_secrets.py` and then runs uvicorn
**does not work** — each subprocess gets a fresh env and loses the secrets.
The exec-in-place pattern is the only reliable shape. See
`ai-agent-secrets` skill (`scripts/load_secrets.py`) for the full template
and the rationale.

## References

- [`references/1password-windows-credential-extraction.md`](references/1password-windows-credential-extraction.md) — Headless credential extraction via Service Account
- [`references/elevenlabs-tts-integration.md`](references/elevenlabs-tts-integration.md) — Personal voice synthesis wiring
- [`references/venv-isolation-windows.md`](references/venv-isolation-windows.md) — Windows venv isolation from Hermes Python
- [`references/vault-sync-patterns.md`](references/vault-sync-patterns.md) — Incremental sync, slugify, ChromaDB rebuild
- [`references/nexus-core-build-log.md`](references/nexus-core-build-log.md) — Complete build diary: venv isolation, uv vs pip, tokenizers compatibility
- [`references/vault-sync-patterns.md`](references/vault-sync-patterns.md) — Slug collision handling, folder-to-source mapping, incremental sync
- [`references/embedding-provider-switching.md`](references/embedding-provider-switching.md) — ChromaDB dimension management, dynamic collection names, provider fallback logic
- [`references/ollama-rag-troubleshooting.md`](references/ollama-rag-troubleshooting.md) — Empty response diagnosis, /api/generate vs /api/chat, VRAM management
- [`references/unc-path-issues.md`](references/unc-path-issues.md) — Q: drive / UNC-path venv and pip install failures on Windows
- [`references/memory-graph-relations.md`](references/memory-graph-relations.md) — Building weighted relations between memories by tag/entity/source overlap; ingesting vault notes as memory nodes

## Related skills

- `ollama-modelfile-authoring` — Model config and chat templates
- `hermes-obsidian-integration` — Hermes plugin fixes and Smart Graph limitations
- `llama-cpp` — Raw llama.cpp inference (bypass Ollama)
- `python-environment-management` — uv/pip venv setup
