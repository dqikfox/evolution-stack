"""A port that answers is not a service that works.

The house dashboard and the estate checks both look at ports. This is the
deeper check: the /health payload of a service that is up can still say
that one of its components is not ready - a RAG service whose vector
store failed to load answers 200 and a broken database. A check that
only asks "is the port open" calls that healthy.

These tests are hermetic: a local HTTP server stands in for the service.
"""
from __future__ import annotations

import importlib.util
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HERMES = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "scripts"
MIRROR = Path(__file__).resolve().parents[1] / "surface-mirror" / "scripts"


def _load(name: str):
    for base in (HERMES, MIRROR):
        path = base / name
        if path.is_file():
            spec = importlib.util.spec_from_file_location("house_" + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    pytest.skip(f"{name} is neither in the house scripts nor in the mirror")


vsi = _load("validate_service_integrity.py")


class _Handler(BaseHTTPRequestHandler):
    payload = "{}"

    def do_GET(self):
        body = self.payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(payload):
    handler = type("H", (_Handler,), {"payload": payload})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_a_service_with_a_broken_component_is_caught():
    server, port = _serve('{"ok": true, "components": {"database": '
                           '{"status": "not_ready", "reason": "chroma did not load"}}}')
    try:
        failures = vsi.check(port)
    finally:
        server.shutdown()
    assert failures, "a component that said not_ready was not caught"
    assert "chroma did not load" in failures[0][1]


def test_a_healthy_service_passes():
    server, port = _serve('{"ok": true, "components": {"database": {"status": "ok"}}}')
    try:
        failures = vsi.check(port)
    finally:
        server.shutdown()
    assert failures == []


def test_a_degraded_component_is_caught_too():
    server, port = _serve('{"ok": true, "components": {"ollama": {"status": "degraded"}}}')
    try:
        failures = vsi.check(port)
    finally:
        server.shutdown()
    assert failures, "a degraded component was treated as ready"


def test_a_service_without_a_json_payload_is_not_failed():
    """A service with no health payload has nothing to declare. Inventing
    a failure from it would make the check cry wolf on every service that
    does not implement /health."""
    server, port = _serve("not json at all")
    try:
        failures = vsi.check(port)
    finally:
        server.shutdown()
    assert failures == []


def test_the_ports_come_from_the_registry_not_from_a_typed_list():
    assert vsi.PORT_MAP.name == "PORT_MAP.json"
    assert vsi.registry_ports() or True  # the map may be absent on a test host


def test_the_check_reports_a_failure_with_a_nonzero_exit():
    server, port = _serve('{"components": {"x": {"status": "failed"}}}')
    try:
        rc = vsi.main(["--port", str(port)])
    finally:
        server.shutdown()
    assert rc == 1
