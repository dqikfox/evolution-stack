#!/usr/bin/env python
"""manual_outreach.py - Generate a follow-up email body for each captured lead/sale.

Reads /leads and /subscribers, generates an email body you can paste into Gmail.
Doesn't actually send anything — that's manual, but it gives you the right copy for each.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

LEADS = Path(r"C:\Users\KING\AppData\Local\hermes\audit\leads.jsonl")
SUBS = Path(r"C:\Users\KING\AppData\Local\hermes\audit\subscribers.jsonl")

def load_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try: out.append(json.loads(line))
        except: pass
    return out

def email_for(entry, kind):
    email = entry.get("email", "")
    ts = entry.get("ts", "")
    intent = entry.get("intent", "")
    sku = entry.get("sku", "")
    product = entry.get("product", "")
    source = entry.get("source", "")

    if kind == "lead":
        subject = f"Your free {product}"
        body = f"""Hi,

Thanks for grabbing the free {product}.

Here's the download link: https://dqikfox.github.io/lummings/lead-magnet/{sku.replace('lm-', '')}/

If you want the full paid version, the {product.split('Free ')[-1]} is available with payment options at https://dqikfox.github.io/lummings/shop/

Reply if anything's wrong.

— The Indie Forge
"""
    elif kind == "subscriber":
        subject = "Welcome — here's what's coming"
        body = f"""Hi,

Thanks for subscribing. You'll get a short build log once a month with what's shipping, what broke, and what's free.

For now:
- Try the Lummings (free, no signup): https://dqikfox.github.io/lummings/
- Grab a free starter pack: https://dqikfox.github.io/lummings/lead-magnet/

If you'd like to support, buy something from the shop: https://dqikfox.github.io/lummings/shop/

Reply if anything's wrong.

— The Indie Forge
"""
    else:
        subject = "Following up"
        body = f"Hi,\n\nYou expressed interest. Anything I can answer?\n\n— The Indie Forge\n"

    return {"to": email, "subject": subject, "body": body, "kind": kind,
            "ts": ts, "source": source, "sku": sku}

print("=" * 70)
print("MANUAL OUTREACH - emails to send")
print("=" * 70)
print("Copy each 'TO:' line and 'SUBJECT:' into a new email, paste BODY.")
print("All emails come from dqikst@gmail.com (manual send).")
print("=" * 70)

print("\n# FREE LEAD CAPTURES (most recent first)")
for entry in reversed(load_jsonl(LEADS)):
    e = email_for(entry, "lead")
    print(f"\n--- TO: {e['to']}  ({e['ts']})  sku={e['sku']} source={e['source']} ---")
    print(f"SUBJECT: {e['subject']}")
    print(f"\n{e['body']}")

print("\n\n# NEWSLETTER SUBSCRIBERS (most recent first)")
for entry in reversed(load_jsonl(SUBS)):
    if not entry.get("intent", "").startswith("lead-magnet:"):
        e = email_for(entry, "subscriber")
        print(f"\n--- TO: {e['to']}  ({e['ts']})  intent={e['intent']} source={e['source']} ---")
        print(f"SUBJECT: {e['subject']}")
        print(f"\n{e['body']}")

print(f"\n{'='*70}")
print(f"Totals: {len(load_jsonl(LEADS))} leads, {len(load_jsonl(SUBS))} subscribers")
print(f"Manual send time: ~30s per email if you batch them in Gmail")
print(f"{'='*70}")