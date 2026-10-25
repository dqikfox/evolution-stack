"""The house service helpers had no tests, and two of their promises were false.

1. `probe_http` could only say "something answered 200". A launcher that
   probes before it reclaims needs to say "MY service answered", because
   the two lead to different actions.

2. `service_control.reclaim` documented that "an unrelated process on the
   port is never touched", but the code only looked for a marker-matching
   SUPERVISOR. A service with no supervisor - a single detached process -
   is by definition an orphan, so the reclaim killed whatever held the
   port. The docstring was a promise the code did not keep.

These tests are hermetic: the process-tree decisions are exercised with
fakes, and the one test that touches a real socket binds a port in a
thread of this process.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HERMES = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "scripts"
MIRROR = Path(__file__).resolve().parents[1] / "surface-mirror" / "scripts"


def _load(name: str):
    """Prefer the live house copy; fall back to the published mirror."""
    for base in (HERMES, MIRROR):
        path = base / name
        if path.is_file():
            spec = importlib.util.spec_from_file_location("house_" + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    pytest.skip(f"{name} is neither in the house scripts nor in the mirror")


service_control = _load("service_control.py")
probe_http = _load("probe_http.py")


# --------------------------------------------------------------------------
# the marker matcher
# --------------------------------------------------------------------------

def test_marker_match_is_containment_for_an_orphan():
    # An orphan's command line has the script in the MIDDLE, with its
    # arguments after it - unlike a supervisor, whose line ENDS with it.
    cmd = r"C:\Users\KING\projects\pixel\server.py --port 8520"
    assert service_control.command_line_matches_marker(cmd, r"pixel\server.py")
    assert service_control.command_line_matches_marker(cmd, r"Pixel\Server.py")


def test_marker_match_rejects_a_stranger():
    cmd = r"C:\Users\KING\Projects\other\server.py --port 8520"
    assert not service_control.command_line_matches_marker(cmd, r"pixel\server.py")


def test_marker_match_rejects_an_empty_command_line():
    assert not service_control.command_line_matches_marker("", r"pixel\server.py")
    assert not service_control.command_line_matches_marker(None, r"pixel\server.py")


# --------------------------------------------------------------------------
# reclaim: a stranger on the port must survive
# --------------------------------------------------------------------------

def _fake_world(monkeypatch, holder_cmdline: str, holder_pid: int = 4321):
    """Point the reclaim at a single process holding the port."""
    chain = [{"ProcessId": holder_pid, "ParentProcessId": 9999,
              "Name": "python.exe", "CommandLine": holder_cmdline}]
    monkeypatch.setattr(service_control, "listener_pid", lambda port: holder_pid)
    monkeypatch.setattr(service_control, "chain_of", lambda pid: list(chain))
    monkeypatch.setattr(service_control, "supervisor_pids", lambda marker: [])
    killed = []
    monkeypatch.setattr(service_control.subprocess, "run",
                        lambda args, **kw: killed.append(args))
    return killed


def test_reclaim_refuses_to_kill_a_stranger(monkeypatch):
    killed = _fake_world(monkeypatch, r"C:\Windows\System32\somebodyelse.exe --port 8520")
    assert service_control.reclaim(8520, r"pixel\server.py") is False
    assert killed == [], "the reclaim tried to kill a process that is not ours"


def test_reclaim_kills_our_own_orphan(monkeypatch):
    killed = _fake_world(monkeypatch, r"C:\Users\KING\projects\pixel\server.py --port 8520")
    calls = {"n": 0}

    def fake_listener_pid(port):
        # the port is free once the kill has been issued
        calls["n"] += 1
        return None if calls["n"] > 1 else 4321

    monkeypatch.setattr(service_control, "listener_pid", fake_listener_pid)
    assert service_control.reclaim(8520, r"pixel\server.py") is True
    assert killed and "taskkill" in killed[0][0]


def test_stop_leaves_a_stranger_on_the_port_alone(monkeypatch):
    # The same promise applies to stop: our processes are stopped, but a
    # port held by something else is not taken from it.
    killed = _fake_world(monkeypatch, r"C:\Windows\System32\somebodyelse.exe --port 8520")
    monkeypatch.setattr(service_control, "descendants", lambda procs, roots: [])
    assert service_control.stop(r"pixel\server.py", port=8520) is True
    assert killed == [], "stop tried to kill a process that is not ours"


# --------------------------------------------------------------------------
# probe_http: which service answered
# --------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    body = b'{"activeCharacter": {"name": "Ryu"}}'

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def live_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d/api/state" % server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def test_probe_without_contains_only_checks_the_status(live_server):
    assert probe_http.main(["probe_http.py", live_server, "3"]) == 0


def test_probe_with_contains_accepts_the_right_service(live_server):
    assert probe_http.main(["probe_http.py", live_server, "3", "--contains", "activeCharacter"]) == 0


def test_probe_with_contains_rejects_the_wrong_service(live_server):
    assert probe_http.main(["probe_http.py", live_server, "3", "--contains", "nexus_core"]) == 1


def test_probe_reports_a_dead_port_as_down():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead = "http://127.0.0.1:%d/" % probe.getsockname()[1]
    assert probe_http.main(["probe_http.py", dead, "1"]) == 1
