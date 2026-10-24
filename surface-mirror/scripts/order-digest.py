#!/usr/bin/env python
"""
order-digest.py - Daily summary of shop orders posted to Notion DB.
Reads orders.jsonl, summarizes, writes to Notion diary DB.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile

ORDERS = Path(r"C:\Users\KING\AppData\Local\hermes\audit\orders.jsonl")
NOTION_DB = "op://credentials/NOTION_DIARY_DB/credential"  # database ID

# Load Notion token + DB id
def load_secret(ref: str) -> str:
    tmp = Path(tempfile.gettempdir()) / f"sec-{os.urandom(4).hex()}.tmp"
    r = subprocess.run(["op", "read", "--out-file", str(tmp), ref],
                       capture_output=True, text=True, timeout=15)
    if r.returncode == 0:
        v = tmp.read_text().strip()
        tmp.unlink(missing_ok=True)
        return v
    raise RuntimeError(f"op read failed: {r.stderr}")


def summarize_today() -> dict:
    """Aggregate today's orders from JSONL."""
    today = datetime.now(timezone.utc).date().isoformat()
    items = []
    revenue = 0.0
    if not ORDERS.exists():
        return {"date": today, "count": 0, "revenue": 0.0, "items": []}
    for line in ORDERS.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("ts", "").startswith(today):
            items.append(o)
            revenue += float(o.get("price", 0))
    return {"date": today, "count": len(items), "revenue": revenue, "items": items}


def post_to_notion(summary: dict) -> bool:
    """Append a diary entry summarizing today's orders."""
    try:
        notion_token = load_secret("op://credentials/NOTION_TOKEN/credential")
        db_id = load_secret("op://credentials/NOTION_DIARY_DB/credential")
    except Exception as e:
        print(f"NOTE: Notion creds unavailable: {e}")
        return False

    if summary["count"] == 0:
        body = f"🛒 Shop digest {summary['date']}\n\nNo orders today."
    else:
        body_lines = [
            f"🛒 Shop digest {summary['date']}",
            "",
            f"Orders: {summary['count']}",
            f"Revenue: ${summary['revenue']:.2f}",
            "",
            "Items:",
        ]
        for o in summary["items"]:
            body_lines.append(
                f"  • {o['id']} — {o['product']} — ${o['price']} — {o['status']}"
            )
        body = "\n".join(body_lines)

    # Notion API: append block to a page. We don't have a parent page ID,
    # so use the DB and create a new row.
    payload = json.dumps({
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {
                "title": [{"text": {"content": f"Shop digest {summary['date']}"}}],
            },
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": body}}],
                },
            },
        ],
    }).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=payload,
        headers={
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
        return d.get("object") == "page"
    except Exception as e:
        print(f"Notion post error: {e}")
        return False


if __name__ == "__main__":
    summary = summarize_today()
    print(f"Digest: {summary['date']} — {summary['count']} orders, ${summary['revenue']:.2f}")
    if "--post" in sys.argv:
        ok = post_to_notion(summary)
        print(f"Posted to Notion: {ok}")
        sys.exit(0 if ok else 1)
    else:
        print(json.dumps(summary, indent=2))