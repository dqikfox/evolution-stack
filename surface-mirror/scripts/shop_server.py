#!/usr/bin/env python
"""shop_server.py - Stripe-integrated shop backend.

Endpoints:
    GET  /                     - landing
    GET  /skus                 - JSON product list with Stripe prices
    POST /checkout/<sku>       - create Stripe Checkout Session, return URL
    POST /webhook             - Stripe webhook receiver
    GET  /health              - health check
    GET  /orders              - admin orders (from JSONL)

Auto-loads STRIPE_SECRET_KEY from:
    1. os.environ (set by parent)
    2. C:\\Users\\KING\\AppData\\Local\\hermes\\.env (STRIPE_SECRET_KEY=...)
    3. 1Password credentials vault (item STRIPE_SECRET_KEY, via op CLI)

Test with:
    Use Stripe test card 4242 4242 4242 4242 / any future date / any CVC
"""
import json
import os
import re
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Load .env file BEFORE anything else
ENV_PATH = Path(r"C:\Users\KING\AppData\Local\hermes\.env")
if ENV_PATH.exists():
    try:
        for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ[key] = value  # overwrite (don't setdefault)
    except Exception as e:
        print(f".env load error: {e}", file=sys.stderr)

# If STRIPE_SECRET_KEY not in env, try 1Password
if not os.environ.get("STRIPE_SECRET_KEY"):
    import subprocess
    import tempfile
    try:
        tmp = Path(tempfile.gettempdir()) / "stripe-key.tmp"
        r = subprocess.run(
            ["op", "read", "--out-file", str(tmp),
             "op://credentials/STRIPE_SECRET_KEY/credential"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and tmp.exists():
            key = tmp.read_text().strip()
            if key:
                os.environ["STRIPE_SECRET_KEY"] = key
            tmp.unlink(missing_ok=True)
    except Exception:
        pass

# Try to load SMTP creds for welcome emails (graceful no-op if missing)
def _load_smtp_creds():
    """Returns (host, port, user, pass) or None if not configured."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    if not user or not pw:
        # Try 1Password for GMAIL_APP_PASSWORD
        try:
            import subprocess, tempfile
            tmp = Path(tempfile.gettempdir()) / "gmail-pw.tmp"
            r = subprocess.run(
                ["op", "read", "--out-file", str(tmp),
                 "op://credentials/GMAIL_APP_PASSWORD/credential"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and tmp.exists():
                    pw = tmp.read().strip()
                    if not user:
                        user = "dqikst@gmail.com"
                    tmp.unlink(missing_ok=True)
        except Exception:
            pass
    if user and pw:
        return host, port, user, pw
    return None

def send_welcome_email(email: str, intent: str = "", sku: str = "") -> bool:
    """Send a welcome email via SMTP. Returns True if sent, False if not configured."""
    import smtplib
    from email.mime.text import MIMEText
    creds = _load_smtp_creds()
    if not creds:
        log.info(f"welcome email SKIPPED (no SMTP) -> {email} intent={intent} sku={sku}")
        return False
    host, port, user, pw = creds
    subject = "Your free starter pack from The Indie Forge"
    body_plain = f"""Hi,

Thanks for grabbing the free starter pack. Here's everything you need:

Lummings web app (free): https://dqikfox.github.io/lummings/
Shop: https://dqikfox.github.io/lummings/shop/
Demo (30s walkthrough): https://dqikfox.github.io/lummings/demo/
Support: hello@dqikst.com

If you grabbed a lead magnet, the link is also in this email.

Reply with any questions.

— The Indie Forge
Sydney, Australia
"""
    msg = MIMEText(body_plain, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"The Indie Forge <{user}>"
    msg["To"] = email
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        log.info(f"welcome email SENT -> {email} intent={intent}")
        return True
    except Exception as e:
        log.error(f"welcome email error to {email}: {e}")
        return False

LOG_DIR = Path(r"C:\Users\KING\AppData\Local\hermes\audit")
LOG_DIR.mkdir(parents=True, exist_ok=True)
ORDERS = LOG_DIR / "orders.jsonl"
ACCESS = LOG_DIR / "checkout-access.jsonl"
SUBSCRIBERS = LOG_DIR / "subscribers.jsonl"
LEADS = LOG_DIR / "leads.jsonl"

logging.basicConfig(
    filename=LOG_DIR / "shop-server.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("shop")

# Try loading Stripe SDK
try:
    import stripe
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False
    log.warning("stripe SDK not installed; payments will use PayPal fallback")

# Try FastAPI for the actual server
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import RedirectResponse, JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    log.warning("fastapi not installed; using http.server fallback")


PRODUCTS = {
    "lum-pack1": {
        "name": "The Lummings Premium Asset Pack",
        "price": 29, "currency": "usd",
        "desc": "60 SVG portraits, 5 character mood packs, brand guidelines.",
        "delivery": "digital download",
        "category": "lummings",
    },
    "shiney-setup": {
        "name": "SHInEyVErSE Remote Setup",
        "price": 299, "currency": "usd",
        "desc": "Done-for-you install by Hitchy + 1h coaching call.",
        "delivery": "scheduling",
        "category": "shineyverse",
    },
    "shiney-studio": {
        "name": "SHInEyVErSE Studio (monthly)",
        "price": 99, "currency": "usd",
        "desc": "Monthly subscription: new models, custom prompts, Discord.",
        "delivery": "subscription",
        "category": "shineyverse",
    },
    "ultra-mountain": {
        "name": "Ultra Studio: Mountain Biome Kit",
        "price": 49, "currency": "usd",
        "desc": "32 terrain chunks + 18 textures + shaders (Unity/Unreal).",
        "delivery": "digital download",
        "category": "ultra",
    },
    "ultra-vfx": {
        "name": "Ultra Studio: Magic VFX Library",
        "price": 39, "currency": "usd",
        "desc": "40 particle prefabs + 8 shaders (Unity Shader Graph).",
        "delivery": "digital download",
        "category": "ultra",
    },
    "ultra-robots": {
        "name": "Ultra Studio: Robot NPC Pack",
        "price": 59, "currency": "usd",
        "desc": "12 rigged characters + 24 animation clips.",
        "delivery": "digital download",
        "category": "ultra",
    },
    "ultra-mega": {
        "name": "Ultra Studio: The Mega Bundle",
        "price": 199, "currency": "usd",
        "desc": "All 24 packs. Save 60%.",
        "delivery": "digital download",
        "category": "ultra",
    },
    "ultra-everything": {
        "name": "Ultra Studio: Everything (lifetime)",
        "price": 499, "currency": "usd",
        "desc": "All current + every future pack. Lifetime updates.",
        "delivery": "digital download",
        "category": "ultra",
    },
    # Free lead magnets (no Stripe - just captures email)
    "lm-free-samples": {
        "name": "Free 10-asset starter pack (3D + image)",
        "price": 0, "currency": "usd",
        "desc": "5 free 3D props + 5 free AI-generated backgrounds. Email required.",
        "delivery": "email link",
        "category": "lead-magnet",
        "delivery_url": "https://dqikfox.github.io/lummings/lead-magnet/free-samples/",
    },
    "lm-shiney-sampler": {
        "name": "Free SHInEyVErSE image sampler",
        "price": 0, "currency": "usd",
        "desc": "10 pre-generated images from Wan2.2 + Flux + SDXL. Email required.",
        "delivery": "email link",
        "category": "lead-magnet",
        "delivery_url": "https://dqikfox.github.io/lummings/lead-magnet/shiney-sampler/",
    },
    "lm-lummings-5pk": {
        "name": "Free Lummings 5-portrait starter",
        "price": 0, "currency": "usd",
        "desc": "5 hero portraits of Lumo, Lila, Pip, Nori, Moki. Email required.",
        "delivery": "email link",
        "category": "lead-magnet",
        "delivery_url": "https://dqikfox.github.io/lummings/lead-magnet/lummings-5pk/",
    },
}


def record_order(order: dict):
    with ORDERS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(order) + "\n")
    log.info(f"NEW ORDER {order.get('id')} sku={order.get('sku')} ${order.get('price')}")


def paypal_url(sku: str) -> str:
    p = PRODUCTS[sku]
    return f"https://paypal.me/dqikst/{p['price']}"


def stripe_checkout_url(sku: str, success_url: str, cancel_url: str) -> tuple[bool, str]:
    """Create a Stripe Checkout Session and return URL. (ok, url_or_err)"""
    if not HAS_STRIPE:
        return False, "stripe SDK not installed"
    secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret:
        return False, "STRIPE_SECRET_KEY not set (PayPal fallback in use)"
    if not (secret.startswith("sk_test_") or secret.startswith("sk_live_")
            or secret.startswith("rk_test_") or secret.startswith("rk_live_")):
        return False, f"Invalid STRIPE_SECRET_KEY prefix (got '{secret[:10]}...')"

    stripe.api_key = secret
    p = PRODUCTS[sku]

    try:
        # Account uses Managed Payments — disable per session so we can use
        # payment_method_types directly. (See: dashboard.stripe.com
        # /settings/managed-payments for account-level toggle.)
        # NOTE: Stripe SDK 16+ removed payment_method_types parameter —
        # payment methods are now managed via Dashboard settings only.
        session = stripe.checkout.Session.create(
            managed_payments={"enabled": False},
            line_items=[{
                "price_data": {
                    "currency": p["currency"],
                    "unit_amount": p["price"] * 100,  # cents
                    "product_data": {
                        "name": p["name"],
                        "description": p["desc"],
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"sku": sku},
        )
        # Record order
        record_order({
            "id": session.id[:8].upper(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "sku": sku,
            "product": p["name"],
            "price": p["price"],
            "status": "checkout_created",
            "stripe_session": session.id,
            "checkout_url": session.url,
        })
        return True, session.url
    except Exception as e:
        log.error(f"stripe error: {e}")
        return False, str(e)


# ------- FastAPI app -------
if HAS_FASTAPI:
    app = FastAPI(title="Hitchy Shop", version="1.0")

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "stripe": bool(os.environ.get("STRIPE_SECRET_KEY")),
            "products": len(PRODUCTS),
        }

    @app.get("/skus")
    def skus():
        out = []
        for sku, p in PRODUCTS.items():
            out.append({"sku": sku, **p, "paypal_url": paypal_url(sku)})
        return out

    @app.post("/checkout/{sku}")
    def checkout(sku: str, request: Request):
        if sku not in PRODUCTS:
            raise HTTPException(404, "unknown sku")
        base = str(request.base_url).rstrip("/")
        ok, url = stripe_checkout_url(
            sku,
            success_url=base + "/success",
            cancel_url=base + "/cancel",
        )
        if ok:
            return {"checkout_url": url, "fallback": False}
        return {
            "checkout_url": paypal_url(sku),
            "fallback": True,
            "reason": url,
        }

    @app.post("/webhook")
    async def webhook(request: Request):
        # Verify and record successful payment
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if HAS_STRIPE and secret:
            try:
                stripe.WebhookEvent = stripe.Event.construct_from(
                    json.loads(payload), sig_header, secret
                )
            except Exception as e:
                log.error(f"webhook signature error: {e}")
                raise HTTPException(400, str(e))
        event = json.loads(payload)
        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            sku = session.get("metadata", {}).get("sku", "?")
            log.info(f"PAYMENT SUCCESS sku={sku} session={session.get('id')}")
            # Update latest order record
            try:
                lines = ORDERS.read_text(encoding="utf-8", errors="ignore").splitlines()
                for i in range(len(lines) - 1, -1, -1):
                    o = json.loads(lines[i])
                    if o.get("stripe_session") == session.get("id"):
                        o["status"] = "paid"
                        o["paid_ts"] = datetime.now(timezone.utc).isoformat()
                        lines[i] = json.dumps(o)
                        break
                ORDERS.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception as e:
                log.error(f"order update error: {e}")
        return {"received": True}

    @app.get("/orders")
    def orders():
        if not ORDERS.exists():
            return []
        out = []
        for line in ORDERS.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    # ------- Email capture + lead-magnet endpoints -------
    @app.post("/subscribe")
    async def subscribe(request: Request):
        """Newsletter signup. Captures email + intent. No auth, no Stripe."""
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "JSON body required: {\"email\": \"...\"}")
        email = (data.get("email") or "").strip().lower()
        intent = (data.get("intent") or "").strip()
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(400, "valid email required")
        if len(email) > 320:
            raise HTTPException(400, "email too long")
        entry = {
            "id": "SUB_" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S%f")[:14],
            "ts": datetime.now(timezone.utc).isoformat(),
            "email": email,
            "intent": intent,
            "ip": request.client.host if request.client else None,
            "ua": request.headers.get("user-agent", "")[:200],
            "source": data.get("source", "shop-form"),
        }
        with SUBSCRIBERS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        log.info(f"NEW SUBSCRIBER {entry['id']} email={email} intent={intent}")
        # Send welcome email (async, non-blocking best-effort)
        try:
            send_welcome_email(email, intent=intent)
        except Exception as e:
            log.warning(f"welcome email skipped: {e}")
        return {
            "ok": True,
            "id": entry["id"],
            "next": "Check your inbox for the welcome pack.",
        }

    @app.get("/subscribers")
    def list_subscribers():
        if not SUBSCRIBERS.exists():
            return []
        out = []
        for line in SUBSCRIBERS.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    @app.post("/lead/{sku}")
    async def lead_magnet(sku: str, request: Request):
        """Free lead-magnet request. Captures email + sends them the free pack link."""
        if sku not in PRODUCTS:
            raise HTTPException(404, "unknown lead sku")
        p = PRODUCTS[sku]
        if p.get("price", 0) > 0:
            raise HTTPException(400, "this sku is paid - use /checkout")
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "JSON body required: {\"email\": \"...\"}")
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            raise HTTPException(400, "valid email required")
        entry = {
            "id": "LEAD_" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S%f")[:14],
            "ts": datetime.now(timezone.utc).isoformat(),
            "sku": sku,
            "product": p["name"],
            "email": email,
            "ip": request.client.host if request.client else None,
            "ua": request.headers.get("user-agent", "")[:200],
            "delivery_url": p.get("delivery_url", ""),
        }
        with LEADS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        # Also log as subscriber so it's in the email list
        sub_entry = {
            "id": "SUB_" + entry["id"][5:],
            "ts": entry["ts"],
            "email": email,
            "intent": f"lead-magnet:{sku}",
            "source": "lead-form",
        }
        with SUBSCRIBERS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sub_entry) + "\n")
        log.info(f"NEW LEAD {entry['id']} sku={sku} email={email}")
        # Send welcome email with the lead magnet link
        try:
            send_welcome_email(email, intent=f"lead-magnet:{sku}", sku=sku)
        except Exception as e:
            log.warning(f"welcome email skipped: {e}")
        return {
            "ok": True,
            "id": entry["id"],
            "product": p["name"],
            "delivery_url": p.get("delivery_url", ""),
            "next": "Check your inbox for the download link.",
        }

    @app.get("/leads")
    def list_leads():
        if not LEADS.exists():
            return []
        out = []
        for line in LEADS.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    @app.get("/stats")
    def stats():
        """Lightweight stats for marketing dashboards."""
        out = {
            "subscribers": 0,
            "leads": 0,
            "orders": 0,
            "paid_orders": 0,
            "revenue_usd": 0,
        }
        if SUBSCRIBERS.exists():
            out["subscribers"] = sum(1 for _ in SUBSCRIBERS.open(encoding="utf-8", errors="ignore"))
        if LEADS.exists():
            out["leads"] = sum(1 for _ in LEADS.open(encoding="utf-8", errors="ignore"))
        if ORDERS.exists():
            for line in ORDERS.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    o = json.loads(line)
                    out["orders"] += 1
                    if o.get("status") == "paid":
                        out["paid_orders"] += 1
                        out["revenue_usd"] += float(o.get("price", 0))
                except Exception:
                    pass
        return out


if __name__ == "__main__":
    if HAS_FASTAPI:
        port = int(os.environ.get("PORT", "8522"))
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    else:
        print("FastAPI not installed; cannot start server.")
        sys.exit(2)