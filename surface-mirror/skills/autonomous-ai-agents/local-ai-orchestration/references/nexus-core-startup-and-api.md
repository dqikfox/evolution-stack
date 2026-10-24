# NEXUS CORE Startup & Key APIs

## Startup (Windows)

NEXUS CORE runs from `Q:\ultron-memory\nexus-core\` and uses a dedicated venv at `C:\Users\KING\.cache\nexus-venv` (NOT the local `.venv`).

### Launch (foreground for visibility)
```bash
C:/Users/KING/.cache/nexus-venv/Scripts/python.exe Q:/ultron-memory/nexus-core/server.py
```

### Launch (background via cmd for OpenClaw-style daemon)
```bash
cmd.exe /c "start /b C:\Users\KING\.cache\nexus-venv\Scripts\python.exe Q:\ultron-memory\nexus-core\server.py"
```

### MSYS2 path-mangling trap
In MSYS2/bash, `/q/ultron-memory/...` gets mangled to `C:\q\ultron-memory\...` when passed as an argument to a Windows binary (python.exe, node.exe, etc.). Always use explicit `Q:/...` or `C:/...` forms, never `/q/`.

### Verify
```bash
curl -4 -s --max-time 5 http://127.0.0.1:8650/health
# → {"ok":true,"status":"live","service":"nexus-core","version":"3.3.0",...}
```

### Health response structure
```json
{
  "ok": true,
  "status": "live",
  "service": "nexus-core",
  "version": "3.3.0",
  "components": {
    "database": {"status": "ok", "notes_count": 1050},
    "ollama": {"status": "ok", "models": ["megatron-fixed-32k:latest", ...]},
    "chroma": {"status": "ok", "vectors": 1050},
    "megatron_memory": {
      "status": "ok",
      "episodes": 2,
      "semantic_facts": 29,
      "semantic_categories": ["user", "pytest", "system"],
      "skills": 0
    }
  }
}
```

## Semantic Facts API (Megatron Memory)

The endpoint uses **form-encoded POST**, not JSON.

### Store a fact
```bash
curl -s -X POST http://127.0.0.1:8650/api/memory/fact \
  -d 'key=system.ollama.context-length' \
  -d 'value=65536' \
  -d 'category=system' \
  -d 'confidence=1.0'
# → {"status":"stored","key":"system.ollama.context-length","category":"system"}
```

### List all facts
```bash
curl -s http://127.0.0.1:8650/api/memory/facts
# → {"facts":{"key.name":{"value":"...","confidence":1.0,"stored_at":"...","version":1}, ...}}
```

### Query by category
```bash
curl -s "http://127.0.0.1:8650/api/memory/facts?category=system"
```

### Pitfall: JSON body is rejected
The `/api/memory/fact` endpoint does NOT accept JSON. Sending `Content-Type: application/json` returns:
```json
{"detail":[{"type":"missing","loc":["body","key"],"msg":"Field required","input":null}]}
```
Always use `-d 'key=...' -d 'value=...'` (URL-encoded form), not `-H 'Content-Type: application/json' -d '{"key":"..."}'`.

## Config file: core/config.py

Key settings in `Q:\ultron-memory\nexus-core\core\config.py`:
- `OLLAMA_MODEL = "megatron-fixed"` — default RAG model
- `EMBEDDING_PROVIDER = "chroma-default"` — 384-dim MiniLM, no Ollama dependency
- `PORT = 8650`
- `HOST = "127.0.0.1"`
- `CHROMA_DIR = DATA_DIR / "chroma"` — persistent on-disk vector DB
