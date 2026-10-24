#!/usr/bin/env python
"""
shop-launcher.py - Run shop-bot with token from 1Password.
This is the entry point that the cron / start.cmd uses.

Usage:
    python shop-launcher.py            # start polling
    python shop-launcher.py --send <chat_id> <text>   # one-shot send
"""
import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Ensure the scripts dir is on sys.path so 'import shop_bot' works
# regardless of cwd.
SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Load token from 1Password at runtime.
# Use DROID (@droid420bot) by default — Ultron420bot token has been rate-limited
# by Telegram (returns 409 on long-polls after rapid restarts).
# Override with SHOP_BOT_TOKEN_REF env var to use a different bot.
TOKEN_REF = os.environ.get(
    "SHOP_BOT_TOKEN_REF",
    "op://credentials/TELEGRAM_BOT_TOKEN_DROID/credential",
)


def load_token() -> str:
    tmp = Path(tempfile.gettempdir()) / "shop-token.tmp"
    try:
        r = subprocess.run(
            ["op", "read", "--out-file", str(tmp), TOKEN_REF],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and tmp.exists():
            token = tmp.read_text().strip()
            tmp.unlink()
            return token
        raise RuntimeError(f"op read failed: {r.stderr}")
    except Exception as e:
        print(f"FAIL: could not load token: {e}", file=sys.stderr)
        sys.exit(2)


def main():
    token = load_token()
    os.environ["TELEGRAM_SHOP_TOKEN"] = token

    if len(sys.argv) >= 3 and sys.argv[1] == "--send":
        sys.path.insert(0, str(Path(__file__).parent))
        import shop_bot
        chat_id = sys.argv[2]
        text = " ".join(sys.argv[3:])
        ok = shop_bot.send_message(chat_id, text)
        print(f"send: ok={ok}")
        sys.exit(0 if ok else 1)

    # Default: start polling
    sys.path.insert(0, str(Path(__file__).parent))
    import shop_bot
    shop_bot.start_poll_loop()


if __name__ == "__main__":
    main()