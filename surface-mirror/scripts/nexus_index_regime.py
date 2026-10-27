#!/usr/bin/env python
"""Is the vector index in the CURRENT chunking regime?

WHY THIS EXISTS
---------------
A rebuild has two modes and they are not interchangeable.

FRESH drops the collection and rebuilds it from zero. It is correct
when the CHUNKING POLICY has changed: the old vector ids (a bare note
id) and the new ones (a note id plus a chunk number) are different
strings, so an incremental run over a policy-changed index leaves the
old vectors behind as orphans that still match queries - a corpus
that answers with the old policy's chunks forever.

RESUME keeps what is there and adds what is missing. It is correct
when the policy has NOT changed, and it is enormously cheaper: on
2026-10-28 the corpus held 2,805 notes and the index covered 2,503 of
them, so a resume had 4,243 vectors to build while a fresh had
20,561 - and a fresh would have thrown away 16,318 vectors that were
already correct.

So the question is not "how many notes are missing" but "does the
index contain any vector the current policy would not produce". An
orphan is the proof that the policy has moved.

Exit codes
----------
  0  no orphans - the index is in the current regime. RESUME is safe.
  1  orphans exist - the policy has changed. FRESH is required.
  2  the check could not be made - the caller must decide for itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_PROJECT = Path(r"E:\ultron-memory\nexus-core")


def main(argv: list[str]) -> int:
    project = Path(argv[1]) if len(argv) > 1 else DEFAULT_PROJECT
    sys.path.insert(0, str(project))

    try:
        import chromadb

        from core.chunking import chunk_note as _chunk
        from core.search import _chunk_ids as _ids_for
    except Exception as exc:  # noqa: BLE001
        print(f"[reindex] could not load the chunking policy: {exc}", file=sys.stderr)
        return 2

    chroma_dir = project / "data" / "chroma"
    db_path = project / "data" / "nexus.db"
    if not chroma_dir.is_dir() or not db_path.is_file():
        print(f"[reindex] no index at {chroma_dir} or no database at {db_path}",
              file=sys.stderr)
        return 2

    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        col = client.get_collection("nexus")
        have: set[str] = set()
        offset = 0
        while True:
            got = col.get(include=[], limit=20000, offset=offset)
            ids = got.get("ids") or []
            have.update(ids)
            offset += len(ids)
            if len(ids) < 20000:
                break
    except Exception as exc:  # noqa: BLE001
        print(f"[reindex] could not read the index: {exc}", file=sys.stderr)
        return 2

    import sqlite3

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT id, body FROM notes").fetchall()
        expected: set[str] = set()
        for row in rows:
            chunks = _chunk(row["body"] or "")
            if not chunks:
                continue
            expected.update(_ids_for(row["id"], len(chunks)))
    finally:
        con.close()

    orphans = have - expected
    missing = expected - have
    report = {
        "vectors": len(have),
        "expected": len(expected),
        "orphans": len(orphans),
        "missing": len(missing),
        "regime": "stale" if orphans else "current",
    }
    print(json.dumps(report))

    if orphans:
        sample = sorted(orphans)[:5]
        print(f"[reindex] {len(orphans)} orphan vectors - the chunking policy "
              f"has changed, so a FRESH rebuild is required.")
        print(f"[reindex]   sample: {sample}")
        return 1

    print(f"[reindex] no orphans: the index is in the current chunking regime.")
    print(f"[reindex]   {len(missing)} vectors still wanted, {len(have)} present.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
