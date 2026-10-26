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


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    """No test may write to the production ledger or the production state.

    route() and call() record every attempt, so without this the suite would
    pollute the real spend log with rows named after test fixtures. The ledger
    is redirected into tmp_path for the whole test.

    The last-known provider record is redirected too. It lives in the same
    directory the dashboard reads, so a test provider named 't' would show up
    in the live provider panel.
    """
    monkeypatch.setattr(pr, "LEDGER", tmp_path / "provider_ledger.jsonl")
    monkeypatch.setattr(pr, "LAST_KNOWN", tmp_path / "provider_last_known.json")
    yield


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
    """Build a test provider.

    'local' is inferred from the base URL: a 127.0.0.1 endpoint is local and
    accepts the well-known placeholder bearer, a hosted endpoint must be
    given a real credential. An explicit local=... always wins.
    """
    if "local" not in kw:
        host = base.split("/")[2].split(":")[0] if base.count("/") >= 2 else ""
        kw["local"] = host in ("127.0.0.1", "localhost", "::1")
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


def test_the_ledger_records_a_call(isolated_ledger):
    pr.record({"provider": "x", "model": "m", "ok": True, "elapsed": 1.0,
               "tokens_in": 1, "tokens_out": 1, "cost_usd": 0.5})
    led = pr.LEDGER
    row = json.loads(led.read_text(encoding="utf-8").splitlines()[0])
    assert row["provider"] == "x"
    assert row["cost_usd"] == 0.5


# ------------------------------------------------------- the vault contract

def test_a_rate_limited_vault_is_not_a_missing_credential(monkeypatch):
    """A vault that will not answer is NOT the same as a credential that does
    not exist.

    The bug this guards: vault_secret() swallowed every error and returned
    None, so a 1Password rate limit looked exactly like 'no key'. The router
    then sent a placeholder bearer to a hosted API, got 'invalid_api_key'
    back, and reported the provider as broken - when the provider was fine
    and only the vault was busy.
    """
    def boom(*a, **k):
        raise pr.VaultUnavailable("Too many requests. Your client has been rate-limited.")

    monkeypatch.setattr(pr, "vault_secret", boom)
    p = mk("t", "http://127.0.0.1:1", key_vault="Some Item", key_env=None)
    with pytest.raises(pr.VaultUnavailable):
        pr.resolve_key(p)


def test_a_vault_outage_keeps_the_last_known_provider_state(monkeypatch, tmp_path):
    """The state of a provider must not change because the vault was busy.

    A provider that was healthy stays healthy in the report, with the reason
    attached. Otherwise a 30-second 1Password blip silently demotes a
    working provider on the dashboard.
    """
    monkeypatch.setattr(pr, "LAST_KNOWN", tmp_path / "provider_last_known.json")
    pr._remember("xai", {"provider": "xai", "model": "grok-3", "status": "healthy",
                          "elapsed": 1.2, "error": None})

    def boom(*a, **k):
        raise pr.VaultUnavailable("the vault was rate-limited")

    monkeypatch.setattr(pr, "vault_secret", boom)
    p = mk("xai", "http://127.0.0.1:1", key_vault="Some Item", key_env=None)
    row = pr.probe(p, timeout=5)
    assert row["status"] == "healthy", "a vault outage changed the provider state to %r" % row["status"]
    assert "vault" in (row["error"] or "").lower(), "the reason must be attached"


def test_a_vault_outage_never_becomes_the_last_known_state(monkeypatch, tmp_path):
    """A state the provider was never SEEN in must not be remembered.

    If a vault outage wrote its own state into the record, the next outage
    would read back 'vault' as if the provider had been seen in it - and the
    real state would be lost for good.
    """
    lk = tmp_path / "provider_last_known.json"
    monkeypatch.setattr(pr, "LAST_KNOWN", lk)

    def boom(*a, **k):
        raise pr.VaultUnavailable("the vault was rate-limited")

    monkeypatch.setattr(pr, "vault_secret", boom)
    p = mk("xai", "http://127.0.0.1:1", key_vault="Some Item", key_env=None)
    pr.probe(p, timeout=5)
    assert not lk.exists(), "a vault outage wrote a state the provider was never seen in"
    if lk.exists():
        d = json.loads(lk.read_text(encoding="utf-8"))
        assert d.get("xai", {}).get("status") != "vault"


def test_a_vault_outage_with_no_previous_state_is_unknown_not_failed(monkeypatch, tmp_path):
    """With no prior state to keep, the provider is 'vault', never 'failed'."""
    monkeypatch.setattr(pr, "LAST_KNOWN", tmp_path / "provider_last_known.json")

    def boom(*a, **k):
        raise pr.VaultUnavailable("the vault was rate-limited")

    monkeypatch.setattr(pr, "vault_secret", boom)
    p = mk("xai", "http://127.0.0.1:1", key_vault="Some Item", key_env=None)
    row = pr.probe(p, timeout=5)
    assert row["status"] == "vault", "expected the vault state, got %r" % row["status"]
    assert row["status"] != "failed"


