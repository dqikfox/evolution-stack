"""Tests for the peer model.

The rules worth protecting, in order of how much damage they do when
they break:

  * A peer that is unreachable is UNREACHABLE, not "down". The two
    look the same in a status list and mean opposite things: one can
    be healed, the other cannot be healed by anyone.
  * An unreachable peer is never healed. A heal that cannot possibly
    work is a slow way to fail, and it burns the watchdog's budget.
  * A reachable peer with a dead service IS healed, through the far
    side's own start task - never through a command invented here.
  * The registry shape is validated, because a registry that has
    drifted turns every probe into a confusing failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evo import peers, paths  # noqa: E402


REGISTRY = {
    "shadow": {
        "ip": "100.96.46.85",
        "user": "shadow",
        "key": "C:/keys/id_ed25519",
        "services": [
            {"name": "gateway", "port": 8644, "health": "http://127.0.0.1:8644/health",
             "heal_task": "Hermes_Gateway", "critical": True},
            {"name": "ollama", "port": 11434, "health": "http://127.0.0.1:11434/api/tags"},
        ],
    }
}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    path = tmp_path / "REMOTE_AGENTS.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(paths, "PEER_REGISTRY", path)
    return path


def _peer(registry):
    peers_found = peers.load()
    assert len(peers_found) == 1
    return peers_found[0]


# --- the registry -----------------------------------------------------------

def test_load_reads_the_registry(registry):
    peer = _peer(registry)
    assert peer.ip == "100.96.46.85"
    assert [s.name for s in peer.services] == ["gateway", "ollama"]
    assert peer.services[0].heal_task == "Hermes_Gateway"


def test_load_tolerates_an_absent_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PEER_REGISTRY", tmp_path / "nope.json")
    assert peers.load() == []


def test_load_tolerates_a_corrupt_registry(tmp_path, monkeypatch):
    bad = tmp_path / "REMOTE_AGENTS.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(paths, "PEER_REGISTRY", bad)
    assert peers.load() == []


def test_load_ignores_comment_keys(registry):
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["_comment"] = "not a peer"
    registry.write_text(json.dumps(data), encoding="utf-8")
    assert [p.name for p in peers.load()] == ["shadow"]


# --- the three states -------------------------------------------------------

def test_probe_reports_up_on_http_200(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "ssh_script", lambda *a, **k: (0, "HTTP 200 {\"ok\": true}", ""))
    state, detail = peers.probe(peer, peer.services[0])
    assert state == "up"
    assert "HTTP 200" in detail


def test_probe_reports_down_when_the_peer_answers_but_the_service_does_not(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "ssh_script", lambda *a, **k: (0, "DOWN connection refused", ""))
    state, detail = peers.probe(peer, peer.services[0])
    assert state == "down"
    assert "DOWN" in detail


def test_probe_reports_unreachable_when_the_peer_does_not_answer(registry, monkeypatch):
    """A closed port on the far side is not a dead service. The peer
    itself is gone, and the reason must say so."""
    peer = _peer(registry)
    monkeypatch.setattr(
        peers, "ssh_script",
        lambda *a, **k: (255, "", "ssh: connect to host 100.96.46.85 port 22: Connection timed out"))
    state, detail = peers.probe(peer, peer.services[0])
    assert state == "unreachable"
    assert "unreachable" in detail


def test_reachable_is_false_for_a_dark_peer(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "ssh_script", lambda *a, **k: (255, "", "Connection timed out"))
    ok, why = peers.reachable(peer)
    assert not ok
    assert "unreachable" in why


# --- the heal ---------------------------------------------------------------

def test_heal_refuses_an_unreachable_peer(registry, monkeypatch):
    """Nobody can start a service on a machine that cannot be reached.
    Trying is how a watchdog burns its budget on a lost cause."""
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (False, "the peer is unreachable"))
    ok, message = peers.heal(peer, peer.services[0])
    assert not ok
    assert "cannot heal" in message


def test_heal_needs_a_start_path(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (True, "reachable"))
    ok, message = peers.heal(peer, peer.services[1])  # ollama has no heal_task
    assert not ok
    assert "no start path" in message


def test_heal_uses_the_peers_own_start_task(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (True, "reachable"))
    calls = []

    def fake_ssh(p, script, timeout=45):
        calls.append(script)
        if "Start-ScheduledTask" in script:
            return 0, "started task Hermes_Gateway", ""
        return 0, "HTTP 200 ok", ""

    monkeypatch.setattr(peers, "ssh_script", fake_ssh)
    monkeypatch.setattr(peers.time, "sleep", lambda *_: None)
    ok, message = peers.heal(peer, peer.services[0])
    assert ok
    assert any("Hermes_Gateway" in c for c in calls)


# --- the survey -------------------------------------------------------------

def test_survey_marks_an_unreachable_peer_and_does_not_heal(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (False, "the peer is unreachable"))
    monkeypatch.setattr(peers, "probe", lambda *a, **k: pytest.fail("a dark peer must not be probed per service"))
    monkeypatch.setattr(peers, "heal", lambda *a, **k: pytest.fail("a dark peer must not be healed"))

    rows = peers.survey(auto_heal=True)
    assert len(rows) == 2
    for row in rows:
        assert row["status"] == "unreachable"
        assert row["peer_reachable"] is False
        assert row["healable"] is False


def test_survey_heals_a_down_service_on_a_reachable_peer(registry, monkeypatch):
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (True, "reachable"))
    monkeypatch.setattr(peers, "probe", lambda *a, **k: ("down", "DOWN refused"))

    healed = []

    def fake_heal(p, service, wait_s=40):
        healed.append(service.name)
        return True, "recovered: HTTP 200"

    monkeypatch.setattr(peers, "heal", fake_heal)
    rows = peers.survey(auto_heal=True)
    assert healed == ["gateway"]  # only the service that has a start path
    gateway = next(r for r in rows if r["name"] == "shadow/gateway")
    ollama = next(r for r in rows if r["name"] == "shadow/ollama")
    assert gateway["status"] == "up"
    assert "recovered" in gateway["healed"]
    assert ollama["status"] == "down"
    assert ollama["healable"] is False


def test_survey_rows_have_the_same_shape_as_a_local_survey(registry, monkeypatch):
    """One consumer reads both, so the keys must match."""
    peer = _peer(registry)
    monkeypatch.setattr(peers, "reachable", lambda *a, **k: (True, "reachable"))
    monkeypatch.setattr(peers, "probe", lambda *a, **k: ("up", "HTTP 200"))
    row = peers.survey()[0]
    for key in ("name", "port", "status", "kind", "healable", "critical", "detail", "elapsed"):
        assert key in row, key
    assert row["kind"] == "peer"
