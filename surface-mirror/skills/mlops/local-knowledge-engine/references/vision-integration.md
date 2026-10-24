# Vision + NEXUS CORE Integration

## Context

Vision (`github.com/dqikfox/vision`) is a Windows-first voice-controlled accessibility operator with its own FastAPI backend (port 8765). NEXUS CORE is a local knowledge engine (port 8650). This reference documents how to bridge them so Vision can query vault knowledge via NEXUS CORE's RAG pipeline.

## Architecture

```
Vision (port 8765)
  └─ nexus_bridge.py ──► NEXUS CORE (port 8650)
                              ├─ SQLite + FTS5 (327 notes)
                              ├─ ChromaDB (vectors)
                              └─ Ollama (starscream)
```

## Integration Files

Add these to Vision's project root:

### 1. nexus_bridge.py

```python
"""Bridge between Vision and NEXUS CORE local knowledge base."""
import requests
from typing import Optional, Dict, Any

NEXUS_URL = "http://127.0.0.1:8650"

class NexusBridge:
    def __init__(self, base_url: str = NEXUS_URL, default_model: str = "starscream"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def health_sync(self) -> Dict[str, Any]:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.json() if resp.status_code == 200 else {"ok": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ask_sync(self, query: str, model: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
        try:
            resp = requests.post(
                f"{self.base_url}/api/ask",
                data={"query": query, "model": model or self.default_model, "top_k": top_k},
                timeout=120
            )
            return resp.json() if resp.status_code == 200 else {"answer": "", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"answer": "", "error": str(e)}
```

### 2. vision_nexus_tools.py

```python
"""NEXUS CORE tools for Vision's tool registry."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "nexus_ask",
            "description": "Query your Obsidian vault knowledge base (2nd Brain) for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The question to ask the vault"},
                    "model": {"type": "string", "enum": ["starscream", "megatron", "CYBA"]},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    # ... additional tools: nexus_memory, nexus_hive_post, nexus_hive_read, nexus_graph, nexus_health, nexus_models
]

# Tool implementations omitted for brevity — see full file in session artifact
```

### 3. elite_patch.py

```python
"""Monkey-patches NEXUS CORE tools into Vision at runtime without modifying source."""
import live_chat_app
from vision_nexus_tools import TOOLS as NEXUS_TOOLS

live_chat_app.TOOLS.extend(NEXUS_TOOLS)
live_chat_app.TOOL_DESCRIPTIONS = "\n".join(
    f"  {t['function']['name']}: {t['function']['description']}"
    for t in live_chat_app.TOOLS
)
```

See [`references/fastapi-pydantic-v2-union-return-types.md`](references/fastapi-pydantic-v2-union-return-types.md) for full details on which patterns fail and why.

## Isolated Launcher

Vision's `live_chat_app.py` imports many packages that conflict with Hermes' Python environment. Use an isolated launcher:

```python
# launch_elite_isolated.py
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_SITE = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"

# Remove Hermes paths, add venv first
sys.path = [str(VENV_SITE)] + [
    p for p in sys.path 
    if "hermes" not in p.lower() and "hermes-agent" not in p.lower()
]

import uvicorn
uvicorn.run("live_chat_app:app", host="0.0.0.0", port=8765, log_level="warning")
```

## Critical Pitfall: FastAPI Union Return Types

Vision's `live_chat_app.py` uses `-> FileResponse | JSONResponse` on route handlers. Under Pydantic v2 (which FastAPI uses), this causes:

```
FastAPIError: Invalid args for response field! Hint: check that 
starlette.responses.FileResponse | starlette.responses.JSONResponse 
is a valid Pydantic field type.
```

**Fix:** Add `response_model=None` to disable Pydantic response model generation:

```python
# BEFORE (crashes on startup)
@app.get("/api/export/trace")
async def api_export_trace() -> FileResponse | JSONResponse:

# AFTER (works)
@app.get("/api/export/trace", response_model=None)
async def api_export_trace():
```

## Environment Setup

```powershell
# Vision config: vision_command_center_config.json
{
  "profile_name": "eliter",
  "launcher": {
    "ollama_access_mode": "local",
    "ollama_host": "127.0.0.1:11434",
    "ollama_models_path": "C:\\Users\\KING\\.ollama\\models"
  },
  "nexus_core": {
    "enabled": true,
    "url": "http://127.0.0.1:8650",
    "default_model": "starscream",
    "rag_enabled": true,
    "hive_enabled": true,
    "remote_rag": "//MSI/rag-v1"
  }
}
```

## VRAM Strategy for 24GB

| Model | Size | Use |
|-------|------|-----|
| starscream | ~17GB | Default for Vision + NEXUS RAG |
| megatron | ~21.7GB | Explicit request only (leaves ~2GB free) |
| qwen2.5:14b | ~8GB | Fallback |

Set `$env:OLLAMA_KEEP_ALIVE = "30m"` in launcher to keep models loaded between queries.

## Verification Commands

```bash
# Check both services
curl -s http://127.0.0.1:8765/api/health | python -c "import sys,json; d=json.load(sys.stdin); print('Vision:', d.get('current_model'))"
curl -s http://127.0.0.1:8650/health | python -c "import sys,json; d=json.load(sys.stdin); print('NEXUS:', d['status'], '|', d['components']['database']['notes_count'])"

# Test RAG bridge
python -c "from vision_nexus_tools import nexus_ask_sync; print(nexus_ask_sync('What is my Tailscale IP?', model='starscream'))"
```

## Session Source

Built during THRONE session 2026-08-17. Full working files at:
- `C:\Users\KING\projects\vision\nexus_bridge.py`
- `C:\Users\KING\projects\vision\vision_nexus_tools.py`
- `C:\Users\KING\projects\vision\elite_patch.py`
- `C:\Users\KING\projects\vision\launch_elite_isolated.py`
