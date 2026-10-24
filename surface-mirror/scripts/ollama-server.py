#!/usr/bin/env python
"""
ollama-server.py - Persistent local LLM server health daemon
Listens on 0.0.0.0:11434 health, proxies to local Ollama, falls back gracefully.
"""
import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import psutil
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
except ImportError as e:
    print(f"missing dep: {e}", file=sys.stderr); sys.exit(2)

LOG = Path(os.environ.get("OLLAMA_HEALTH_LOG",
                          r"C:\Users\KING\AppData\Local\hermes\health\ollama.log"))
LOG.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG), logging.StreamHandler()],
)
log = logging.getLogger("ollama-daemon")

UPSTREAM = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434")
HOST = os.environ.get("OLLAMA_HEALTH_HOST", "0.0.0.0")
PORT = int(os.environ.get("OLLAMA_HEALTH_PORT", "11435"))

app = FastAPI(title="Ollama Health Daemon", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    """Cheap liveness probe for cron."""
    return {"ok": True, "ts": datetime.utcnow().isoformat() + "Z"}


@app.get("/ollama/tags")
async def ollama_tags() -> dict:
    """Proxy model list to upstream Ollama, never blocks."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{UPSTREAM}/api/tags")
            return r.json()
    except Exception as e:
        log.warning(f"upstream unreachable: {e}")
        return {"error": str(e), "upstream": UPSTREAM}


@app.get("/ollama/stats")
async def ollama_stats() -> dict:
    """Host metrics useful for cron alerts."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        gpus = []
        import subprocess
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        for row in out.stdout.strip().splitlines():
            parts = [p.strip() for p in row.split(",")]
            if len(parts) == 5:
                gpus.append({
                    "i": int(parts[0]), "temp": int(parts[1]),
                    "util": int(parts[2]),
                    "mem_used_mb": int(parts[3]),
                    "mem_total_mb": int(parts[4]),
                })
    except Exception:
        gpus = None
    return {
        "cpu_pct": cpu, "mem_pct": mem.percent, "mem_avail_mb": int(mem.available/1e6),
        "disk_pct": disk.percent, "gpus": gpus, "ts": datetime.utcnow().isoformat() + "Z",
    }


if __name__ == "__main__":
    log.info(f"start upstream={UPSTREAM} bind={HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")