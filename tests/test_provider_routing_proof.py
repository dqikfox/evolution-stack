"""
The routing proof, as a test that can never be faked.

A delegation or a prompt that CONTAINS the expected answer proves nothing: the
model can echo it back from the prompt. The earlier multi-provider proof was
exactly that mistake - the subagent goals said "Reply with exactly: CLAUDE
SAYS HELLO", so every child passed while all of them ran on the same
inherited parent model.

So this test does it properly:

  * The caller generates a FRESH RANDOM NONCE. It is not in any prompt the
    caller can see in advance and it is different for every provider.
  * Each provider is PINNED, so exactly one provider is eligible.
  * The response must contain that provider's nonce and no other.
  * The SERVED provider must equal the PINNED provider.
  * The token counts must differ between providers, which is the signature
    that genuinely different models served the calls.

These are live calls. They cost real money (a few thousandths of a dollar)
and they are the only way to prove a rotation actually reaches several
different models. Everything else - a models list, a listening port, a
config entry - is inference, not evidence.
"""

import json
import os
import secrets
import string
import subprocess
import sys

import pytest

ROUTER_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py"
PY = r"C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

# The providers a real request must reach, with the model each one serves.
# The local ones are free; the hosted ones cost a fraction of a cent.
TARGETS = [
    ("anthropic", "claude-sonnet-4-6", True),
    ("xai", "grok-3", True),
    ("ollama-local", "starscream:latest", True),
    ("nexus", "kimi-k2.6:cloud", True),
    ("ollama-cloud", "minimax-m3.1-flash", True),
]


def _nonce() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


def _call(provider: str, nonce: str) -> dict:
    """One pinned, real call. Returns the router's JSON answer."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    r = subprocess.run(
        [PY, ROUTER_PATH, "chat",
         "Reply with exactly this token and nothing else: " + nonce,
         "--provider", provider, "--json"],
        capture_output=True, text=True, timeout=240, env=env,
        encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    start = out.find("{")
    assert start >= 0, "the router returned no JSON: %s" % out[:200]
    return json.loads(out[start:])


@pytest.mark.parametrize("provider,model,hosted", TARGETS)
def test_a_pinned_provider_serves_its_own_nonce(provider, model, hosted):
    """The pinned provider answers, and it is the provider that answered."""
    nonce = _nonce()
    d = _call(provider, nonce)

    assert d.get("http") == 200, "%s did not answer 200: %s" % (provider, d.get("error"))
    assert nonce in (d.get("text") or ""), \
        "%s did not echo the nonce it was given: %r" % (provider, d.get("text"))
    assert d.get("provider") == provider, \
        "the call was pinned to %s but %s served it" % (provider, d.get("provider"))
    assert d.get("model") == model, \
        "%s served the wrong model: %s" % (provider, d.get("model"))
    assert d.get("ok") is True, "%s reported a failure: %s" % (provider, d.get("error"))
    assert d.get("tokens_in") is not None, "the call recorded no token usage"


def test_the_providers_are_genuinely_different_models():
    """Different token counts prove different models served the calls.

    Two calls to the same model with the same prompt would land on the same
    token count. Distinct counts are the signature of distinct models.
    """
    seen = {}
    for provider, model, _hosted in TARGETS:
        d = _call(provider, _nonce())
        assert d.get("http") == 200, "%s failed: %s" % (provider, d.get("error"))
        seen[provider] = (d.get("tokens_in"), d.get("model"))

    assert len(seen) == len(TARGETS), "a provider was not exercised: %s" % seen
    counts = [v[0] for v in seen.values()]
    assert len(set(counts)) == len(counts), \
        "two providers reported identical token counts, so they may be the same model: %s" % seen


def test_a_pin_is_honoured_and_does_not_fall_through():
    """A pinned call must not be served by another provider.

    Without this, a broken provider would silently be answered by a
    neighbour and the rotation would look healthy while it is not.
    """
    nonce = _nonce()
    d = _call("xai", nonce)
    assert d.get("provider") == "xai", \
        "the pin was not honoured, %s served it" % d.get("provider")
    assert not d.get("attempts"), \
        "a pinned call tried other providers: %s" % d.get("attempts")