def test_no_placeholder_credential_is_sent_to_a_hosted_api(monkeypatch):
    """A HOSTED API must never receive a placeholder bearer token.

    The old code sent 'nexus-local' when there was no key, which the provider
    answered with 'invalid_api_key' - a false diagnosis of bad credentials
    when the truth was that the vault would not give us one.
    """
    sent = {}

    def capture(url, payload, headers, timeout):
        sent["headers"] = dict(headers)
        return 401, {"error": {"code": "invalid_api_key", "message": "Incorrect API key provided"}}, None

    monkeypatch.setattr(pr, "_post", capture)
    monkeypatch.setattr(pr, "resolve_key", lambda p: None)
    p = mk("openai", "https://api.openai.com/v1", kind="openai", key_env=None, key_vault=None)
    with pytest.raises(RuntimeError):
        pr.call(p, "hello", max_tokens=16, timeout=5)
    assert "headers" not in sent, "a hosted API was called with no credential at all"
    assert sent.get("headers", {}).get("Authorization", "").lower() != "bearer nexus-local", \
        "a placeholder credential was sent to a hosted API"


def test_a_local_endpoint_still_accepts_the_placeholder(monkeypatch):
    """The NEXUS proxy is local and expects the well-known placeholder.

    The hosted-API fix must not break the local path.
    """
    sent = {}

    def capture(url, payload, headers, timeout):
        sent["headers"] = dict(headers)
        return 200, {"choices": [{"message": {"content": "ORCHESTRA OK"}}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1}}, None

    monkeypatch.setattr(pr, "_post", capture)
    monkeypatch.setattr(pr, "resolve_key", lambda p: None)
    p = mk("nexus", "http://127.0.0.1:8650/v1", kind="openai", key_env=None, key_vault=None,
           local=True)
    text, _ = pr.call(p, "hello", max_tokens=16, timeout=5)
    assert text == "ORCHESTRA OK"
    assert sent["headers"]["Authorization"] == "Bearer nexus-local"


def test_the_router_never_writes_a_plaintext_secret_to_disk(monkeypatch, tmp_path):
    """The DPAPI cache must not hold a plaintext secret."""
    monkeypatch.setattr(pr, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(pr, "_dpapi", lambda plain, protect=True: "CIPHER-" + plain[::-1])
    pr._cache_write("Some Item", "credential", "SUPER-SECRET-VALUE")
    for f in tmp_path.iterdir():
        blob = f.read_text(encoding="utf-8")
        assert "SUPER-SECRET-VALUE" not in blob, "a plaintext secret reached %s" % f.name


def test_a_real_response_updates_the_last_known_record(server, monkeypatch, tmp_path):
    """A state the provider was actually SEEN in is remembered."""
    lk = tmp_path / "provider_last_known.json"
    monkeypatch.setattr(pr, "LAST_KNOWN", lk)
    server.mode = "ok"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port)
    pr.probe(p)
    d = json.loads(lk.read_text(encoding="utf-8"))
    assert d["t"]["status"] == "healthy"
    assert d["t"]["seen_at"], "the record must say when the state was observed"


def test_the_last_known_record_holds_no_secret_material(server, monkeypatch, tmp_path):
    """The record must not carry the credential it was fetched with."""
    lk = tmp_path / "provider_last_known.json"
    monkeypatch.setattr(pr, "LAST_KNOWN", lk)
    server.mode = "ok"
    p = mk("t", "http://127.0.0.1:%d" % server.server_port, key_vault="Some Item")
    monkeypatch.setattr(pr, "vault_secret", lambda *a, **k: "SUPER-SECRET-VALUE")
    pr.probe(p)
    blob = lk.read_text(encoding="utf-8")
    assert "SUPER-SECRET-VALUE" not in blob, "the record contains the credential"


def test_no_test_writes_to_the_production_last_known_record():
    """A regression guard for the isolation of the last-known record.

    It lives in the same directory the dashboard reads, so a test provider
    would show up in the live provider panel. The autouse fixture redirects
    it; this asserts the redirect is in place.
    """
    import inspect
    src = inspect.getsource(pr.probe)
    assert "_remember" in src, "the probe must record the state it observed"
    fixture_src = inspect.getsource(isolated_ledger)
    assert "LAST_KNOWN" in fixture_src, "the autouse fixture must redirect LAST_KNOWN"
