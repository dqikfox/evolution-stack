#!/usr/bin/env python
"""Send a Telegram alert to the operator when monitored services go down."""
import sys, subprocess, json, os
from pathlib import Path

# Bot token from .env or 1Password
ENV_PATH = Path(r"C:\Users\KING\AppData\Local\hermes\.env")
bot_token = ""
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line: continue
        key, _, val = line.partition("=")
        if key.strip() == "TELEGRAM_BOT_TOKEN":
            bot_token = val.strip().strip('"').strip("'")
            break

if not bot_token:
    # Try 1Password
    try:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "tg-token.tmp"
        r = subprocess.run(
            ["op", "read", "--out-file", str(tmp),
             "op://credentials/TELEGRAM_BOT_TOKEN/credential"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and tmp.exists():
            bot_token = tmp.read_text().strip()
            tmp.unlink(missing_ok=True)
    except Exception as e:
        pass

# Chat ID (your personal ID, hardcoded or from env)
chat_id = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID", "")
if not chat_id:
    try:
        # First chat_id from the bot's recent users - auto-detect
        import urllib.request
        req = urllib.request.Request(f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=5")
        with urllib.request.urlopen(req, timeout=5) as r:
            updates = json.loads(r.read().decode())
        if updates.get("result"):
            chat_id = str(updates["result"][-1]["message"]["chat"]["id"])
    except Exception as e:
        pass

if not bot_token or not chat_id:
    print(f"telegram_alert: no bot_token or chat_id", file=sys.stderr)
    sys.exit(1)

msg = " ".join(sys.argv[1:]) or "(no message)"
try:
    import urllib.request, urllib.parse
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": f"⚠️ {msg}"}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as r:
        pass
    print(f"alert sent: {msg[:50]}")
except Exception as e:
    print(f"alert error: {e}", file=sys.stderr)
    sys.exit(1)