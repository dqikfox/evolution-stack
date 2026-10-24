#!/usr/bin/env python
"""
shop-bot.py - Telegram storefront bot.
Takes orders, replies with confirmation, logs to orders.jsonl.

Commands:
    /start        - welcome
    /products     - list all 3 products
    /buy <sku>    - initiate order
    /order        - complete current order
    /status       - check order
    /help         - usage
"""
import os
import json
import time
import logging
import secrets
from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import urllib.parse

LOG = Path(r"C:\Users\KING\AppData\Local\hermes\audit\shop-bot.log")
LOG.parent.mkdir(parents=True, exist_ok=True)
ORDERS = Path(r"C:\Users\KING\AppData\Local\hermes\audit\orders.jsonl")
ORDERS.parent.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_SHOP_TOKEN", "")  # from 1Password
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

# Resolve op:// URLs via op CLI
def _resolve_op_url(val: str) -> str:
    """Resolve an op:// URL via the op CLI. Returns the plain value or val unchanged."""
    if not val or not val.startswith("op://"):
        return val
    try:
        import subprocess, tempfile
        tmp = Path(tempfile.gettempdir()) / "op-resolve.tmp"
        r = subprocess.run(
            ["op", "read", "--out-file", str(tmp), val],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and tmp.exists():
            v = tmp.read_text().strip()
            tmp.unlink(missing_ok=True)
            return v
    except Exception as e:
        pass
    return val

BOT_TOKEN = _resolve_op_url(BOT_TOKEN)
ADMIN_CHAT_ID = _resolve_op_url(ADMIN_CHAT_ID)

PRODUCTS = {
    "lum-app": {"name": "The Lummings (web app)", "price": 0, "currency": "USD",
                "desc": "Free kids' AI creative app. Web app, no install needed.",
                "delivery": "https://dqikfox.github.io/lummings/"},
    "lum-pack1": {"name": "The Lummings Premium Asset Pack", "price": 29, "currency": "USD",
                  "desc": "60 SVG portraits, 5 character mood packs, brand guidelines.",
                  "delivery": "digital download"},
    "shiney-free": {"name": "SHInEyVErSE (self-install)", "price": 0, "currency": "USD",
                    "desc": "Free open-source install. Bring your own NVIDIA GPU.",
                    "delivery": "https://github.com/dqikfox/SHinEyVErsE"},
    "shiney-setup": {"name": "SHInEyVErSE Remote Setup", "price": 299, "currency": "USD",
                     "desc": "Done-for-you install by Hitchy + 1h coaching call.",
                     "delivery": "scheduling"},
    "shiney-studio": {"name": "SHInEyVErSE Studio (monthly)", "price": 99, "currency": "USD",
                      "desc": "Monthly subscription: new models, custom prompts, Discord.",
                      "delivery": "subscription"},
    "ultra-mountain": {"name": "Ultra Studio: Mountain Biome Kit", "price": 49, "currency": "USD",
                       "desc": "32 terrain chunks + 18 textures + shaders (Unity/Unreal).",
                       "delivery": "digital download"},
    "ultra-vfx": {"name": "Ultra Studio: Magic VFX Library", "price": 39, "currency": "USD",
                  "desc": "40 particle prefabs + 8 shaders (Unity Shader Graph).",
                  "delivery": "digital download"},
    "ultra-robots": {"name": "Ultra Studio: Robot NPC Pack", "price": 59, "currency": "USD",
                     "desc": "12 rigged characters + 24 animation clips.",
                     "delivery": "digital download"},
    "ultra-mega": {"name": "Ultra Studio: The Mega Bundle", "price": 199, "currency": "USD",
                   "desc": "All 24 packs. Save 60%.",
                   "delivery": "digital download"},
    "ultra-everything": {"name": "Ultra Studio: Everything (lifetime)", "price": 499,
                         "currency": "USD",
                         "desc": "All current + every future pack. Lifetime updates.",
                         "delivery": "digital download"},
    # Free lead magnets (email-capture, no payment)
    "lm-lummings-5pk": {"name": "Free Lummings 5-Portrait Pack", "price": 0,
                        "currency": "USD",
                        "desc": "5 hand-illustrated portraits. Free for commercial use.",
                        "delivery": "https://dqikfox.github.io/lummings/lead-magnet/lummings-5pk/"},
    "lm-shiney-sampler": {"name": "Free SHInEyVErSE Image Sampler", "price": 0,
                          "currency": "USD",
                          "desc": "10 real images from Wan2.2 + Flux + SDXL. Email required.",
                          "delivery": "https://dqikfox.github.io/lummings/lead-magnet/shiney-sampler/"},
    "lm-free-samples": {"name": "Free 10-Asset Starter (CC0)", "price": 0,
                        "currency": "USD",
                        "desc": "5 3D props + 5 AI backgrounds. CC0 license.",
                        "delivery": "https://dqikfox.github.io/lummings/lead-magnet/free-samples/"},
}

# Telegram Bot API
API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None


def send_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """Send message via Telegram Bot API."""
    if not API or not BOT_TOKEN:
        log(f"NO TOKEN: would send to {chat_id}: {text[:100]}")
        return False
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"{API}/sendMessage", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
            return d.get("ok", False)
    except Exception as e:
        log(f"send_message error: {e}")
        return False


def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{ts} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def product_list_text() -> str:
    out = ["🛒 *Hitchy's Shop*\n", "Three products, one forge:\n"]
    out.append("📖 *The Lummings* — kids' AI creative app")
    out.append("   • Free web app · https://dqikfox.github.io/lummings/\n")
    out.append("🦄 *SHInEyVErSE* — AI image & video studio")
    out.append("   • Free / $299 setup / $99/mo")
    out.append("   • https://dqikfox.github.io/lummings/shineyverse/\n")
    out.append("💎 *Ultra Studio* — 3D asset library")
    out.append("   • $19 - $499 per pack or bundle")
    out.append("   • https://dqikfox.github.io/lummings/ultra-studio/\n")
    out.append("Reply with `/buy <sku>` to order, or `/products` for SKU list.")
    return "\n".join(out)


def sku_list_text() -> str:
    out = ["*SKUs & prices:*\n"]
    for sku, p in PRODUCTS.items():
        price = f"${p['price']}" if p['price'] else "FREE"
        out.append(f"`{sku}` — {p['name']} ({price})")
    return "\n".join(out)


def record_order(chat_id: str, sku: str, username: str = "") -> str:
    """Create order ID and log it. Returns order ID."""
    order_id = secrets.token_hex(4).upper()
    order = {
        "id": order_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "username": username,
        "sku": sku,
        "product": PRODUCTS[sku]["name"],
        "price": PRODUCTS[sku]["price"],
        "status": "pending_payment",
    }
    with ORDERS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(order) + "\n")
    log(f"NEW ORDER {order_id} sku={sku} chat={chat_id}")
    return order_id


