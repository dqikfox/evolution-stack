#!/usr/bin/env python
"""
memory-promoter.py - Scan USER.md / MEMORY.md for stale entries; report TTL.
Flags entries older than their last verified date. Does NOT auto-edit;
outputs a report for human or agent review.
"""
import sys, os, re, json, argparse
from pathlib import Path
from datetime import datetime, timedelta

_DEF_USER = r"C:\Users\KING\AppData\Local\hermes\memories\USER.md"
_DEF_MEM = r"C:\Users\KING\AppData\Local\hermes\memories\MEMORY.md"
USER_MD = Path(os.environ.get("USER_MD", _DEF_USER))
MEMORY_MD = Path(os.environ.get("MEMORY_MD", _DEF_MEM))

NOW = datetime.utcnow()
STALE_30 = NOW - timedelta(days=30)
STALE_60 = NOW - timedelta(days=60)
STALE_90 = NOW - timedelta(days=90)


def parse_entries(text: str):
    """Split memory text into entries by § separator. Return list of (header, body, mtime)."""
    out = []
    sections = re.split(r"\n§\n", text)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        # First line is the entry header (no leading bullet)
        lines = sec.splitlines()
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        # Try to find YYYY-MM-DD
        m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", sec)
        last_verified = None
        if m:
            try:
                last_verified = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        out.append({"header": header, "body": body, "verified": last_verified.isoformat() if last_verified else None})
    return out


def classify(entry: dict) -> str:
    if not entry["verified"]:
        return "no-date"
    try:
        v = datetime.fromisoformat(entry["verified"])
    except ValueError:
        return "no-date"
    if v >= STALE_30:
        return "fresh"
    if v >= STALE_60:
        return "stale-30d"
    if v >= STALE_90:
        return "stale-60d"
    return "stale-90d+"


def scan(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False, "entries": []}
    text = path.read_text(encoding="utf-8", errors="ignore")
    entries = parse_entries(text)
    counts = {"fresh": 0, "stale-30d": 0, "stale-60d": 0, "stale-90d+": 0, "no-date": 0}
    for e in entries:
        counts[classify(e)] += 1
    return {
        "path": str(path),
        "exists": True,
        "size_kb": path.stat().st_size // 1024,
        "entries": len(entries),
        "counts": counts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = {
        "ts": NOW.isoformat() + "Z",
        "user": scan(USER_MD),
        "memory": scan(MEMORY_MD),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"=== MEMORY HYGIENE {report['ts']} ===\n")
    for label, data in [("USER.md", report["user"]), ("MEMORY.md", report["memory"])]:
        if not data["exists"]:
            print(f"{label}: NOT FOUND at {data['path']}")
            continue
        c = data["counts"]
        print(f"{label} ({data['size_kb']} KB, {data['entries']} entries):")
        print(f"  fresh       {c['fresh']:>3}")
        print(f"  stale-30d   {c['stale-30d']:>3}  <- verify")
        print(f"  stale-60d   {c['stale-60d']:>3}  <- promote to skill or delete")
        print(f"  stale-90d+  {c['stale-90d+']:>3}  <- delete unless core identity")
        print(f"  no-date     {c['no-date']:>3}  <- add verified-date")
    return 0


if __name__ == "__main__":
    sys.exit(main())