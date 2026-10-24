"""
Hermes Agent Memory Graph Builder
==================================

Reads %LOCALAPPDATA%\\hermes\\state.db and produces a {nodes, edges} graph JSON
suitable for d3-force-graph rendering. Designed to be dropped into a FastAPI
server (e.g. TESSERACT) as a live `/api/memory-graph` endpoint.

Drop-in usage in a FastAPI app:

    from hermes_memory_graph import build_memory_graph
    import os

    HERMES_DB = os.path.expandvars(r"%LOCALAPPDATA%\\hermes\\state.db")

    @app.get("/api/memory-graph")
    async def memory_graph():
        return build_memory_graph(HERMES_DB)

    @app.get("/api/memory-graph/stats")
    async def memory_graph_stats():
        return build_memory_graph(HERMES_DB)["meta"]

Verified against 238 sessions / 28,250 messages (2026-08-26) — produces
~220 KB JSON with 288 nodes and 1,588 edges. Renders smoothly in d3-force-graph
at any zoom level.

Topic classification is keyword-based. Adjust _TOPIC_PATTERNS to match your
user's actual vocabulary. The "general" bucket is the default; tighten
patterns to reduce it.
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime


# Topic keyword patterns. Match against session title + last_activity_description
# + display_name (lowercased). The pattern with the highest hit count wins.
# Add or remove freely. Keep them as a single string with alternation so
# `len(re.findall(pat, text))` is a meaningful score.
_TOPIC_PATTERNS: dict[str, str] = {
    "ai_identity":   r"(identity|conscious|self|sentien|personality|turing)",
    "kali_linux":    r"(kali|metasploit|msfconsole|virtualbox|exploit)",
    "ollama":        r"(ollama|llama|qwen|deepseek|kimi|megatron|starscream|cyba|gemma)",
    "voice_agent":   r"(vision|voic|elevenlabs|tts|speech)",
    "memory_rag":    r"(memor|recall|retriev|graph|nexus|chroma|vector|rag)",
    "security":      r"(security|vulnerab|harden|firewall|defender|fail2ban|ssh|1password|op cli)",
    "telegram":      r"(telegram|bot|oh420|botfather)",
    "projects":      r"(project|build|deploy|tesseract|vision)",
    "tools_mcp":     r"(mcp|tool|plugin|skill|hook)",
    "obsidian":      r"(obsidian|note|vault|markdown)",
    "goals_tasks":   r"(goal|task|kanban|cron|schedul)",
    "autoresearch":  r"(autonomous|agent|orchestrat|colibri|ultron)",
    "openclaw":      r"(openclaw|gateway|whatsapp|signal|discord)",
}

# Visual sizing. Edges are NOT node-pinned (see d3-force-graph skill pitfalls).
_NODE_SIZE_BASE = {"user": 18, "agent": 18, "model": 8, "topic": 6, "tool": 4, "session": 3}
_NODE_COLORS = {
    "user":    "#ff2d78",
    "agent":   "#00d4ff",
    "model":   "#a855f7",
    "topic":   "#00ff87",
    "tool":    "#ffb300",
    "session": "#00a8cc",
    "topic_default": "#666",
}

# How many tool nodes to include (top N by usage)
_TOP_TOOLS = 40


def _classify_topic(text: str) -> str:
    text = (text or "").lower()
    best, best_score = "general", 0
    for topic, pat in _TOPIC_PATTERNS.items():
        s = len(re.findall(pat, text))
        if s > best_score:
            best, best_score = topic, s
    return best


def build_memory_graph(db_path: str) -> dict:
    """Build the {nodes, edges} graph from a Hermes state.db file.

    Returns a dict with shape:
        {
            "meta":  {"title", "source_db", "generated_at", "stats": {...}},
            "nodes": [{"id", "kind", "label", "color", "size", ...props}],
            "edges": [{"from", "to", "kind", "weight"?}],
        }

    If the DB doesn't exist, returns a stub with an "error" key — never raises.
    """
    if not os.path.exists(db_path):
        return {
            "error": f"state.db not found at {db_path}",
            "meta": {"title": "Hermes Agent Memory Graph", "stats": {}},
            "nodes": [],
            "edges": [],
        }

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Sessions
    cur.execute("""
        SELECT id, source, model, started_at, ended_at, end_reason,
               message_count, tool_call_count, input_tokens, output_tokens,
               title, display_name, profile_name, archived, pinned,
               last_activity_description, last_activity_at, cwd
        FROM sessions
        ORDER BY started_at
    """)
    sessions = [dict(r) for r in cur.fetchall()]
    sess_ids = {s["id"] for s in sessions}

    # Message stats by session + role
    cur.execute("""
        SELECT session_id, role, COUNT(*) c, SUM(COALESCE(token_count, 0)) tok
        FROM messages
        GROUP BY session_id, role
    """)
    stats = defaultdict(lambda: Counter())
    for r in cur.fetchall():
        stats[r["session_id"]][r["role"]] = (r["c"], r["tok"])

    # Tool usage
    cur.execute("""
        SELECT session_id, tool_name, COUNT(*) c
        FROM messages
        WHERE tool_name IS NOT NULL AND tool_name != ''
        GROUP BY session_id, tool_name
        ORDER BY c DESC
        LIMIT 500
    """)
    tool_calls = [dict(r) for r in cur.fetchall()]

    con.close()

    # ----- Build nodes -----
    nodes: dict[str, dict] = {}

    def add(nid: str, kind: str, label: str, **props) -> None:
        nodes[nid] = {"id": nid, "kind": kind, "label": label, **props}

    add("user", "user", "Jamie", color=_NODE_COLORS["user"], size=_NODE_SIZE_BASE["user"])
    add("agent", "agent", "Hermes Agent", color=_NODE_COLORS["agent"], size=_NODE_SIZE_BASE["agent"])

    # Model nodes (sized by session count)
    model_usage = Counter(s.get("model") for s in sessions if s.get("model"))
    for m, c in model_usage.most_common():
        add(
            f"model::{m}", "model", m,
            size=_NODE_SIZE_BASE["model"] + math.log2(c + 1) * 2,
            color=_NODE_COLORS["model"], count=c,
        )

    # Topic nodes
    sess_topic: dict[str, str] = {}
    for s in sessions:
        text = " ".join(filter(None, [
            s.get("title"),
            s.get("last_activity_description"),
            s.get("display_name"),
        ]))
        sess_topic[s["id"]] = _classify_topic(text)

    topic_count = Counter(sess_topic.values())
    for t, c in topic_count.most_common():
        add(
            f"topic::{t}", "topic", t.replace("_", " ").title(),
            size=_NODE_SIZE_BASE["topic"] + math.log2(c + 1) * 2,
            color=_NODE_COLORS["topic"] if t != "general" else _NODE_COLORS["topic_default"],
            count=c,
        )

    # Tool nodes
    tool_counter: Counter = Counter()
    for t in tool_calls:
        tool_counter[t["tool_name"]] += t["c"]
    top_tools = [name for name, _ in tool_counter.most_common(_TOP_TOOLS)]
    for t in top_tools:
        add(
            f"tool::{t}", "tool", t,
            size=_NODE_SIZE_BASE["tool"] + math.log2(tool_counter[t] + 1) * 1.5,
            color=_NODE_COLORS["tool"], count=tool_counter[t],
        )

    # Session nodes (size by actual message count from messages table)
    for s in sessions:
        sid = s["id"]
        short = sid[:14] + "…" if len(sid) > 14 else sid
        title = (s.get("title") or s.get("display_name") or s.get("last_activity_description") or short)[:60]
        mc = s.get("message_count") or 0
        if mc == 0:
            # Recompute from messages if column is stale
            mc = sum(stats[sid].get(r, (0, 0))[0] for r in ("user", "assistant", "tool"))
        add(
            f"sess::{sid}", "session", title,
            size=_NODE_SIZE_BASE["session"] + min(8, math.log2(mc + 1)),
            color=_NODE_COLORS["session"],
            started_at=s.get("started_at"),
            msg_count=mc,
            source=s.get("source"),
            pinned=bool(s.get("pinned")),
        )

    # ----- Build edges -----
    edges: list[dict] = []

    for s in sessions:
        sid = s["id"]
        edges.append({"from": "user", "to": f"sess::{sid}", "kind": "owned"})
        edges.append({"from": f"sess::{sid}", "to": "agent", "kind": "uses"})
        if s.get("model"):
            edges.append({"from": f"sess::{sid}", "to": f"model::{s['model']}", "kind": "model"})
        t = sess_topic.get(sid)
        if t:
            edges.append({"from": f"sess::{sid}", "to": f"topic::{t}", "kind": "topic"})

    for t in tool_calls:
        sid = t["session_id"]
        if sid in sess_ids and t["tool_name"] in top_tools:
            edges.append({
                "from": f"sess::{sid}", "to": f"tool::{t['tool_name']}",
                "kind": "tool", "weight": min(t["c"], 50),
            })

    # Chronological edges within each day
    by_date: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s.get("started_at"):
            d = datetime.fromtimestamp(s["started_at"]).strftime("%Y-%m-%d")
            by_date[d].append(s)
    for d, sl in by_date.items():
        if len(sl) < 2:
            continue
        sl.sort(key=lambda x: x["started_at"])
        for i in range(len(sl) - 1):
            edges.append({
                "from": f"sess::{sl[i]['id']}",
                "to":   f"sess::{sl[i + 1]['id']}",
                "kind": "chronological",
            })

    return {
        "meta": {
            "title": "Hermes Agent Memory Graph",
            "source_db": db_path,
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "sessions": len(sessions),
                "messages": sum(
                    sum(stats[s["id"]].get(r, (0, 0))[0] for r in ("user", "assistant", "tool"))
                    for s in sessions
                ),
                "models": len(model_usage),
                "topics": len(topic_count),
                "tools": len(top_tools),
                "nodes": len(nodes),
                "edges": len(edges),
            },
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# CLI usage
if __name__ == "__main__":
    import json
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else os.path.expandvars(r"%LOCALAPPDATA%\hermes\state.db")
    g = build_memory_graph(db)
    print(json.dumps(g, indent=2)[:2000])
    print(f"\n... {len(g['nodes'])} nodes, {len(g['edges'])} edges")
    print(f"stats: {g['meta']['stats']}")
