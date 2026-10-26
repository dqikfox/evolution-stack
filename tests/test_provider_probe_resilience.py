"""
Tests for the provider router's failure reporting and probe resilience.

Three defects are covered here, all found the hard way - by a live run
that reported something the operator could not act on:

1. A request that times out returns NO body. `_err(None)` used to return
   the string "None", so the recorded error was literally "None" and the
   provider looked defective for a reason nobody could name.

2. One transport failure was enough to demote a working provider. A cold
   start on a local provider is not a verdict, so the probe is retried once
   and only a second failure counts.

3. A local provider is a process on this host, not a link across the
   internet, so a cold start gets a longer leash than a hosted one.

    pytest tests/test_provider_probe_resilience.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROUTER = "C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py"

spec = importlib.util.spec_from_file_location("_router_under_test", ROUTER)
mod = importlib.util.module_from_spec(spec)
sys.modules["_router_under_test"] = mod
spec.loader.exec_module(mod)


# ------------------------------------------------------- the masked error

def test_a_missing_body_does_not_become_the_string_none():
    """The error must never be the word 'None'."""
    assert mod._err(None) == "", "_err(None) must return an empty string"


def test_a_body_error_is_still_readable():
    assert "boom" in mod._err({"error": "boom"})
    assert "boom" in mod._err({"error": {"type": "invalid", "message": "boom"}})
    assert mod._err({"nothing": "here"}) != ""


def test_a_transport_failure_is_reported_as_a_transport_failure(monkeypatch):
    """A timeout must name the timeout, not vanish."""
    seen = {}

    def fake_post(url, payload, headers, timeout):
        # exactly what _post returns when the socket times out
        return None, None, "timed out"

    monkeypatch.setattr(mod, "_post", fake_post)
    p = mod.Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
                     cost_tier="local", priority=40, local=True)
    with pytest.raises(RuntimeError) as e:
        mod.call(p, "hello", max_tokens=8, timeout=5)
    msg = str(e.value)
    assert "None" != msg.strip(), "the error must not be the string 'None'"
    assert "timed out" in msg.lower(), "the transport error was lost: %r" % msg
    seen["ok"] = True


# ------------------------------------------------------- the retry

def test_a_single_transport_failure_does_not_demote_the_provider(monkeypatch):
    """One slow request, then a good one: the provider is healthy."""
    calls = {"n": 0}

    def flaky(p, prompt, max_tokens=256, timeout=120):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("timed out")
        return "Reply with exactly: ORCHESTRA OK", {"elapsed": 1.2}

    monkeypatch.setattr(mod, "call", flaky)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
                     cost_tier="local", priority=40, local=True)
    out = mod.probe(p, timeout=5)
    assert out["status"] == "healthy", out
    assert calls["n"] == 2, "the probe must have retried once"
    assert out["elapsed"] == 1.2


def test_two_transport_failures_do_demote_the_provider(monkeypatch):
    """Two agreeing failures are a verdict."""
    calls = {"n": 0}

    def always_slow(p, prompt, max_tokens=256, timeout=120):
        calls["n"] += 1
        raise RuntimeError("timed out")

    monkeypatch.setattr(mod, "call", always_slow)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
                     cost_tier="local", priority=40, local=True)
    out = mod.probe(p, timeout=5)
    assert out["status"] == "failed", out
    assert calls["n"] == 2
    assert "timed out" in (out["error"] or "").lower(), out["error"]


def test_a_credential_failure_is_not_retried(monkeypatch):
    """A wrong key is a verdict on the first try - retrying is pointless."""
    calls = {"n": 0}

    def noauth(p, prompt, max_tokens=256, timeout=120):
        calls["n"] += 1
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(mod, "call", noauth)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("xai", "openai", "https://api.x.ai/v1", "grok-3",
                     cost_tier="xai", priority=10)
    out = mod.probe(p, timeout=5)
    assert calls["n"] == 1, "a credential failure must not be retried"
    assert out["status"] == "noauth", out


def test_a_wrong_answer_is_not_retried(monkeypatch):
    """A provider that answers wrongly answered. That is a verdict."""
    calls = {"n": 0}

    def wrong(p, prompt, max_tokens=256, timeout=120):
        calls["n"] += 1
        return "I am a helpful assistant", {"elapsed": 0.5}

    monkeypatch.setattr(mod, "call", wrong)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
                     cost_tier="local", priority=40, local=True)
    out = mod.probe(p, timeout=5)
    assert calls["n"] == 1
    assert out["status"] == "wrong-answer", out
    assert "did not match" in (out["error"] or "")


# ------------------------------------------------------- the timeouts

def test_a_local_provider_gets_the_local_timeout_floor(monkeypatch):
    """A local provider must not be given a hosted provider's leash."""
    seen = {}

    def capture(p, prompt, max_tokens=256, timeout=120):
        seen["timeout"] = timeout
        return "Reply with exactly: ORCHESTRA OK", {"elapsed": 1.0}

    monkeypatch.setattr(mod, "call", capture)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("nexus", "openai", "http://127.0.0.1:8650/v1", "kimi-k2.6:cloud",
                     cost_tier="local", priority=40, local=True)
    mod.probe(p, timeout=5)
    assert seen["timeout"] >= mod.LOCAL_TIMEOUT, seen


def test_a_hosted_provider_keeps_the_callers_timeout(monkeypatch):
    seen = {}

    def capture(p, prompt, max_tokens=256, timeout=120):
        seen["timeout"] = timeout
        return "Reply with exactly: ORCHESTRA OK", {"elapsed": 1.0}

    monkeypatch.setattr(mod, "call", capture)
    monkeypatch.setattr(mod, "_remember", lambda *a, **k: None)
    p = mod.Provider("xai", "openai", "https://api.x.ai/v1", "grok-3",
                     cost_tier="xai", priority=10)
    mod.probe(p, timeout=5)
    assert seen["timeout"] == 5, seen


def test_the_transient_list_covers_the_real_transport_failures():
    for phrase in ("timed out", "connection reset", "connection refused",
                   "bad gateway", "service unavailable", "eof occurred"):
        assert mod._is_transient(phrase), phrase
    for phrase in ("401 unauthorized", "credit_balance_exhausted",
                   "no such model", "invalid_api_key"):
        assert not mod._is_transient(phrase), phrase
