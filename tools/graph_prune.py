#!/usr/bin/env python3
"""Prune weak edges from the second-brain memory graph.

The original relation builder emitted an edge for every pair sharing even ONE
tag. With generic tags like 'ultron', 'rag' and 'memory' on thousands of
rows, that produced 37,404 edges at tag-overlap=2 alone - a hairball where
every node touches every other node and traversal returns noise.

This tool recomputes the true overlap for every edge and keeps only the
edges that actually carry signal:
  * shares_context - needs a real ENTITY overlap (shared named things)
  * shares_entity  - entity overlap, always kept
  * shares_tags    - needs a tag overlap of at least --min-tag-overlap
  * same_source    - always kept (rare and informative)

It also drops edges whose endpoints no longer exist, and reports what it
removed. A backup is taken before any destructive change.

Usage:
  python graph_prune.py --dry-run                    # report only
  python graph_prune.py --min-tag-overlap 3 --apply  # prune for real
  python graph_prune.py --min-tag-overlap 3 --apply --restore-from <db>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(r"E:\ultron-memory\db\ultron-memory.db")
BACKUP_DIR = DB.parent


def load_overlaps(conn):
    mem = {}
    for u, t, e in conn.execute("SELECT uuid, tags, entities FROM memories"):
        try:
            tt = set(json.loads(t or "[]"))
        except Exception:
            tt = set()
        try:
            ee = set(json.loads(e or "[]"))
        except Exception:
            ee = set()
        mem[u] = (tt, ee)
    return mem


def classify(a, b, mem, min_tag_overlap):
    """Return (keep, reason) for the edge between a and b."""
    if a not in mem or b not in mem:
        return False, "dangling"
    ta, ea = mem[a]
    tb, eb = mem[b]
    tag_ov = len(ta & tb)
    ent_ov = len(ea & eb)
    if ent_ov > 0:
        return True, "entity"
    if tag_ov >= min_tag_overlap:
        return True, "tags"
    return False, f"weak(tag_ov={tag_ov},ent_ov={ent_ov})"


def main() -> int:
    p = argparse.ArgumentParser(description="Prune weak edges from the memory graph")
    p.add_argument("--min-tag-overlap", type=int, default=3,
                   help="minimum shared tags for a shares_tags edge to survive (default 3)")
    p.add_argument("--apply", action="store_true", help="actually delete (default is dry run)")
    p.add_argument("--restore-from", help="restore the DB from a backup file and exit")
    args = p.parse_args()

    if args.restore_from:
        src = Path(args.restore_from)
        if not src.exists():
            print(json.dumps({"error": f"backup not found: {src}"}), file=sys.stderr)
            return 1
        stamp = time.strftime("%Y%m%d-%H%M%S")
        keep = DB.with_suffix(f".db.pre-restore-{stamp}")
        shutil.copy2(DB, keep)
        shutil.copy2(src, DB)
        print(json.dumps({"restored_from": str(src), "previous_db": str(keep)}, indent=2))
        return 0

    if not DB.exists():
        print(json.dumps({"error": f"db missing: {DB}"}), file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB))
    mem = load_overlaps(conn)
    edges = conn.execute(
        "SELECT id, source_uuid, target_uuid, relation, strength FROM memory_relations"
    ).fetchall()

    keep_ids, drop_ids, reasons = [], [], {}
    for eid, a, b, rel, strength in edges:
        ok, why = classify(a, b, mem, args.min_tag_overlap)
        if rel == "same_source":
            ok, why = True, "same_source"
        if ok:
            keep_ids.append(eid)
        else:
            drop_ids.append(eid)
            reasons[why] = reasons.get(why, 0) + 1

    report = {
        "total_edges": len(edges),
        "keep": len(keep_ids),
        "drop": len(drop_ids),
        "drop_reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
        "min_tag_overlap": args.min_tag_overlap,
        "applied": False,
    }

    if args.apply and drop_ids:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"ultron-memory.db.bak-preprune-{stamp}"
        shutil.copy2(DB, backup)
        conn.execute("BEGIN")
        chunk = 900
        for i in range(0, len(drop_ids), chunk):
            conn.execute(
                f"DELETE FROM memory_relations WHERE id IN ({','.join('?' * len(drop_ids[i:i + chunk]))})",
                drop_ids[i:i + chunk],
            )
        conn.commit()
        report["applied"] = True
        report["backup"] = str(backup)

    after = conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
    hubs = conn.execute(
        "SELECT COUNT(*) FROM (SELECT source_uuid FROM memory_relations GROUP BY 1 HAVING COUNT(*)>50)"
    ).fetchone()[0]
    orphan = conn.execute(
        "SELECT COUNT(*) FROM memories m WHERE NOT EXISTS "
        "(SELECT 1 FROM memory_relations r WHERE r.source_uuid=m.uuid OR r.target_uuid=m.uuid)"
    ).fetchone()[0]
    report["relations_after"] = after
    report["hubs_over_50_edges_after"] = hubs
    report["memories_without_edges_after"] = orphan
    conn.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
