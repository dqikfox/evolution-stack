"""Orchestrating a REMOTE Hermes agent needs its own discipline.

The remote channels are real and they fail differently from the local
ones. A name that is not registered must not be guessed at. A peer's
identity lives in its ANCESTRY, not in the process holding the port. A
PowerShell script sent through ssh has three layers of quoting between
it and the code, so it travels as an encoded file, not as a string.

These tests are hermetic: no host is contacted, no tunnel is opened.
The facts are injected.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
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


hr = _load("hermes_remote.py")


HOST = {"name": "shadow", "tailnet_name": "ultron-brain", "ip": "100.96.46.85",
        "user": "shadow", "key": "E:/keys/id_ed25519", "platform_port": 8644}


# ------------------------------------------------------------------ registry

def test_an_unregistered_host_is_refused_not_guessed(monkeypatch):
    monkeypatch.setattr(hr, "load_registry", lambda: {"shadow": HOST})
    with pytest.raises(SystemExit):
        hr.resolve_host("nonexistent")


def test_a_host_is_found_by_its_tailnet_name(monkeypatch):
    monkeypatch.setattr(hr, "load_registry", lambda: {"shadow": HOST})
    assert hr.resolve_host("ultron-brain")["ip"] == "100.96.46.85"


def test_the_real_registry_is_valid_and_complete():
    path = Path(hr.REGISTRY)
    if not path.is_file():
        pytest.skip("no remote agent registry on this host")
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, host in data.items():
        if name.startswith("_"):
            continue
        for field in ("ip", "user", "key"):
            assert host.get(field), f"{name} has no {field}"


# --------------------------------------------------------------------- ssh

def test_the_remote_script_travels_as_encoded_utf16():
    """Three shells sit between the code and the host; a quoted string
    loses something in every one of them."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        hr.ssh_command(HOST, "Write-Host 'héllo'", timeout=5)
    finally:
        monkey.undo()
    encoded = captured["cmd"][captured["cmd"].index("-EncodedCommand") + 1]
    script = base64.b64decode(encoded).decode("utf-16-le")
    assert script == "Write-Host 'héllo'"


def test_ssh_uses_the_registered_user_and_key(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        hr.ssh_command(HOST, "hostname", timeout=5)
    finally:
        monkey.undo()
    cmd = captured["cmd"]
    assert "shadow@100.96.46.85" in cmd
    assert "E:/keys/id_ed25519" in cmd
    assert "BatchMode=yes" in cmd, "a prompt would hang the house"


def test_a_timeout_is_reported_not_raised(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        rc, out, err = hr.ssh_command(HOST, "sleep 100", timeout=5)
    finally:
        monkey.undo()
    assert rc == 124
    assert "exceeded" in err


# ------------------------------------------------------------------ output

def test_the_clixml_noise_is_stripped():
    raw = "real output\n#< CLIXML\n<Objs Version=\"1.1\"><Obj /></Objs>\nmore noise"
    assert hr._clean(raw) == "real output"


def test_the_clients_own_post_quantum_warning_is_stripped():
    raw = ("** WARNING: connection is not using a post-quantum key exchange algorithm.\n"
           "** This session may be vulnerable.\n"
           "the answer\n")
    assert hr._clean(raw) == "the answer"


# --------------------------------------------------------------- tailnet

def test_a_peer_is_matched_by_ip_not_by_name(monkeypatch):
    """The tailnet records the name a node REGISTERED under, which is not
    the hostname the node reports. Only the IP identifies the machine."""
    payload = json.dumps({"Peer": {
        "nodekey:1": {"HostName": "ultron-brain", "Online": True,
                      "LastSeen": "0001-01-01T00:00:00Z", "OS": "windows",
                      "TailscaleIPs": ["100.96.46.85"]}}})

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, payload, "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        state = hr.tailscale_state(HOST)
    finally:
        monkey.undo()
    assert "ultron-brain" in state
    assert "online=True" in state


def test_a_peer_that_is_not_in_the_tailnet_says_so(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"Peer": {}}), "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        assert "not in the tailnet" in hr.tailscale_state(HOST)
    finally:
        monkey.undo()


# ------------------------------------------------------------------- cli

def test_exec_without_a_command_is_refused(monkeypatch):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(sys, "argv", ["hermes_remote.py", "exec", "--host", "shadow"])
    monkey.setattr(hr, "load_registry", lambda: {"shadow": HOST})
    try:
        with pytest.raises(SystemExit):
            hr.main()
    finally:
        monkey.undo()


def test_tunnel_without_a_port_is_refused(monkeypatch):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(sys, "argv", ["hermes_remote.py", "tunnel", "--host", "shadow"])
    monkey.setattr(hr, "load_registry", lambda: {"shadow": HOST})
    try:
        with pytest.raises(SystemExit):
            hr.main()
    finally:
        monkey.undo()


def test_a_script_that_does_not_exist_is_refused(monkeypatch, tmp_path):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr, "load_registry", lambda: {"shadow": HOST})
    try:
        with pytest.raises(SystemExit):
            hr.cmd_script(HOST, tmp_path / "nope.ps1", timeout=5)
    finally:
        monkey.undo()


def test_a_script_is_uploaded_not_piped(monkeypatch):
    """The script must not travel over the channel as stdin.

    The far side has to read its stdin to EOF. When the client gives up
    first, the remote process is left reading a pipe that will never
    close: it holds its session, it holds its temp file, and every
    later connection is starved behind it. A timeout then costs the
    channel, not just the run. So the script is uploaded, run, and
    removed - three short sessions, none of them blocking on stdin.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        hr.ssh_script(HOST, "Write-Output 'x'\n", timeout=5)
    finally:
        monkey.undo()

    for cmd, kwargs in calls:
        assert kwargs.get("input") is None, "a script was piped over stdin"
    assert any(c[0][0].lower().endswith("scp") or c[0][0].lower().endswith("scp.exe")
               for c in calls), "the script was never uploaded"
    assert any("-File" in c[0] for c in calls), "the uploaded script was never run"


def test_the_remote_copy_is_removed_even_when_the_run_fails(monkeypatch):
    """A file left on the remote is litter that outlives the tool."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "-File" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        rc, out, err = hr.ssh_script(HOST, "Write-Output 'x'\n", timeout=5)
    finally:
        monkey.undo()
    assert rc == 1
    assert any("Remove-Item" in " ".join(c) for c in calls), "the remote copy was left behind"


def test_the_script_name_is_unique_per_run(monkeypatch):
    """Two runs must not fight over one file name - the loser blocks on
    the lock and the channel looks broken."""
    names = []

    def fake_run(cmd, **kwargs):
        for part in cmd:
            if part.endswith(".ps1"):
                names.append(part)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hr.subprocess, "run", fake_run)
    try:
        hr.ssh_script(HOST, "Write-Output 'x'\n", timeout=5)
        hr.ssh_script(HOST, "Write-Output 'y'\n", timeout=5)
    finally:
        monkey.undo()
    assert names, "no script file was named"
    assert len(set(names)) == len(names), "two runs shared a file name"
