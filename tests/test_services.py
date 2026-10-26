"""The service status must be body-aware, not a TCP connect.

A port that accepts a connection is not proof of health. The KRYSYS SPA
answers ``/health`` with its own shell, so a port check reports the shop
"up" while the API behind it is dead. The registry names the real route
(``/api/health``), and the status must be taken from that route's BODY.

These tests use an isolated local HTTP server on an ephemeral port. They
never touch a live service, and they never open a socket to the estate.
"""
from __future__ import annotations

import http.server
import threading

import pytest

from evo import services


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b'{"ok":true}'
    content_type = "application/json"
    status = 200

    def do_GET(self):  # noqa: N802 - the http.server API
        self.send_response(self.status)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):  # silence the server
        return


_SERVERS: list = []


def serve(payload: bytes, content_type: str = "application/json", status: int = 200) -> str:
    """Start a local server with a given body, and return its base URL.

    The server is closed by the `serve_cleanup` fixture, so nothing leaks
    between tests and nothing outside this module is contacted.
    """
    handler = type("H", (_Handler,), {"payload": payload, "content_type": content_type,
                                      "status": status})
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _SERVERS.append(srv)
    return "http://127.0.0.1:%d" % srv.server_address[1]


@pytest.fixture(autouse=True)
def serve_cleanup():
    """Close every local server this module started."""
    yield
    for srv in _SERVERS:
        srv.shutdown()
        srv.server_close()
    _SERVERS.clear()


def _service(name="t", port=0, health=None):
    return services.Service(
        name=name, port=port, status="up", start_type="none", start_path=None,
        start_args=None, start_interpreter=None, health=health, critical=False, notes="",
    )


def test_a_json_health_body_is_healthy():
    url = serve(b'{"ok":true,"service":"krysys"}') + "/api/health"
    assert services.health_body_ok(_service(health=url)) is True


def test_an_html_body_is_not_health():
    """The SPA shell. A 200 that serves a page is not a service reporting ready."""
    url = serve(b"<!DOCTYPE html><html><head><title>KRYSYS</title></head></html>",
                content_type="text/html") + "/health"
    assert services.health_body_ok(_service(health=url)) is False


def test_a_not_ready_payload_is_not_health():
    url = serve(b'{"status":"not_ready"}') + "/health"
    assert services.health_body_ok(_service(health=url)) is False


def test_an_ok_false_payload_is_not_health():
    url = serve(b'{"ok":false}') + "/health"
    assert services.health_body_ok(_service(health=url)) is False


def test_a_dead_route_is_not_health():
    """Nothing is listening on this port, so the body cannot be fetched."""
    assert services.health_body_ok(
        _service(health="http://127.0.0.1:1/health")) is False


def test_no_health_url_asserts_nothing_beyond_the_port():
    """A service with no documented health route keeps the old behaviour."""
    assert services.health_body_ok(_service(health=None)) is True


def test_status_of_reports_down_when_the_body_is_not_health():
    """The regression that started this: the port answers, the service does not."""
    payload = b"<!DOCTYPE html><html><title>KRYSYS</title></html>"
    url = serve(payload, content_type="text/html") + "/health"
    s = _service(health=url)
    # The port IS open - the server is listening on it.
    s.port = int(url.rsplit(":", 1)[1].split("/")[0])
    assert services.port_open(s.port) is True
    # ...and the status must still be "down", because the body is a page.
    assert services.status_of(s) == "down"


def test_status_of_reports_up_when_the_body_is_health():
    url = serve(b'{"ok":true}') + "/api/health"
    s = _service(health=url)
    s.port = int(url.rsplit(":", 1)[1].split("/")[0])
    assert services.status_of(s) == "up"


def test_a_retired_service_is_still_retired():
    s = _service(health="http://127.0.0.1:1/health")
    s.status = "retired"
    assert services.status_of(s) == "retired"


def test_the_registry_names_a_json_health_route_for_krysys():
    """The registry must point at the route that proves the service, not the
    route that proves a file was served."""
    reg = [s for s in services.load() if s.name == "krysys"]
    assert reg, "krysys must be in the registry"
    assert reg[0].health, "krysys must document a health route"
    assert reg[0].health.rstrip("/").endswith("/api/health"), (
        "krysys health must be the API route: %s" % reg[0].health)
