# Ollama Keep-Alive and VRAM Management

## Context

When running local Ollama models alongside other GPU workloads, managing how long models stay loaded is critical for VRAM availability. This reference documents the `OLLAMA_KEEP_ALIVE` parameter and patterns for keeping models resident.

## OLLAMA_KEEP_ALIVE Values

| Value | Behavior | Use Case |
|-------|----------|----------|
| `-1` | Keep loaded forever | Dedicated inference server |
| `30m` | Unload after 30 min idle | Interactive sessions, default for this user |
| `5m` | Unload after 5 min idle | Conservative VRAM management |
| `0` | Unload immediately after request | Minimal VRAM usage (high latency) |
| `1h`, `2h` | Extended keep-alive | Batch processing, long conversations |

## Setting Keep-Alive

### Method 1: Environment Variable (Recommended for Scripts)

```powershell
# PowerShell
$env:OLLAMA_KEEP_ALIVE = "30m"

# Or permanent (system-wide)
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "30m", "User")
```

```bash
# Bash (MSYS/Git Bash)
export OLLAMA_KEEP_ALIVE="30m"
```

### Method 2: Ollama Launch Wrapper

```powershell
# launch_elite.ps1
$env:OLLAMA_KEEP_ALIVE = "30m"
$env:VISION_DEFAULT_MODEL = "starscream"
python live_chat_app.py
```

### Method 3: Per-Request Override

```python
import requests

# Force unload after this request
requests.post("http://localhost:11434/api/generate", json={
    "model": "starscream",
    "prompt": "Hello",
    "keep_alive": "0"  # Unload immediately
})
```

## VRAM Reality for 24GB RTX 3090

| Model | Quant | Context | VRAM | Notes |
|-------|-------|---------|------|-------|
| megatron (Qwen3.5 MoE 35B) | Q4_K_M | 128K | ~21.7GB | Leaves ~2GB free — fragile with other GPU consumers |
| starscream (Gemma 4 26B) | Q4 | 128K | ~17GB | Comfortable headroom for browser + overlays |
| qwen2.5:14b | Q4_K_M | 8K | ~8GB | Plenty of headroom |

**Rule of thumb:** If `nvidia-smi` shows >95% VRAM usage, Ollama returns empty responses. Switch to a smaller model or free GPU memory.

## Checking Model Status

```bash
# See which models are loaded
ollama ps

# Example output:
# NAME                    ID              SIZE    PROCESSOR   UNTIL
# starscream:latest       abcd1234        17 GB   100% GPU    28 minutes from now
# megatron:latest         efgh5678        22 GB   100% GPU    15 minutes from now
```

**The `UNTIL` column shows when Ollama will unload the model.** If you need it to stay longer, set a higher `OLLAMA_KEEP_ALIVE` value and reload.

## `ollama launch hermes --model <name>`

Ollama v0.32.13+ supports launching Hermes Agent directly:

```bash
# Launch Hermes with a specific model
ollama launch hermes --model starscream

# Launch with cloud model via provider
ollama launch hermes --model kimi-k2.7-code:cloud

# The -- separator passes args to Hermes after Ollama handles the launch
ollama launch hermes --model starscream -- --version
```

**Verified working:** Launches Hermes Agent v0.20.0 with the specified model pre-configured as default.

## Session Source

THRONE session 2026-08-17. User requested `OLLAMA_KEEP_ALIVE=30m` and verified `ollama launch hermes --model` functionality.
