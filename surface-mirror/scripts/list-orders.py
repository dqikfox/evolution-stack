#!/usr/bin/env python3
"""list-orders.py - List KRYSYS orders from the local JSON store.

Usage:
    python list-orders.py           all orders
    python list-orders.py payid     only PayID orders
    python list-orders.py unpaid    only unpaid orders
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STORE = Path(r"C:\Users\KING\Projects\krysys-shop\krysys-data\krysys-store.json")

if not STORE.exists():
    print(f"Store not found: {STORE}", file=sys.stderr)
    print("Run the krysys-shop server once to create it.", file=sys.stderr)
    sys.exit(1)

filt = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""

store = json.load(STORE.open())
orders = store.get("krysys_orders", {})
customers = store.get("krysys_customers", {})


def fmt_date(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16]


rows = []
for _oid, o in sorted(orders.items(), key=lambda x: x[1].get("order_date", ""), reverse=True):
    if filt == "payid" and o.get("payment_method") != "payid":
        continue
    if filt == "unpaid" and o.get("payment_status") != "unpaid":
        continue
    rows.append(o)

if not rows:
    msg = "No orders" + (f' matching "{filt}"' if filt else "")
    print(msg)
    sys.exit(0)

print("{:<24} {:<16} {:<12} {:<10} {:>9} {:<10} {:<12}".format(
    "ID", "Date", "Customer", "Pkg", "Total", "Method", "Status"))
print("-" * 100)
for o in rows:
    print("{:<24} {:<16} {:<12} {:<10} ${:>8.2f} {:<10} {:<12}".format(
        o["id"],
        fmt_date(o.get("order_date", "")),
        o.get("codename", "?"),
        o.get("pkg_label", "?"),
        o.get("total_amount", 0),
        o.get("payment_method", "?"),
        o.get("payment_status", "?")))

total = sum(o.get("total_amount", 0) for o in rows if o.get("payment_status") == "paid")
pending = sum(o.get("total_amount", 0) for o in rows if o.get("payment_status") != "paid")
print("-" * 100)
print("{:<70} ${:>8.2f}".format("Total paid:", total))
print("{:<70} ${:>8.2f}".format("Total pending (awaiting confirmation):", pending))
print()
print("To confirm a PayID payment once the customer has sent it:")
print("  1. Verify the funds landed on your bank account (BSB + Acc + ref)")
print("  2. Mark the order paid via the admin dashboard at http://127.0.0.1:8080 (Admin tab)")