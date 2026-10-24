"""DGM-style archive: every proposed variant, its lineage, its score, its fate.

The archive is the memory the old evolution scripts never had. It answers:
  - what did we try?
  - did it work?
  - which parent produced the current best?
  - what is the current best proposer prompt / skill version?
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import paths


def _connect() -> sqlite3.Connection:
    paths.ensure_dirs()
    conn = sqlite3.connect(paths.ARCHIVE_DB, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
    with _connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                kind TEXT NOT NULL DEFAULT 'patch',
                target TEXT NOT NULL,
                summary TEXT NOT NULL,
                diff TEXT,
                score_before REAL,
                score_after REAL,
                status TEXT NOT NULL DEFAULT 'proposed',
                ts REAL NOT NULL,
                meta TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                score REAL NOT NULL,
                checks INTEGER NOT NULL,
                failures INTEGER NOT NULL,
                detail TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_variants_status ON variants(status);
            CREATE INDEX IF NOT EXISTS ix_variants_ts ON variants(ts DESC);
            """
        )


def log_event(kind: str, message: str, **data) -> None:
    with _connect() as c:
        c.execute(
            "INSERT INTO events (ts, kind, message, data) VALUES (?,?,?,?)",
            (time.time(), kind, message, json.dumps(data, default=str)),
        )


def record_benchmark(score: float, checks: int, failures: int, detail: dict) -> int:
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO benchmarks (ts, score, checks, failures, detail) VALUES (?,?,?,?,?)",
            (time.time(), score, checks, failures, json.dumps(detail, default=str)),
        )
        return int(cur.lastrowid)


def add_variant(
    target: str,
    summary: str,
    diff: str = "",
    parent_id: int | None = None,
    kind: str = "patch",
    score_before: float | None = None,
    score_after: float | None = None,
    status: str = "proposed",
    **meta,
) -> int:
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO variants (parent_id, kind, target, summary, diff, score_before,"
            " score_after, status, ts, meta) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (parent_id, kind, target, summary, diff, score_before, score_after,
             status, time.time(), json.dumps(meta, default=str)),
        )
        vid = int(cur.lastrowid)
    log_event("variant", f"proposed #{vid} -> {target}", variant_id=vid, summary=summary)
    return vid


def set_status(variant_id: int, status: str, score_after: float | None = None) -> None:
    with _connect() as c:
        if score_after is None:
            c.execute("UPDATE variants SET status=? WHERE id=?", (status, variant_id))
        else:
            c.execute(
                "UPDATE variants SET status=?, score_after=? WHERE id=?",
                (status, score_after, variant_id),
            )
    log_event("variant", f"#{variant_id} -> {status}", variant_id=variant_id, score=score_after)


def get_variant(variant_id: int) -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM variants WHERE id=?", (variant_id,)).fetchone()
    return dict(row) if row else None


def best_variant(target: str | None = None) -> dict | None:
    q = "SELECT * FROM variants WHERE status='accepted'"
    args: tuple = ()
    if target:
        q += " AND target=?"
        args = (target,)
    q += " ORDER BY score_after DESC, ts DESC LIMIT 1"
    with _connect() as c:
        row = c.execute(q, args).fetchone()
    return dict(row) if row else None


def history(limit: int = 50) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, parent_id, kind, target, summary, score_before, score_after, status, ts"
            " FROM variants ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def latest_benchmark() -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM benchmarks ORDER BY ts DESC LIMIT 1").fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["detail"] = json.loads(d["detail"])
    except Exception:
        pass
    return d


def benchmark_history(limit: int = 30) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT ts, score, checks, failures FROM benchmarks ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with _connect() as c:
        total = c.execute("SELECT COUNT(*) FROM variants").fetchone()[0]
        accepted = c.execute(
            "SELECT COUNT(*) FROM variants WHERE status='accepted'").fetchone()[0]
        rejected = c.execute(
            "SELECT COUNT(*) FROM variants WHERE status='rejected'").fetchone()[0]
        best = c.execute(
            "SELECT MAX(score_after) FROM variants WHERE status='accepted'").fetchone()[0]
    return {
        "variants": total,
        "accepted": accepted,
        "rejected": rejected,
        "best_score": best,
        "archive_db": str(paths.ARCHIVE_DB),
    }
