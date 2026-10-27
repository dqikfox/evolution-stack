#!/usr/bin/env python3
"""Query the second-brain memory graph (ultron-memory.db) with weighted traversal.

The DB holds ~70k relations, most of them weak. Raw edge listing is a hairball,
so every query is a filtered multi-hop traversal from a set of seed memories.

Usage:
  python graph_query.py "port map"                 # hybrid text search, then traverse
  python graph_query.py --seed "PORT MAP" --depth 2 --min-strength 1.0
  python graph_query.py --tag evolution --depth 2
  python graph_query.py --entity THRONE --depth 1
  python graph_query.py --neighbors "NEXUS CORE" --limit 20
  python graph_query.py --stats

Exit codes: 0 ok, 1 error.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB = Path(r"E:\ultron-memory\db\ultron-memory.db")
MAX_SEEDS = 12
MAX_NODES = 400


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise SystemExit(f"graph db missing: {DB}")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_memories(conn: sqlite3.Connection) -> dict:
    mem = {}
    for r in conn.execute("SELECT uuid, content, summary, category, tags, entities, source FROM memories"):
        d = dict(r)
        for col in ("tags", "entities"):
            try:
                d[col] = json.loads(d.get(col) or "[]")
            except Exception:
                d[col] = []
        mem[d["uuid"]] = d
    return mem


def text_seeds(conn, mem, query, limit=8):
    like = f"%{query}%"
    # The SQL LIMIT must not truncate before scoring: the highest-priority rows
    # are often not the ones matching the phrase. Pull a wider candidate set,
    # then rank and cut in Python.
    rows = conn.execute(
        "SELECT uuid FROM memories "
        "WHERE content LIKE ? OR summary LIKE ? "
        "ORDER BY priority DESC, updated_at DESC LIMIT 400",
        (like, like),
    ).fetchall()
    scored = []
    q = query.lower()
    for r in rows:
        m = mem.get(r["uuid"])
        if not m:
            continue
        blob = (m["summary"] or m["content"]).lower()
        score = 0
        if q in blob:
            score += 10
        score += 3 * sum(1 for t in m["tags"] if q == t.lower())
        score += 2 * sum(1 for e in m["entities"] if e.lower() in q)
        score += sum(1 for t in m["tags"] if t.lower() in q) * 2
        scored.append((score, m))
    scored.sort(key=lambda x: (-x[0], x[1]["category"] or ""))
    return [m for s, m in scored[:limit] if s > 0]


def tag_seeds(mem, tag):
    return [m for m in mem.values() if tag in m["tags"]]


def entity_seeds(mem, entity):
    return [m for m in mem.values() if entity in m["entities"]]


def traverse(conn, seeds, depth=2, min_strength=0.0, limit=MAX_NODES):
    """BFS over memory_relations, keeping only edges at or above min_strength."""
    seed_uuids = {m["uuid"] for m in seeds}
    visited = set(seed_uuids)
    frontier = set(seed_uuids)
    edges = []
    for _ in range(max(0, depth)):
        if not frontier or len(visited) >= limit:
            break
        placeholders = ",".join("?" * len(frontier))
        rows = conn.execute(
            f"SELECT source_uuid, target_uuid, relation, strength FROM memory_relations "
            f"WHERE (source_uuid IN ({placeholders}) OR target_uuid IN ({placeholders})) "
            f"AND strength >= ?",
            (*frontier, *frontier, min_strength),
        ).fetchall()
        nxt = set()
        for r in rows:
            a, b, rel, st = r["source_uuid"], r["target_uuid"], r["relation"], r["strength"]
            edges.append((a, b, rel, st))
            for n in (a, b):
                if n not in visited and len(visited) < limit:
                    visited.add(n)
                    nxt.add(n)
        frontier = nxt
    return visited, edges


def summarize(mem, uuids, edges, limit=30):
    out = []
    for u in list(uuids)[:limit]:
        m = mem.get(u)
        if not m:
            continue
        out.append({
            "category": m["category"],
            "source": m["source"],
            "summary": (m["summary"] or m["content"])[:220],
            "tags": m["tags"][:6],
            "entities": m["entities"][:6],
        })
    rel_counts = {}
    for _, _, rel, _ in edges:
        rel_counts[rel] = rel_counts.get(rel, 0) + 1
    return {"nodes": out, "node_count": len(uuids), "edge_count": len(edges),
            "relation_counts": rel_counts}


def cmd_stats(conn, mem, args):
    total_m = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    total_r = conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
    by_rel = conn.execute(
        "SELECT relation, COUNT(*) FROM memory_relations GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    by_cat = conn.execute(
        "SELECT category, COUNT(*) FROM memories GROUP BY 1 ORDER BY 2 DESC LIMIT 12"
    ).fetchall()
    orphan = conn.execute(
        "SELECT COUNT(*) FROM memories m WHERE NOT EXISTS "
        "(SELECT 1 FROM memory_relations r WHERE r.source_uuid=m.uuid OR r.target_uuid=m.uuid)"
    ).fetchone()[0]
    hubs = conn.execute(
        "SELECT COUNT(*) FROM (SELECT source_uuid FROM memory_relations GROUP BY 1 HAVING COUNT(*)>50)"
    ).fetchone()[0]
    print(json.dumps({
        "memories": total_m,
        "relations": total_r,
        "by_relation": {r[0]: r[1] for r in by_rel},
        "top_categories": {c[0]: c[1] for c in by_cat},
        "memories_without_edges": orphan,
        "hubs_over_50_edges": hubs,
    }, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description="Query the THRONE second-brain memory graph")
    p.add_argument("query", nargs="?", help="free-text seed query")
    p.add_argument("--seed", help="seed by category or source")
    p.add_argument("--tag")
    p.add_argument("--entity")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--min-strength", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--neighbors", help="list direct neighbours of a matching memory")
    p.add_argument("--stats", action="store_true")
    args = p.parse_args()

    conn = connect()
    mem = load_memories(conn)
    if args.stats:
        cmd_stats(conn, mem, args)
        return 0

    if args.neighbors:
        seeds = text_seeds(conn, mem, args.neighbors, limit=1)
        if not seeds:
            print(json.dumps({"error": "no match", "query": args.neighbors}))
            return 1
        seed = seeds[0]
        rows = conn.execute(
            "SELECT source_uuid, target_uuid, relation, strength FROM memory_relations "
            "WHERE source_uuid=? OR target_uuid=? ORDER BY strength DESC LIMIT ?",
            (seed["uuid"], seed["uuid"], args.limit),
        ).fetchall()
        out = []
        for r in rows:
            other = r["target_uuid"] if r["source_uuid"] == seed["uuid"] else r["source_uuid"]
            om = mem.get(other)
            out.append({
                "relation": r["relation"],
                "strength": r["strength"],
                "summary": (om["summary"] or om["content"])[:180] if om else "(missing)",
            })
        print(json.dumps({"seed": (seed["summary"] or seed["content"])[:200],
                          "neighbors": out}, indent=2))
        return 0

    seeds = []
    if args.tag:
        seeds = tag_seeds(mem, args.tag)
    elif args.entity:
        seeds = entity_seeds(mem, args.entity)
    elif args.query:
        seeds = text_seeds(conn, mem, args.query, limit=8)
    elif args.seed:
        seeds = [m for m in mem.values()
                 if m["category"] == args.seed or m["source"] == args.seed]
    if not seeds:
        print(json.dumps({"error": "no seeds", "hint": "use a query, --tag, --entity or --seed"}))
        return 1

    seeds = seeds[:MAX_SEEDS]
    uuids, edges = traverse(conn, seeds, depth=args.depth,
                            min_strength=args.min_strength, limit=MAX_NODES)
    payload = summarize(mem, uuids, edges, limit=args.limit)
    payload["seed_count"] = len(seeds)
    payload["depth"] = args.depth
    payload["min_strength"] = args.min_strength
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