def handle(chat_id: str, text: str, username: str = "") -> str:
    """Process incoming message. Returns reply text."""
    if not text.startswith("/"):
        return "Type `/start` to begin, `/products` to browse, or `/help` for usage."
    parts = text.strip().split()
    cmd = parts[0].lower()

    if cmd in ("/start", "/help"):
        return ("Welcome to Hitchy's Shop!\n\n"
                "/products — see all 3 storefronts\n"
                "/skus — list every SKU with price\n"
                "/buy <sku> — start an order\n"
                "/status — see your pending orders\n\n"
                "Pay via: dqikst@gmail.com (PayPal / Wise / crypto)")

    if cmd == "/products":
        return product_list_text()

    if cmd == "/skus":
        return sku_list_text()

    if cmd == "/buy":
        if len(parts) < 2:
            return "Usage: `/buy <sku>`. Try `/skus` to see available SKUs."
        sku = parts[1].lower()
        if sku not in PRODUCTS:
            return f"Unknown SKU `{sku}`. Try `/skus` for valid SKUs."
        p = PRODUCTS[sku]
        # Record this order
        order_id = record_order(chat_id, sku, username)
        if p["price"] == 0:
            return (f"✅ *Free order placed*\n\n"
                    f"Order `{order_id}`: {p['name']}\n"
                    f"Access: {p['delivery']}\n\n"
                    f"Thanks for shopping!")
        # Try to get a real Stripe Checkout URL
        stripe_url = None
        try:
            r = urllib.request.Request(
                f"http://127.0.0.1:8522/checkout/{sku}",
                method="POST",
                timeout=8,
            )
            with urllib.request.urlopen(r) as resp:
                d = json.loads(resp.read().decode())
                if not d.get('fallback'):
                    stripe_url = d.get('checkout_url')
        except Exception:
            pass

        if stripe_url:
            return (f"📝 *Order placed*\n\n"
                    f"Order `{order_id}`\n"
                    f"Product: {p['name']}\n"
                    f"Price: ${p['price']} {p['currency']}\n\n"
                    f"💳 *Pay with card (Stripe):*\n"
                    f"{stripe_url}\n\n"
                    f"PayPal fallback: paypal.me/dqikst/{p['price']}\n\n"
                    f"After payment, reply with `/paid {order_id}` and I'll "
                    f"deliver {p['delivery']} within 24h.")
        return (f"📝 *Order placed*\n\n"
                f"Order `{order_id}`\n"
                f"Product: {p['name']}\n"
                f"Price: ${p['price']} {p['currency']}\n\n"
                f"💳 *Pay instantly:*\n"
                f"  • PayPal: https://paypal.me/dqikst/{p['price']}\n"
                f"  • Wise: dqikst@gmail.com (Pay to email)\n\n"
                f"After payment, reply with `/paid {order_id}` and I'll "
                f"deliver {p['delivery']} within 24h.")

    if cmd == "/paid":
        if len(parts) < 2:
            return "Usage: `/paid <order_id>`"
        order_id = parts[1].upper()
        if ADMIN_CHAT_ID:
            send_message(ADMIN_CHAT_ID,
                         f"💰 *Payment claim*\n\nOrder: `{order_id}`\nFrom: {chat_id}\n@username: @{username}\n\nVerify and fulfill.")
        return (f"✅ Payment claim received for `{order_id}`.\n\n"
                f"I'll verify and deliver within 24h. "
                f"Reply here if you need anything.")

    if cmd == "/status":
        # Read user's orders from log
        if not ORDERS.exists():
            return "No orders yet."
        user_orders = []
        for line in ORDERS.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                o = json.loads(line)
                if str(o.get("chat_id")) == str(chat_id):
                    user_orders.append(o)
            except Exception:
                pass
        if not user_orders:
            return "You have no orders. Try `/buy skus-buy`."
        out = [f"*Your orders:* ({len(user_orders)})\n"]
        for o in user_orders[-5:]:
            out.append(f"`{o['id']}` — {o['product']} — {o['status']}")
        return "\n".join(out)

    return f"Unknown command. Try `/help`."


