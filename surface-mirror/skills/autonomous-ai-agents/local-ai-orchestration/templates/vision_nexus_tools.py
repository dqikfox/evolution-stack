"""
vision_nexus_tools.py — NEXUS CORE tools for Vision Operator
============================================================
Tool definitions + handlers compatible with Vision's tool format.
Drop this into your Vision project root.
"""

import asyncio
import json
from typing import Any, Dict

from nexus_bridge import get_bridge, NexusBridge

# Tool definitions (Vision-compatible format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "nexus_ask",
            "description": "Query your Obsidian vault knowledge base for information. Use when the user asks about their personal data, configs, notes, or stored knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The question to ask the vault"},
                    "model": {"type": "string", "enum": ["starscream", "megatron", "CYBA"], "default": "starscream"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "nexus_hive_post",
            "description": "Post a message to the multi-agent Hive Bus shared consciousness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "default": "general"},
                    "content": {"type": "string"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "nexus_health",
            "description": "Check NEXUS CORE system health.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]

# ── Tool Handlers ────────────────────────────────────

async def nexus_ask(query: str, model: str = "starscream", top_k: int = 5) -> str:
    bridge = get_bridge()
    result = await bridge.ask(query, model=model, top_k=top_k)
    if result.get("error"):
        return f"❌ Error: {result['error']}"
    answer = result.get("answer", "No answer")
    sources = result.get("sources", [])
    source_list = ""
    if sources and isinstance(sources[0], dict):
        source_list = ", ".join([s.get("slug", "") for s in sources[:3]])
    elif sources and isinstance(sources[0], str):
        source_list = ", ".join(sources[:3])
    return f"📚 {answer}\n\n🔍 Sources: {source_list}" if source_list else answer

def nexus_ask_sync(query: str, model: str = "starscream", top_k: int = 5) -> str:
    bridge = get_bridge()
    result = bridge.ask_sync(query, model=model, top_k=top_k)
    if result.get("error"):
        return f"❌ Error: {result['error']}"
    answer = result.get("answer", "No answer")
    sources = result.get("sources", [])
    source_list = ""
    if sources and isinstance(sources[0], dict):
        source_list = ", ".join([s.get("slug", "") for s in sources[:3]])
    elif sources and isinstance(sources[0], str):
        source_list = ", ".join(sources[:3])
    return f"📚 {answer}\n\n🔍 Sources: {source_list}" if source_list else answer

async def nexus_hive_post(content: str, channel: str = "general") -> str:
    bridge = get_bridge()
    success = await bridge.post_to_hive(channel, content, agent="vision")
    return f"✅ Posted to #{channel}" if success else "❌ Failed"

async def nexus_health() -> str:
    bridge = get_bridge()
    health = await bridge.health()
    return f"🧠 NEXUS: {health.get('status', '?')} | {health.get('components',{}).get('database',{}).get('notes_count',0)} notes"

# Tool handler map for Vision integration
TOOL_HANDLERS = {"nexus_ask": nexus_ask, "nexus_hive_post": nexus_hive_post, "nexus_health": nexus_health}
SYNC_TOOL_HANDLERS = {"nexus_ask": nexus_ask_sync}

if __name__ == "__main__":
    print(asyncio.run(nexus_health()))
    print(asyncio.run(nexus_ask("What is my Tailscale IP?")))
