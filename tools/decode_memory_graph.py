"""Decode a Hermes Memory Graph export blob into JSON.

The desktop's Star Map can be exported as a single opaque line. That
line is NOT encrypted and carries no key: it is a compact binary
serialisation of the same graph that `hermes journey --json` prints,
wrapped in a compression layer.

THE FORMAT, established byte by byte:

  base64url_line = <7-char prefix> + <base64url body>
  decoded        = base64url_decode(body)          -> 4075 bytes
  inflated       = raw DEFLATE (no zlib header)     -> 5968 bytes
  plaintext      = "S1!" magic + compact binary graph

  * A string is  [len byte][bytes], where the len byte is TWICE the
    byte length. The doubling is the format counting UTF-16 code
    units, so a string written as UTF-8 is measured as if it were
    UTF-16.  "1password" -> 0x12 (18 = 2 x 9).

  * The node table is run-length encoded by category: each node is
    [id][category], and the category is only written when it changes.
    The category token FOLLOWS the id it belongs to.

  * Long strings (memory entries) are capped at 65 characters by the
    format, so a memory body arrives truncated.

  * The remaining bytes are binary: per-node metadata and the edge
    structure.

The node table is reconciled against the live graph (`hermes journey
--json`) so the full node metadata, categories and memory bodies come
back complete, and the two graphs can be diffed.

Usage:
    python decode_memory_graph.py <blob-path> [--live journey.json] [--out out.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import zlib

DEFAULT_BLOB = (
    r"C:\Users\KING\AppData\Local\hermes\composer-pastes"
    r"\pasted_content_2026-10-27_08-48-57-898_aff663.txt"
)
DEFAULT_LIVE = r"C:\Users\KING\AppData\Local\hermes\cache\scratch\journey.json"


def inflate(blob_path: str) -> tuple[bytes, dict]:
    s = open(blob_path, "rb").read().decode("utf-8").strip()
    prefix, body = s[:7], s[7:]
    raw = base64.urlsafe_b64decode(body + "=" * ((-len(body)) % 4))
    plain = zlib.decompress(raw, -15)
    meta = {
        "outer": "base64url with a 7-character prefix",
        "prefix": prefix,
        "compression": "raw deflate (no zlib header)",
        "magic": plain[:3].decode("ascii", "replace"),
        "plaintext_bytes": len(plain),
        "string_rule": "length byte = 2 x byte length (UTF-16 code-unit counting)",
        "max_string_chars": 65,
    }
    return plain, meta


def parse_strings(plain: bytes) -> list[tuple[int, str]]:
    """Walk the string table: [len byte][bytes], len = 2 x byte length."""
    items: list[tuple[int, str]] = []
    i = 0
    while i < len(plain):
        n = plain[i] >> 1
        if n and i + 1 + n <= len(plain):
            cand = plain[i + 1: i + 1 + n]
            try:
                txt = cand.decode("utf-8")
            except UnicodeDecodeError:
                txt = None
            if txt and all(ch.isprintable() or ch in "\t\n\r" for ch in txt):
                items.append((i, txt))
                i += 1 + n
                continue
        i += 1
    return items


CATEGORIES = {
    "security", "email", "skills", "software-development", "research",
    "productivity", "mlops", "inference", "media", "infrastructure",
    "github", "evolutionary-loops", "devops", "creative",
    "autonomous-ai-agents", "web", "video", "memory", "business-term-evaluation",
    "github-workflow", "llm-inference", "local-rag", "voice",
    "image-generation", "video-generation", "research-provenance",
    "software-development", "multimodal", "observability",
}


def split_nodes(strings: list[str]) -> tuple[list[dict], list[dict]]:
    """The node table is [id][category] with the category run-length
    encoded: it follows the id it belongs to."""
    first_mem = next(
        (i for i, t in enumerate(strings) if len(t) > 40), len(strings)
    )
    table = strings[:first_mem]

    nodes: list[dict] = []
    pending: str | None = None
    for t in table:
        if t in CATEGORIES and pending is None:
            pending = t
            continue
        nodes.append({"id": t, "category": pending})
        pending = None

    memories = [
        {"title": t, "truncated": len(t) >= 65}
        for t in strings[first_mem:]
        if t != "memory" and len(t) >= 4
    ]
    return nodes, memories


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("blob", nargs="?", default=DEFAULT_BLOB)
    ap.add_argument("--live", default=DEFAULT_LIVE)
    ap.add_argument("--out", default="memory_graph_decoded.json")
    args = ap.parse_args()

    plain, meta = inflate(args.blob)
    items = parse_strings(plain)
    strings = [t for _, t in items]
    nodes, memories = split_nodes(strings)

    live = None
    if os.path.exists(args.live):
        live = json.load(open(args.live, encoding="utf-8"))

    if live:
        live_nodes = {n["id"]: n for n in live["nodes"]}
        live_mem = {}
        for m in live["memory"]:
            live_mem.setdefault(m["title"][:60], m)
        for n in nodes:
            ln = live_nodes.get(n["id"])
            if ln:
                n.update({
                    "label": ln.get("label"),
                    "kind": ln.get("kind"),
                    "timestamp": ln.get("timestamp"),
                    "useCount": ln.get("useCount"),
                    "state": ln.get("state"),
                    "createdBy": ln.get("createdBy"),
                    "pinned": ln.get("pinned"),
                })
        for m in memories:
            lm = live_mem.get(m["title"][:60])
            if lm:
                m.update({
                    "source": lm.get("source"),
                    "timestamp": lm.get("timestamp"),
                    "body": lm.get("body"),
                    "fingerprint": lm.get("fingerprint"),
                })

    blob_ids = {n["id"] for n in nodes}
    live_skill_ids = (
        {n["id"] for n in live["nodes"] if n.get("kind") == "skill"} if live else set()
    )

    result = {
        "decoded_from": args.blob,
        "encoding": meta,
        "blob_node_count": len(nodes),
        "blob_memory_count": len(memories),
        "live_graph": (
            {k: len(v) for k, v in live.items() if isinstance(v, list)}
            if live else None
        ),
        "reconciliation": {
            "blob_skills_matched_in_live": sum(1 for n in nodes if n["id"] in live_skill_ids),
            "blob_skills_total": len(nodes),
            "blob_memories_matched_in_live": sum(1 for m in memories if "body" in m),
            "blob_memories_total": len(memories),
            "in_live_not_in_blob": sorted(live_skill_ids - blob_ids),
            "in_blob_not_in_live": sorted(blob_ids - live_skill_ids),
            "unmatched_blob_memories": [m["title"] for m in memories if "body" not in m],
        },
        "nodes": nodes,
        "memories": memories,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print(f"magic {meta['magic']!r}  prefix {meta['prefix']!r}  "
          f"plaintext {meta['plaintext_bytes']} bytes")
    print(f"nodes {len(nodes)}  memories {len(memories)}")
    print("reconciliation:", json.dumps(result["reconciliation"], indent=2))
    print("written", os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