def start_poll_loop():
    """Long-polling loop for incoming Telegram updates."""
    if not API or not BOT_TOKEN:
        log("NO_BOT_TOKEN: set TELEGRAM_SHOP_TOKEN env var to enable")
        return
    log(f"start polling bot={BOT_TOKEN[:10]}...")
    offset = 0
    # Use 30s long-poll (matches Telegram default). We've observed that
    # shorter timeouts (5s, 10s) trigger 409 after a few requests — the
    # bot needs to hold the long-poll slot for the full duration.
    POLL_TIMEOUT = 30
    while True:
        try:
            req = urllib.request.Request(
                f"{API}/getUpdates?timeout={POLL_TIMEOUT}&offset={offset}",
                headers={"Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=POLL_TIMEOUT + 15) as r:
                d = json.loads(r.read().decode())
            for u in d.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                msg = u.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                username = msg.get("from", {}).get("username", "")
                if chat_id and text:
                    reply = handle(str(chat_id), text, username)
                    send_message(str(chat_id), reply)
        except KeyboardInterrupt:
            log("polling stopped")
            return
        except Exception as e:
            log(f"polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Dry-run test
        log("DRY RUN: testing reply logic")
        for cmd in ["/start", "/products", "/skus", "/buy shiney-setup",
                    "/buy lum-app", "/paid ABC123"]:
            print(f"\n>>> {cmd}")
            print(handle("test-chat-id", cmd, "testuser"))
    else:
        start_poll_loop()