---
name: mainframe-bootstrap
description: Bootstrap THRONE with Python, services, scripts.
---

# Mainframe Bootstrap

## When to load
- Setting up a new THRONE host
- "install whatever you need"
- "build the ultimate ai mainframe"
- After major Windows reinstall

## Required packages (elite baseline)
```
pip install --quiet \
    psutil aiohttp fastapi 'uvicorn[standard]' pydantic watchfiles tenacity \
    rich typer 'httpx[http2]' prometheus_client structlog numpy \
    pypdf markdownify beautifulsoup4 pillow requests opencv-python-headless \
    scikit-learn pywin32 pyttsx3 sounddevice faster-whisper
```

## Directory layout to create
```
%LOCALAPPDATA%/hermes/scripts/          # python daemon scripts
%LOCALAPPDATA%/hermes/bin/              # symlinked tool wrappers
%LOCALAPPDATA%/hermes/health/           # healthcheck logs
%LOCALAPPDATA%/hermes/audit/            # audit trail
C:/Users/KING/Projects/TESSERACT/       # main project repo
C:/Users/KING/Projects/ULTRON/          # secondary repo
```

## Services to register
- **Ollama**: `sc.exe create Ollama binPath= "<ollama.exe> serve" start= auto`
- **HERETIK**: NSSM wrapper for llama-server.exe
- **NEXUS**: NSSM wrapper for nexus-core
- **Ollama_Health_Beat**: scheduled task every 5min

## Required scripts (write under scripts/)
- `ollama_health.py` — POST to :11434, log + alert
- `throttle_audit.py` — process audit + safe-kill
- `memory_hygiene.py` — scan USER.md/MEMORY.md, flag stale
- `workspace_backup.py` — verify recent commits + rsync to E:/backup

## Verify
- `python -c "import psutil, fastapi, uvicorn, pydantic, watchfiles, tenacity, rich, typer, prometheus_client, structlog, numpy, sklearn, faster_whisper"` — must succeed
- All scripts exit 0 in --dry-run mode

## Do not
- Install GPU pytorch wheels (separate environment)
- Force-install conflicting versions
- Touch existing working scripts