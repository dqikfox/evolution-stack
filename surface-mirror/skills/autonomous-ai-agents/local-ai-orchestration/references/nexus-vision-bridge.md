# NEXUS CORE ↔ Vision Bridge Architecture

## Overview

This bridge connects Vision (voice-controlled computer operator) with NEXUS CORE (local knowledge base) by injecting NEXUS tools into Vision's runtime tool registry without modifying Vision's source code.

## Files

| File | Purpose | Loads When |
|------|---------|------------|
| `nexus_bridge.py` | HTTP client for NEXUS CORE API (async + sync) | Import from any module |
| `vision_nexus_tools.py` | Tool definitions + handlers compatible with Vision's tool format | `elite_patch.py` imports |
| `elite_patch.py` | Monkey-patches tools into Vision's `TOOLS` list and `exec_tool` | Before `live_chat_app` import |
| `elite_launcher.py` | Entry point: patches → imports Vision → starts server | `python elite_launcher.py` |
| `test_nexus_integration.py` | Verification harness for all components | `python test_nexus_integration.py` |

## Integration Sequence

```python
# Must happen BEFORE importing live_chat_app
from elite_patch import apply_elite_patch
apply_elite_patch()  # Extends TOOLS list, patches exec_tool

# Now safe to import Vision
import live_chat_app
live_chat_app.main()
```

## NEXUS CORE Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | System status, DB count, model list |
| `/api/ask` | POST | RAG query with vault knowledge |
| `/api/vault-graph` | GET | Nodes + links for visualization |
| `/api/hive/message` | POST | Multi-agent messaging |
| `/api/hive/messages/{channel}` | GET | Read Hive Bus messages |
| `/api/models` | GET | List Ollama models |

## Vision Tool Registry Additions

After patch, Vision recognizes these tools by name:
- `nexus_ask(query, model="starscream", top_k=5)` — Vault RAG
- `nexus_memory(query)` — Memory context retrieval
- `nexus_hive_post(content, channel="general")` — Send to Hive Bus
- `nexus_hive_read(channel="general", limit=5)` — Read Hive Bus
- `nexus_graph()` — Vault graph stats
- `nexus_health()` — System health
- `nexus_models()` — List available models

## Configuration

`vision_command_center_config.json` gains a `nexus_core` section:
```json
{
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

## VRAM Strategy

Vision's default model should be `starscream` (17GB) instead of `megatron` (21.7GB) to leave headroom on a 24GB card:
```powershell
$env:OLLAMA_KEEP_ALIVE = "30m"  # Or "5m" for aggressive unloading
$env:VISION_DEFAULT_MODEL = "starscream"
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ImportError: No module named 'nexus_bridge'` | Wrong Python interpreter (Hermes venv pollution) | Use Vision's own Python: `C:\project\vision\.venv\Scripts\python.exe` |
| `Event loop is closed` | Calling async tools from sync context without `asyncio.run()` | Use `nexus_ask_sync()` instead of `nexus_ask()` |
| `Connection refused` on :8650 | NEXUS CORE server not running | Start it: `cd nexus-core-throne && python launch.py` |
| `400 Bad Request: invalid model name` | Ollama create run outside `.ollama/models/` | `cd ~/.ollama/models && ollama create ...` |

## Code Templates

See `templates/nexus_bridge.py` and `templates/vision_nexus_tools.py` for starter files to drop into new Vision instances.
