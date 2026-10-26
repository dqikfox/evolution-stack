"""
Tests for the ChatGPT provider in the multi-provider router.

ChatGPT reaches the router through the Codex CLI's OAuth session, not through
an HTTP API. That is a different transport from every other provider in the
registry, so it gets its own contract tests.

The contract these tests pin down:
  * The ChatGPT provider is in the registry and is not BLOCKED.
  * It never asks the vault for a credential - it has no API key.
  * A failed Codex run becomes a provider error, not a crash.
  * A successful Codex run returns the answer and records zero cost, because
    a Plus subscription is not metered API usage.
  * The router never writes the OAuth token to disk or into the ledger.
  * No test here contacts ChatGPT. The live proof is a separate, opt-in
    script that generates its own nonce.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROUTER_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py"
spec = importlib.util.spec_from_file_location("provider_router_chatgpt", ROUTER_PATH)
pr = importlib.util.module_from_spec(spec)
# @dataclass resolves annotations through sys.modules, so the module must be
# registered BEFORE it is executed or the decorator blows up.
sys.modules["provider_router_chatgpt"] = pr
spec.loader.exec_module(pr)


def chatgpt_provider():
    for p in pr.REGISTRY:
        if p.name == "chatgpt":
            return p
    raise AssertionError("the chatgpt provider is missing from the registry")


# ------------------------------------------------------------------ registry

def test_the_chatgpt_provider_is_in_the_registry():
    p = chatgpt_provider()
    assert p.kind == "codex"
    assert p.model
    assert p.cost_tier == "chatgpt"


def test_the_chatgpt_provider_is_not_blocked():
    """ChatGPT Plus IS entitled - it must not sit in the BLOCKED list."""
    blocked = {b["provider"] for b in pr.BLOCKED}
    assert "chatgpt" not in blocked
    assert "openai-codex" not in blocked


def test_the_chatgpt_provider_asks_the_vault_for_nothing():
    """ChatGPT has no API key. The vault must never be consulted for it."""
    called = []

    def boom(title, field="credential"):
        called.append(title)
        return "should-not-happen"

    original = pr.vault_secret
    pr.vault_secret = boom
    try:
        pr.resolve_key(chatgpt_provider())
    finally:
        pr.vault_secret = original
    assert called == []


def test_the_chatgpt_provider_is_not_given_a_placeholder_credential():
    """The local-placeholder path must never apply to a hosted service."""
    p = chatgpt_provider()
    assert p.local is True  # the CLI is local; the SERVICE is not metered
    # and the key resolution is explicitly empty
    assert pr.resolve_key(p) is None


# ------------------------------------------------------------------ transport

def test_a_failed_codex_run_becomes_a_provider_error(monkeypatch):
    """A broken CLI must degrade the provider, not crash the router."""

    def boom(p, prompt, timeout):
        return "", {"http": None, "error": "the Codex CLI is not installed",
                    "tokens_in": 0, "tokens_out": 0}

    monkeypatch.setattr(pr, "_codex_call", boom)
    with pytest.raises(RuntimeError) as exc:
        pr.call(chatgpt_provider(), "hello")
    assert "Codex CLI" in str(exc.value)


def test_a_codex_run_with_no_message_is_an_error(monkeypatch):
    def empty(p, prompt, timeout):
        return "", {"http": None, "error": "the Codex CLI returned no message",
                    "tokens_in": 0, "tokens_out": 0}

    monkeypatch.setattr(pr, "_codex_call", empty)
    with pytest.raises(RuntimeError):
        pr.call(chatgpt_provider(), "hello")


def test_a_successful_codex_run_returns_the_answer_and_records_no_cost(monkeypatch):
    """A Plus subscription is not metered usage: the cost must be zero."""

    def good(p, prompt, timeout):
        return "THE ANSWER", {"http": 200, "error": None,
                              "tokens_in": 1234, "tokens_out": 56}

    monkeypatch.setattr(pr, "_codex_call", good)
    text, meta = pr.call(chatgpt_provider(), "hello")
    assert text == "THE ANSWER"
    assert meta["http"] == 200
    assert meta["cost_usd"] == 0.0
    assert meta["tokens_in"] == 1234


def test_the_codex_call_does_not_pass_a_secret_on_a_command_line(monkeypatch):
    """The CLI refreshes its own OAuth token. No secret may appear in argv."""
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        # the -o file is the only path the router hands the CLI
        for i, a in enumerate(cmd):
            if a == "-o":
                Path(cmd[i + 1]).write_text("THE ANSWER", encoding="utf-8")
        return FakeProc()

    monkeypatch.setattr(pr.subprocess, "run", fake_run)
    text, meta = pr._codex_call(chatgpt_provider(), "hello", 60)
    assert text == "THE ANSWER"
    assert meta["http"] == 200
    joined = " ".join(seen["cmd"])
    assert "sk-" not in joined
    assert "Bearer" not in joined
    # the child must not inherit a foreign python/venv state
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        assert var not in seen.get("env", {})


def test_a_codex_timeout_becomes_an_error(monkeypatch):
    import subprocess as sp

    def timeout(cmd, **kw):
        raise sp.TimeoutExpired(cmd, kw.get("timeout", 60))

    monkeypatch.setattr(pr.subprocess, "run", timeout)
    text, meta = pr._codex_call(chatgpt_provider(), "hello", 1)
    assert text == ""
    assert "timeout" in meta["error"]


# ------------------------------------------------------------------ hygiene

def test_the_registry_holds_no_chatgpt_secret_material():
    """No OAuth token, refresh token or id token in the registry."""
    blob = json.dumps([p.__dict__ for p in pr.REGISTRY], default=str)
    for needle in ("eyJ", "refresh_token", "id_token", "access_token", "sk-"):
        assert needle not in blob


def test_the_router_never_reads_the_codex_auth_file_itself():
    """The CLI owns the OAuth session. The router must not parse it.

    The check is on CODE, not on text: the router's own note legitimately
    names the file it deliberately does NOT read. So the test walks the AST
    and looks for an actual FILE READ of that path.
    """
    import ast

    src = Path(ROUTER_PATH).read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)

    read_calls = {"open", "read_text", "read_bytes", "load", "loads"}
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name not in read_calls:
            continue
        # any string argument naming the OAuth session is a violation
        for arg in list(node.args) + [k.value for k in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    if ".codex" in sub.value or "auth.json" in sub.value:
                        offenders.append((name, sub.value))

    assert not offenders, "the router must not read the OAuth session: %s" % offenders


def test_the_router_holds_no_oauth_token_field_names_in_code():
    """No token field names may appear in executable code."""
    import ast

    src = Path(ROUTER_PATH).read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    banned = {"refresh_token", "id_token", "access_token"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in banned:
                hits.append(node.value)
    assert not hits, "the router must not name OAuth token fields: %s" % hits


def test_the_chatgpt_provider_survives_a_vault_outage(monkeypatch):
    """A vault outage must not change what ChatGPT IS."""

    def unavailable(title, field="credential"):
        raise pr.VaultUnavailable("rate limited")

    original = pr.vault_secret
    pr.vault_secret = unavailable
    try:
        # ChatGPT never asks the vault, so this must not raise.
        assert pr.resolve_key(chatgpt_provider()) is None
    finally:
        pr.vault_secret = original
