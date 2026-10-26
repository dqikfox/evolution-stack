"""
Tests for the estate's provider-health check.

The rule this file protects: the estate must not report a healthy gate while
the model rotation is dead. A gate that cannot fail proves nothing, so the
negative control here is as important as the positive case.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, "E:/ultron-memory/evolution-stack")
from evo import bench  # noqa: E402

EVO = "E:/ultron-memory/evolution-stack"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"choices": [{"message": {"content": "ORCHESTRA OK"}}],
                           "usage": {"prompt_tokens": 5, "completion_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _fake_router(tmp_path, providers):
    """Write a router stub that reports the given provider states."""
    p = tmp_path / "provider_router.py"
    p.write_text(
        "def health(timeout=25):\n"
        "    return %r\n" % (providers,), encoding="utf-8")
    return p


def test_the_check_passes_with_enough_healthy_providers(tmp_path, monkeypatch):
    providers = [
        {"provider": "a", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "b", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "c", "model": "m", "status": "blocked", "error": "no credits", "note": "add credit"},
    ]
    p = _fake_router(tmp_path, providers)
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = bench.check_providers()
    by = {c.name: c for c in checks}
    assert by["providers:rotation"].passed
    assert by["providers:fallback_depth"].passed
    assert "2/3 healthy" in by["providers:rotation"].detail


def test_the_check_fails_when_only_one_provider_is_healthy(tmp_path, monkeypatch):
    """The floor is 2. One survivor means the fallback chain is a single point
    of failure, which is a degraded estate, not a healthy one."""
    providers = [
        {"provider": "a", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "b", "model": "m", "status": "blocked", "error": "no credits", "note": "x"},
    ]
    _fake_router(tmp_path, providers)
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = {c.name: c for c in bench.check_providers()}
    assert not checks["providers:rotation"].passed
    assert not checks["providers:fallback_depth"].passed


def test_the_check_fails_when_every_provider_is_dead(tmp_path, monkeypatch):
    providers = [
        {"provider": "a", "model": "m", "status": "failed", "error": "conn refused", "note": ""},
        {"provider": "b", "model": "m", "status": "failed", "error": "conn refused", "note": ""},
    ]
    _fake_router(tmp_path, providers)
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = {c.name: c for c in bench.check_providers()}
    assert not checks["providers:rotation"].passed


def test_a_blocked_provider_is_still_accounted_for(tmp_path, monkeypatch):
    """A blocked provider is a known state, not a failure - it must not fail
    the gate, and it must not be silently dropped."""
    providers = [
        {"provider": "a", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "b", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "c", "model": "m", "status": "blocked", "error": "no key", "note": "add a key"},
    ]
    _fake_router(tmp_path, providers)
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = {c.name: c for c in bench.check_providers()}
    assert checks["providers:accounted"].passed
    assert checks["providers:rotation"].passed
    assert "1 blocked" in checks["providers:rotation"].detail


def test_a_provider_with_no_state_and_no_error_is_unaccounted(tmp_path, monkeypatch):
    providers = [
        {"provider": "a", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "b", "model": "m", "status": "healthy", "error": None, "note": ""},
        {"provider": "ghost", "model": "m", "status": "unknown", "error": None, "note": ""},
    ]
    _fake_router(tmp_path, providers)
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = {c.name: c for c in bench.check_providers()}
    assert not checks["providers:accounted"].passed
    assert "ghost" in checks["providers:accounted"].detail


def test_a_missing_router_fails_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path / "nothing-here")
    checks = bench.check_providers()
    assert len(checks) == 1
    assert not checks[0].passed
    assert "missing" in checks[0].detail


def test_a_broken_router_does_not_crash_the_gate(tmp_path, monkeypatch):
    p = tmp_path / "provider_router.py"
    p.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setattr(bench.paths, "SCRIPTS_DIR", tmp_path)
    checks = bench.check_providers()
    assert not checks[0].passed
    assert "RuntimeError" in checks[0].detail


def test_the_check_is_registered_in_the_runner():
    """If this is not in the runner tuple, the check never runs and the gate
    says 100.0 while every provider is dead - the exact defect it prevents."""
    src = open(os.path.join(EVO, "evo", "bench.py"), encoding="utf-8").read()
    assert "check_providers" in src.split("def run(")[1]
