"""
Tests for the multi-provider router.

The point of these tests is that a provider is only "healthy" if a REAL request
returned the expected content - never because a port answered, a models list
loaded, or a config file claimed it would work.

No test here touches a live provider or a real key. They use an isolated local
HTTP server and injected keys, so the suite stays deterministic and offline.
"""

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROUTER_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py"
spec = importlib.util.spec_from_file_location("provider_router", ROUTER_PATH)
pr = importlib.util.module_from_spec(spec)
# @dataclass resolves annotations through sys.modules, so the module must be
# registered BEFORE it is executed or the decorator blows up.
sys.modules["provider_router"] = pr
spec.loader.exec_module(pr)


# ------------------------------------------------------------------ fixtures

class _Handler(BaseHTTPRequestHandler):
    """Serves whatever the test set up. Records what it was asked."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps(self.server.responses.get(self.path, {})).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        self.server.seen.append((self.path, raw))
        # The mode can be set per-path PREFIX, so a test can make one provider
        # fail and another on the SAME server succeed. A global mode would make
        # both fail, which cannot express "the first is blocked, the second is not".
        # The router appends /chat/completions to the base_url, so the prefix is
        # matched against the full path.
        mode = self.server.mode
        for prefix, m in self.server.modes.items():
            if self.path.startswith(prefix):
                mode = m
                break

        if mode == "ok":
            payload = {"choices": [{"message": {"content": "ORCHESTRA OK"}}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
            status = 200
        elif mode == "wrong":
            payload = {"choices": [{"message": {"content": "hello there"}}]}
            status = 200
        elif mode == "empty":
            payload = {"choices": [{"message": {"content": "   "}}]}
            status = 200
        elif mode == "no_credits":
            payload = {"error": {"code": "credit_balance_exhausted",
                                 "message": "You have no credits remaining."}}
            status = 429
        elif mode == "badauth":
            payload = {"error": {"code": "invalid_api_key",
                                 "message": "Incorrect API key provided"}}
            status = 401
        elif mode == "notfound":
            payload = {"error": {"code": "model_not_found",
                                 "message": "The model is not supported"}}
            status = 404
        else:
            payload = {"error": {"message": "boom"}}
            status = 500

        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    srv.mode = "ok"
    srv.modes = {}          # path -> mode, so two providers on one server can differ
    srv.seen = []
    srv.responses = {}
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def mk(name, base, model="test-model", **kw):
    return pr.Provider(name, kw.pop("kind", "openai"), base, model, **kw)


# ------------------------------------------------------------------ the tests

def test_a_provider_is_healthy_only_on_the_expected_answer(server):
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "healthy"
    assert r["elapsed"] is not None


def test_a_wrong_answer_is_not_healthy(server):
    server.mode = "wrong"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "wrong-answer"
    assert "did not match" in r["error"]


def test_an_empty_answer_is_not_healthy(server):
    server.mode = "empty"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "failed"
    assert "empty" in r["error"].lower()


def test_no_credits_is_blocked_not_failed(server):
    """A key that cannot pay is BLOCKED - it must not be retried on every call."""
    server.mode = "no_credits"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "blocked"
    assert "credit" in r["error"].lower()


def test_bad_auth_is_noauth(server):
    server.mode = "badauth"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "noauth"


def test_a_missing_model_is_nomodel(server):
    server.mode = "notfound"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    r = pr.probe(p)
    assert r["status"] == "nomodel"


def test_an_unreachable_provider_fails_without_raising(server):
    p = mk("t", "http://127.0.0.1:9")
    r = pr.probe(p)
    assert r["status"] == "failed"


def test_routing_falls_through_to_the_next_working_provider(server, monkeypatch):
    """The first provider is dead, the second answers. The second must win."""
    dead = mk("dead", "http://127.0.0.1:9", priority=1)
    good = mk("good", "http://127.0.0.1:%d" % server.server_port, priority=2)
    monkeypatch.setattr(pr, "REGISTRY", [dead, good])
    text, meta = pr.route("hello")
    assert meta["provider"] == "good"
    assert "ORCHESTRA OK" in text
    assert len(meta["attempts"]) == 1
    assert meta["attempts"][0]["provider"] == "dead"


def test_routing_reports_every_failed_attempt_in_order(server, monkeypatch):
    a = mk("a", "http://127.0.0.1:9", priority=1)
    b = mk("b", "http://127.0.0.1:9", priority=2)
    c = mk("c", "http://127.0.0.1:%d" % server.server_port, priority=3)
    monkeypatch.setattr(pr, "REGISTRY", [a, b, c])
    _, meta = pr.route("hello")
    assert [x["provider"] for x in meta["attempts"]] == ["a", "b"]
    assert meta["provider"] == "c"


def test_routing_raises_when_every_provider_fails(server, monkeypatch):
    monkeypatch.setattr(pr, "REGISTRY", [mk("a", "http://127.0.0.1:9")])
    with pytest.raises(RuntimeError):
        pr.route("hello")


def test_a_blocked_provider_is_never_rotated_into(server, monkeypatch):
    """A provider with no credits must be skipped, not retried."""
    base = "http://127.0.0.1:%d" % server.server_port
    server.modes["/no_credits"] = "no_credits"
    bad = mk("bad", base, priority=1)
    bad.base_url = base + "/no_credits"
    good = mk("good", base, priority=2)
    good.base_url = base + "/ok"
    monkeypatch.setattr(pr, "REGISTRY", [bad, good])
    _, meta = pr.route("hello")
    assert meta["provider"] == "good"
    assert meta["attempts"][0]["status"] == "blocked"


def test_pinning_a_provider_uses_only_that_provider(server, monkeypatch):
    a = mk("a", "http://127.0.0.1:%d" % server.server_port, priority=1)
    b = mk("b", "http://127.0.0.1:%d" % server.server_port, priority=2)
    monkeypatch.setattr(pr, "REGISTRY", [a, b])
    _, meta = pr.route("hello", only="b")
    assert meta["provider"] == "b"
    assert meta["attempts"] == []


def test_cost_is_derived_from_the_model_not_the_tier(server, monkeypatch):
    """A regression guard: PRICE is keyed by MODEL, and the router must not
    look it up by provider tier and silently record every call as free."""
    server.mode = "ok"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port, model="claude-sonnet-4-6",
           cost_tier="anthropic")
    _, meta = pr.call(p, "hello", max_tokens=64)
    assert meta["cost_usd"] > 0.0, "a paid model must not record a zero cost"


def test_a_local_model_records_no_cost(server, monkeypatch):
    server.mode = "ok"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port, cost_tier="local")
    _, meta = pr.call(p, "hello", max_tokens=64)
    assert meta["cost_usd"] == 0.0


def test_the_registry_carries_no_secret_material():
    """No key, token or password may be written into the router source."""
    src = open(ROUTER_PATH, encoding="utf-8").read()
    for bad in ("sk-proj-", "sk-ant-", "xai-", "Bearer sk-", "eyJhbGciOi"):
        assert bad not in src, "the router source contains key material: %s" % bad


def test_the_registry_has_a_verified_provider_for_each_frontier():
    names = {p.name for p in pr.REGISTRY}
    for required in ("anthropic", "xai", "nexus", "ollama-cloud", "ollama-local"):
        assert required in names, "the rotation is missing %s" % required


def test_blocked_providers_carry_an_unblock_instruction():
    for b in pr.BLOCKED:
        assert b.get("unblock"), "a blocked provider must say how to unblock it"
        assert b.get("reason"), "a blocked provider must say why"


def test_health_includes_the_blocked_providers(monkeypatch):
    monkeypatch.setattr(pr, "probe", lambda p, timeout=90: {
        "provider": p.name, "model": p.model, "status": "healthy", "elapsed": 0.1,
        "error": None, "note": p.note, "cost_tier": p.cost_tier, "priority": p.priority})
    rows = pr.health()
    reported = {r["provider"] for r in rows}
    for b in pr.BLOCKED:
        assert b["provider"] in reported, "%s is blocked but health does not report it" % b["provider"]


def test_the_ledger_records_a_call(tmp_path, monkeypatch):
    led = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(pr, "LEDGER", led)
    pr.record({"provider": "x", "model": "m", "ok": True, "elapsed": 1.0,
               "tokens_in": 1, "tokens_out": 1, "cost_usd": 0.5})
    row = json.loads(led.read_text(encoding="utf-8").splitlines()[0])
    assert row["provider"] == "x"
    assert row["cost_usd"] == 0.5
