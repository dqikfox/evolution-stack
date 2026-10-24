"""
nexus_bridge.py — NEXUS CORE integration for Vision
====================================================
HTTP client for NEXUS CORE API (async + sync wrappers).
Drop this into your Vision project root.
"""

import requests
import asyncio
import aiohttp
from typing import Optional, Dict, List, Any

NEXUS_URL = "http://127.0.0.1:8650"
DEFAULT_MODEL = "starscream"

class NexusBridge:
    def __init__(self, base_url: str = NEXUS_URL, default_model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def health(self) -> Dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                return await resp.json() if resp.status == 200 else {"ok": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_sync(self) -> Dict[str, Any]:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.json() if resp.status_code == 200 else {"ok": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def ask(self, query: str, model: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
        session = await self._get_session()
        payload = {"query": query, "model": model or self.default_model, "top_k": top_k}
        try:
            async with session.post(f"{self.base_url}/api/ask", data=payload, timeout=120) as resp:
                return await resp.json() if resp.status == 200 else {"answer": "", "error": f"HTTP {resp.status}"}
        except asyncio.TimeoutError:
            return {"answer": "", "error": "Timeout — model loading may be slow"}
        except Exception as e:
            return {"answer": "", "error": str(e)}

    def ask_sync(self, query: str, model: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
        payload = {"query": query, "model": model or self.default_model, "top_k": top_k}
        try:
            resp = requests.post(f"{self.base_url}/api/ask", data=payload, timeout=120)
            return resp.json() if resp.status_code == 200 else {"answer": "", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"answer": "", "error": str(e)}

    async def vault_graph(self) -> Dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/api/vault-graph", timeout=10) as resp:
                return await resp.json() if resp.status == 200 else {"nodes": [], "links": []}
        except Exception:
            return {"nodes": [], "links": []}

    async def list_models(self) -> List[Dict]:
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/api/models", timeout=10) as resp:
                return (await resp.json()).get("models", []) if resp.status == 200 else []
        except Exception:
            return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

_nexus_bridge: Optional[NexusBridge] = None

def get_bridge() -> NexusBridge:
    global _nexus_bridge
    if _nexus_bridge is None:
        _nexus_bridge = NexusBridge()
    return _nexus_bridge


if __name__ == "__main__":
    bridge = NexusBridge()
    print("Health:", bridge.health_sync())
    print("Ask:", bridge.ask_sync("What is my Tailscale IP?"))
