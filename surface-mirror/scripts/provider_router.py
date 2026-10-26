#!/usr/bin/env python3
"""
provider_router.py - one routing layer across every model provider on THRONE.

The point: a single call that reaches whichever provider is healthy, falls back
when one is not, and records what each provider actually did - so "which model
answered" is a fact, not a guess.

Design rules (each one earned):
  * A provider is HEALTHY only if a real request returned the expected content.
    A TCP connect, a 200 on a page, or a models list proves nothing.
  * A key that is present but cannot pay is BLOCKED, not FAILED. It is kept out
    of the rotation but it is not retried on every call.
  * Secrets are read from the Windows environment or from 1Password at call
    time and are never written to disk, logged, or echoed.
  * Every call records: provider, model, latency, tokens, and estimated cost.

Usage:
    provider_router.py health                 # probe every provider, print the matrix
    provider_router.py health --json
    provider_router.py chat "your prompt"      # route a request, with fallback
    provider_router.py chat "prompt" --provider anthropic --model claude-sonnet-4-6
    provider_router.py chat "prompt" --json
    provider_router.py stats                  # the spend/latency ledger
    provider_router.py providers              # the registry as configured

Exit codes: 0 ok, 1 no provider could serve the request, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import winreg
from dataclasses import dataclass, field, asdict
from pathlib import Path

LEDGER = Path(os.environ.get("HERMES_HOME", r"C:\Users\KING\AppData\Local\hermes")) / "logs" / "provider_ledger.jsonl"
# The canonical provider state directory. The bench publishes providers.json
# here, TESSERACT reads it from here, and the router keeps its last-known
# record beside it - so all three agree on one picture.
STATE = Path(os.environ.get("PROVIDER_STATE_DIR",
                            r"E:\ultron-memory\evolution-stack\state"))
# The last state each provider was actually SEEN in. Only a real response
# from the provider may update this file - never an infrastructure failure.
# So a 1Password rate limit cannot overwrite a healthy provider's state and
# then be read back as if it were the truth.
LAST_KNOWN = STATE / "provider_last_known.json"
OP_EXE = r"C:\Users\KING\AppData\Local\Microsoft\WinGet\Links\op.exe"
OP_SA = Path(r"C:\Users\KING\.ultron\.op_service_account")
VAULT = "credentials"

# Approximate USD per 1M tokens. Used for cost accounting only, never for billing.
PRICE = {
    "claude-opus-4-8": (15.0, 75.0), "claude-opus-4.6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.5": (1.25, 10.0), "gpt-5.1": (1.25, 10.0), "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "grok-3": (3.0, 15.0), "grok-4": (3.0, 15.0),
    "kimi-k2.6:cloud": (0.0, 0.0), "minimax-m3.1-flash": (0.0, 0.0),
}


@dataclass
class Provider:
    name: str
    kind: str                      # anthropic | openai | ollama | nexus
    base_url: str
    model: str
    key_env: str | None = None     # Windows environment variable holding the key
    key_vault: str | None = None   # 1Password item title
    key_field: str = "credential"
    headers: str = "bearer"        # bearer | x-api-key
    local: bool = False
    cost_tier: str = "local"
    priority: int = 50
    note: str = ""
    enabled: bool = True


# Providers that exist in the credential pool but CANNOT serve a request right
# now. They are reported, never rotated into, and never retried on every call.
# Verified 2026-10-26.
BLOCKED: list[dict] = [
    {"provider": "openai-codex", "model": "gpt-5.5", "status": "blocked",
     "reason": "The ChatGPT OAuth token authenticates but the account has NO entitled Codex "
               "models - /backend-api/codex/models returns an empty list and every model name "
               "is rejected with 'not supported when using Codex with a ChatGPT account'.",
     "unblock": "A ChatGPT plan with Codex entitlement."},
    {"provider": "copilot", "model": "gpt-4o", "status": "blocked",
     "reason": "The GitHub token is valid but the account is 'not licensed to use Copilot'.",
     "unblock": "A GitHub Copilot licence on the account behind the gh token."},
    {"provider": "openrouter", "model": "anthropic/claude-opus-4.8", "status": "blocked",
     "reason": "No OpenRouter key exists in the Windows environment or the 1Password vault, so "
               "the MOA aggregator had nothing to aggregate through.",
     "unblock": "An OpenRouter API key. It would be the single cheapest way to reach "
                "Claude+GPT+Grok+Gemini under one key."},
]


# The registry. `priority` decides the rotation order: lower runs first.
REGISTRY: list[Provider] = [
    Provider("anthropic", "anthropic", "https://api.anthropic.com", "claude-sonnet-4-6",
             key_env="ANTHROPIC_API_KEY", key_vault="ANTHROPIC_API_KEY",
             headers="x-api-key", cost_tier="anthropic", priority=10,
             note="Claude. Key in the Windows env and mirrored in 1Password."),
    Provider("xai", "openai", "https://api.x.ai/v1", "grok-3",
             key_env="XAI_API_KEY", key_vault="XAI_API_KEY",
             cost_tier="xai", priority=20,
             note="Grok. Key in the Windows env and mirrored in 1Password."),
    Provider("openai", "openai", "https://api.openai.com/v1", "gpt-5.5",
             key_vault="OpenAI Project Key",
             cost_tier="openai", priority=30,
             note="ChatGPT. Key in 1Password as 'OpenAI Project Key'; the env var "
                  "OPENAI_API_KEY is a 'nexus-local' placeholder and will NOT work here. "
                  "The key is valid but the account has no credits - add credit at "
                  "platform.openai.com/settings/organization/billing/ to unblock."),
    Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
             cost_tier="local", priority=40, local=True,
             note="NEXUS CORE as an OpenAI-compatible endpoint. Local models, zero cost."),
    Provider("ollama-cloud", "openai", "https://ollama.com/v1", "minimax-m3.1-flash",
             key_env="OLLAMA_API_KEY", key_vault="OLLAMA_API_KEY",
             cost_tier="ollama-cloud", priority=50,
             note="Ollama Cloud, paid tier. The env key is set and working."),
    Provider("ollama-local", "ollama", "http://127.0.0.1:11434", "starscream:latest",
             cost_tier="local", priority=60, local=True,
             note="The local 3090. Free, offline, 64K context."),
]


# ---------------------------------------------------------------- secrets

def win_env(name: str) -> str | None:
    """Read a user or machine environment variable without printing it."""
    for hive, path in ((winreg.HKEY_CURRENT_USER, "Environment"),
                       (winreg.HKEY_LOCAL_MACHINE,
                        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(hive, path) as k:
                v, _ = winreg.QueryValueEx(k, name)
                if v:
                    return str(v)
        except OSError:
            pass
    return None


class VaultUnavailable(RuntimeError):
    """The vault was reached but could not answer (rate limit, outage, timeout).

    This is NOT the same as 'the credential does not exist'. A rate-limited
    vault must never change a provider's reported state, so it gets its own
    exception and its own status.
    """


# A 1Password outage degrades a provider, it does not change what the
# provider IS. So the resolved secret is cached with Windows DPAPI
# (CurrentUser scope) and the cache is used when the vault will not answer.
# The plaintext never touches the disk and never appears on a command line.
VAULT_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\KING\AppData\Local\hermes")) / "vault"


def _dpapi(plain: str, protect: bool = True) -> str:
    script = (
        "try{Add-Type -AssemblyName System.Security}catch{};"
        "try{Add-Type -AssemblyName System.Security.Cryptography.ProtectedData}catch{};"
        "$b=[System.Text.Encoding]::UTF8.GetBytes($env:PLAIN);"
        "$p=[System.Security.Cryptography.ProtectedData]::Protect($b,$null,"
        "[System.Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[Convert]::ToBase64String($p)"
        if protect else
        "try{Add-Type -AssemblyName System.Security}catch{};"
        "try{Add-Type -AssemblyName System.Security.Cryptography.ProtectedData}catch{};"
        "$b=[Convert]::FromBase64String($env:CIPHER);"
        "$p=[System.Security.Cryptography.ProtectedData]::Unprotect($b,$null,"
        "[System.Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[System.Text.Encoding]::UTF8.GetString($p)"
    )
    env = dict(os.environ)
    env["PLAIN" if protect else "CIPHER"] = plain
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError("DPAPI failed: %s" % (r.stderr or "")[:120])
    return r.stdout.strip()


def _cache_path(title: str, field: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in "%s.%s" % (title, field))
    return VAULT_DIR / ("%s.dpapi" % safe)


def _cache_read(title: str, field: str) -> str | None:
    p = _cache_path(title, field)
    if not p.is_file():
        return None
    try:
        return _dpapi(p.read_text(encoding="utf-8").strip(), protect=False)
    except Exception:
        return None


def _cache_write(title: str, field: str, value: str) -> None:
    try:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(title, field).write_text(_dpapi(value), encoding="utf-8")
    except Exception:
        pass


def vault_secret(title: str, field: str = "credential") -> str | None:
    """Read one secret out of the 1Password service account. Never logged.

    Raises VaultUnavailable when the vault was reached but would not answer
    (rate limit, outage). Returns None only when the item genuinely has no
    such field. Falls back to the DPAPI cache so a vault outage degrades the
    provider instead of silently changing its state.
    """
    if not OP_SA.is_file() or not Path(OP_EXE).is_file():
        raise VaultUnavailable("the 1Password CLI or the service account is missing")
    env = dict(os.environ)
    env["OP_SERVICE_ACCOUNT_TOKEN"] = OP_SA.read_text(encoding="utf-8").strip()
    try:
        r = subprocess.run(
            [OP_EXE, "item", "get", title, "--vault", VAULT, "--format", "json", "--reveal"],
            capture_output=True, text=True, timeout=90, env=env,
            encoding="utf-8", errors="replace")
    except Exception as e:
        cached = _cache_read(title, field)
        if cached:
            return cached
        raise VaultUnavailable("the vault call failed: %s" % str(e)[:100])
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        # A rate limit or an outage is not a missing credential.
        if "rate-limit" in err.lower() or "too many requests" in err.lower() \
                or "couldn't connect" in err.lower() or "server error" in err.lower():
            cached = _cache_read(title, field)
            if cached:
                return cached
            raise VaultUnavailable(err[:140] or "the vault was rate-limited")
        # The item may not exist at all. That IS a real answer.
        if "not found" in err.lower() or "no item" in err.lower():
            return None
        cached = _cache_read(title, field)
        if cached:
            return cached
        raise VaultUnavailable(err[:140] or "the vault call failed")
    try:
        data = json.loads(r.stdout)
    except Exception:
        cached = _cache_read(title, field)
        if cached:
            return cached
        raise VaultUnavailable("the vault returned an unreadable answer")
    for f in data.get("fields", []):
        if f.get("id") == field:
            v = str(f.get("value", "")).strip()
            if v:
                _cache_write(title, field, v)
                return v
    return None


def resolve_key(p: Provider) -> str | None:
    """The credential for a provider. Raises VaultUnavailable if the vault
    would not answer - never silently returns None for that reason."""
    if p.key_env:
        v = win_env(p.key_env)
        if v:
            return v
    if p.key_vault:
        v = vault_secret(p.key_vault, p.key_field)
        if v:
            return v
    return None


# ---------------------------------------------------------------- transport

def _post(url: str, payload: dict, headers: dict, timeout: int):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body, None
    except Exception as e:
        return None, None, str(e)[:200]


def call(p: Provider, prompt: str, max_tokens: int = 256, timeout: int = 120):
    """One real request. Returns (text, meta). Raises on unusable responses."""
    key = resolve_key(p)
    t0 = time.time()
    meta = {"provider": p.name, "model": p.model, "http": None, "error": None}

    if p.kind == "anthropic":
        if not key:
            meta["error"] = "no key"
            raise RuntimeError("no key")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        payload = {"model": p.model, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
        st, body, err = _post(p.base_url + "/v1/messages", payload, headers, timeout)
        meta["http"] = st
        if st != 200:
            meta["error"] = _err(body)
            raise RuntimeError(meta["error"])
        text = "".join(c.get("text", "") for c in body.get("content", []))
        usage = body.get("usage", {})
        meta["tokens_in"] = usage.get("input_tokens", 0)
        meta["tokens_out"] = usage.get("output_tokens", 0)

    elif p.kind == "openai":
        if not key:
            # A LOCAL endpoint (the NEXUS proxy) accepts a well-known
            # placeholder. A HOSTED API must never receive one: it answers
            # 'invalid_api_key', which reads as bad credentials when the
            # truth is that we had no credential to send.
            if p.local:
                key = "nexus-local"
            else:
                meta["error"] = "no key"
                raise RuntimeError("no key")
        headers = {"Authorization": "Bearer " + key}
        payload = {"model": p.model, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
        # The Responses API is required for the newest OpenAI reasoning models.
        if p.name == "openai":
            payload = {"model": p.model, "input": prompt, "max_output_tokens": max_tokens}
            st, body, err = _post(p.base_url + "/responses", payload, headers, timeout)
        else:
            st, body, err = _post(p.base_url + "/chat/completions", payload, headers, timeout)
        meta["http"] = st
        if st != 200:
            meta["error"] = _err(body)
            raise RuntimeError(meta["error"])
        try:
            if p.name == "openai":
                text = body["output"][0]["content"][0]["text"]
            else:
                text = body["choices"][0]["message"]["content"]
        except Exception:
            text = json.dumps(body)[:2000]
        usage = body.get("usage", {}) or body.get("output_tokens", {}) or {}
        meta["tokens_in"] = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
        meta["tokens_out"] = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0

    elif p.kind == "ollama":
        payload = {"model": p.model, "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "think": False, "options": {"num_ctx": 65536}}
        st, body, err = _post(p.base_url + "/api/chat", payload, {}, timeout)
        meta["http"] = st
        if st != 200:
            meta["error"] = _err(body) or err or ("HTTP %s" % st)
            raise RuntimeError(meta["error"])
        text = body.get("message", {}).get("content", "")
        meta["tokens_in"] = body.get("prompt_eval_count", 0)
        meta["tokens_out"] = body.get("eval_count", 0)

    else:
        raise RuntimeError("unknown provider kind %r" % p.kind)

    if not text or not str(text).strip():
        meta["error"] = "empty response"
        raise RuntimeError("empty response")

    meta["elapsed"] = round(time.time() - t0, 2)
    tin, tout = meta.get("tokens_in", 0), meta.get("tokens_out", 0)
    # PRICE is keyed by MODEL. A local model and the Ollama Cloud tier are free
    # to the house. Everything else is priced by its model name.
    if p.cost_tier in ("local", "ollama-cloud"):
        pin, pout = 0.0, 0.0
    else:
        pin, pout = PRICE.get(p.model, PRICE.get(p.cost_tier, (0.0, 0.0)))
    meta["cost_usd"] = round((tin / 1e6) * pin + (tout / 1e6) * pout, 6)
    meta["ok"] = True
    return str(text), meta


def _err(body) -> str:
    if isinstance(body, dict):
        e = body.get("error")
        if isinstance(e, dict):
            return "%s: %s" % (e.get("code") or e.get("type") or "error",
                               str(e.get("message"))[:120])
        if e:
            return str(e)[:120]
    return str(body)[:120]


def classify(err: str) -> str:
    """Distinguish 'cannot pay' from 'cannot authenticate' from 'broken'."""
    s = (err or "").lower()
    if any(k in s for k in ("credit", "quota", "insufficient", "billing", "payment required")):
        return "blocked"
    if any(k in s for k in ("api key", "unauthorized", "authentication", "401", "invalid")):
        return "noauth"
    if any(k in s for k in ("not found", "404", "model")):
        return "nomodel"
    return "failed"


# ---------------------------------------------------------------- health

def probe(p: Provider, timeout: int = 90) -> dict:
    """A provider is healthy only if a real request returns real content."""
    out = {"provider": p.name, "model": p.model, "status": "unknown", "elapsed": None,
           "error": None, "cost_tier": p.cost_tier, "note": p.note, "priority": p.priority}
    try:
        text, meta = call(p, "Reply with exactly: ORCHESTRA OK", max_tokens=24, timeout=timeout)
        ok = "ORCHESTRA OK" in text
        out["status"] = "healthy" if ok else "wrong-answer"
        out["elapsed"] = meta.get("elapsed")
        if not ok:
            out["error"] = "responded but did not match: %r" % text[:60]
    except VaultUnavailable as e:
        # The vault would not answer. That is NOT a provider failure and it is
        # NOT missing credentials. The provider's last known state is kept so
        # a rate limit cannot silently demote a working provider.
        out["status"] = "vault"
        out["error"] = str(e)[:140]
        prev = _last_known(p.name)
        if prev and prev.get("status") not in (None, "unknown"):
            out["status"] = prev["status"]
            out["elapsed"] = prev.get("elapsed")
            out["error"] = ("the vault would not answer; the last known state is kept "
                            "(%s)" % str(e)[:80])
        # NOTE: nothing is remembered here. A state the provider was never
        # seen in must not become the last known state.
        return out
    except Exception as e:
        msg = str(e)
        out["status"] = classify(msg)
        out["error"] = msg[:140]
    # The provider answered, so this IS an observed state: remember it.
    _remember(p.name, out)
    return out


def _last_known(provider: str) -> dict | None:
    """The state the provider was last SEEN in, from a real response."""
    try:
        if not LAST_KNOWN.is_file():
            return None
        d = json.loads(LAST_KNOWN.read_text(encoding="utf-8", errors="replace"))
        row = d.get(provider)
        return row if isinstance(row, dict) else None
    except Exception:
        return None


def _remember(provider: str, row: dict) -> None:
    """Record a state the provider was actually observed in."""
    try:
        d = {}
        if LAST_KNOWN.is_file():
            d = json.loads(LAST_KNOWN.read_text(encoding="utf-8", errors="replace"))
        d[provider] = {"status": row.get("status"), "model": row.get("model"),
                       "elapsed": row.get("elapsed"), "error": row.get("error"),
                       "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        LAST_KNOWN.parent.mkdir(parents=True, exist_ok=True)
        tmp = LAST_KNOWN.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        tmp.replace(LAST_KNOWN)
    except Exception:
        pass


def health(timeout: int = 90) -> list[dict]:
    rows = [probe(p, timeout) for p in sorted(REGISTRY, key=lambda x: x.priority) if p.enabled]
    for b in BLOCKED:
        rows.append({"provider": b["provider"], "model": b["model"], "status": b["status"],
                     "elapsed": None, "error": b["reason"], "note": b["unblock"],
                     "cost_tier": "blocked", "priority": 99})
    return rows


# ---------------------------------------------------------------- ledger

def record(meta: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                **{k: meta.get(k) for k in
                                   ("provider", "model", "elapsed", "tokens_in",
                                    "tokens_out", "cost_usd", "ok", "error")}}) + "\n")
    except Exception:
        pass


def stats() -> dict:
    rows = []
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    by = {}
    for r in rows:
        b = by.setdefault(r.get("provider") or "?", {"calls": 0, "errors": 0, "cost_usd": 0.0,
                                                      "tokens": 0, "latencies": []})
        b["calls"] += 1
        if not r.get("ok"):
            b["errors"] += 1
        b["cost_usd"] += float(r.get("cost_usd") or 0)
        b["tokens"] += int(r.get("tokens_in") or 0) + int(r.get("tokens_out") or 0)
        if r.get("elapsed"):
            b["latencies"].append(float(r["elapsed"]))
    for b in by.values():
        L = b.pop("latencies")
        b["avg_latency"] = round(sum(L) / len(L), 2) if L else None
    return {"total_calls": len(rows),
            "total_cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rows), 4),
            "by_provider": by}


# ---------------------------------------------------------------- routing

def route(prompt: str, only: str | None = None, model: str | None = None,
          max_tokens: int = 256, timeout: int = 120):
    """Try providers in priority order, falling back on failure."""
    cands = [p for p in sorted(REGISTRY, key=lambda x: x.priority)
             if p.enabled and (only is None or p.name == only)]
    if not cands:
        raise SystemExit("no provider matches %r" % only)
    if model:
        cands = [p for p in cands if p.model == model] or cands
    attempts = []
    for p in cands:
        try:
            text, meta = call(p, prompt, max_tokens, timeout)
            record(meta)
            meta["attempts"] = attempts
            return text, meta
        except Exception as e:
            meta = {"provider": p.name, "model": p.model, "ok": False,
                    "error": str(e)[:140], "status": classify(str(e))}
            record(meta)
            attempts.append(meta)
    raise RuntimeError("every provider failed: %s" %
                       "; ".join("%s=%s" % (a["provider"], a["status"]) for a in attempts))


# ---------------------------------------------------------------- cli

def main() -> int:
    ap = argparse.ArgumentParser(description="THRONE multi-provider router")
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("health", help="probe every provider")
    h.add_argument("--json", action="store_true")
    h.add_argument("--timeout", type=int, default=90)

    c = sub.add_parser("chat", help="route a prompt")
    c.add_argument("prompt")
    c.add_argument("--provider")
    c.add_argument("--model")
    c.add_argument("--max-tokens", type=int, default=256)
    c.add_argument("--timeout", type=int, default=120)
    c.add_argument("--json", action="store_true")

    sub.add_parser("stats", help="the spend and latency ledger")
    sub.add_parser("providers", help="the registry")
    a = ap.parse_args()

    if a.cmd == "health":
        rows = health(a.timeout)
        if a.json:
            print(json.dumps(rows, indent=2))
        else:
            print("PROVIDER                MODEL                      STATUS       LATENCY")
            print("-" * 72)
            for r in rows:
                print("%-23s %-25s %-12s %s" % (
                    r["provider"], r["model"], r["status"],
                    ("%ss" % r["elapsed"]) if r["elapsed"] else (r["error"] or "")[:28]))
            healthy = [r for r in rows if r["status"] == "healthy"]
            print("\n%d/%d providers healthy" % (len(healthy), len(rows)))
            for r in rows:
                if r["status"] == "blocked":
                    print("\n  BLOCKED %s/%s" % (r["provider"], r["model"]))
                    print("    why:    %s" % str(r["error"])[:160])
                    print("    unblock: %s" % str(r["note"])[:160])
        return 0 if any(r["status"] == "healthy" for r in rows) else 1

    if a.cmd == "chat":
        try:
            text, meta = route(a.prompt, a.provider, a.model, a.max_tokens, a.timeout)
        except Exception as e:
            print("ROUTE FAILED: %s" % e, file=sys.stderr)
            return 1
        if a.json:
            print(json.dumps({"text": text, **meta}, indent=2))
        else:
            print(text)
            print("\n--- provider=%s model=%s elapsed=%ss tokens=%s/%s cost=$%s" % (
                meta["provider"], meta["model"], meta.get("elapsed"),
                meta.get("tokens_in"), meta.get("tokens_out"), meta.get("cost_usd")), file=sys.stderr)
        return 0

    if a.cmd == "stats":
        print(json.dumps(stats(), indent=2))
        return 0

    if a.cmd == "providers":
        for p in REGISTRY:
            print("%-14s %-26s %-12s prio=%-3d %s" % (p.name, p.model, p.cost_tier, p.priority, p.note))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
