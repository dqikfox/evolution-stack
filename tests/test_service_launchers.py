"""A launcher must never destroy a service it could have left alone.

The house launchers had one order and it was the wrong one: reclaim the
port FIRST, then probe, and only afterwards check that the tools they
need even exist. That order has two failures baked into it.

1. The dependency checks came after the reclaim, so a launcher whose
   probe or reclaimer was missing tore down a working service and THEN
   reported the missing file. The service was down and the diagnosis was
   "a file is missing" - the opposite order of what a reader would guess.

2. The reclaim came before the probe, so the launcher decided what to do
   with the port before it knew whether the service was healthy.

The fix is one decision instead of two steps: `service_control.prepare`
probes the service, then answers a single question - free port, orphan
of ours, stranger, or healthy supervised chain - and only destroys
something when that is the only correct action.

These tests are hermetic. The launcher files are checked as source
(order is a property of the file), and the decision is exercised with
fakes.
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import pytest

HERMES = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "scripts"
MIRROR = Path(__file__).resolve().parents[1] / "surface-mirror" / "scripts"

LAUNCHERS = ("start_nexus.cmd", "start_tesseract.cmd", "start_pixel.cmd")


def _load(name: str):
    for base in (HERMES, MIRROR):
        path = base / name
        if path.is_file():
            spec = importlib.util.spec_from_file_location("house_" + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    pytest.skip(f"{name} is neither in the house scripts nor in the mirror")


service_control = _load("service_control.py")


def _launcher_text(name: str) -> str:
    for base in (HERMES, MIRROR):
        path = base / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    pytest.skip(f"{name} is not present")


# --------------------------------------------------------------- the order

@pytest.mark.parametrize("name", LAUNCHERS)
def test_a_launcher_checks_its_dependencies_before_it_touches_the_port(name):
    text = _launcher_text(name)
    decision = text.index("prepare --port")
    assert decision > 0, name
    after = text[decision:]
    assert "if not exist" not in after, (
        name + ": a dependency check sits AFTER the decision, so the launcher "
               "can destroy a working service and only then report a missing file")


@pytest.mark.parametrize("name", LAUNCHERS)
def test_a_launcher_never_reclaims_directly(name):
    """The reclaim is destructive. The launcher asks for a DECISION and
    lets the helper decide whether anything has to die."""
    text = _launcher_text(name)
    assert "reclaim --port" not in text, name + ": still reclaims without a decision"


@pytest.mark.parametrize("name", LAUNCHERS)
def test_a_launcher_probes_as_part_of_the_decision(name):
    text = _launcher_text(name)
    assert "--health" in text, name + ": the decision does not probe the service"


@pytest.mark.parametrize("name", LAUNCHERS)
def test_a_launcher_handles_every_outcome_of_the_decision(name):
    text = _launcher_text(name)
    assert '"%RC%"=="2"' in text, name + ": no branch for 'healthy and supervised'"
    assert '"%RC%"=="1"' in text, name + ": no branch for 'a stranger holds the port'"
    assert text.index("set RC=%ERRORLEVEL%") < text.index('"%RC%"=="2"'), (
        name + ": the exit code is read after it is used")


# ------------------------------------------------------------- the decision

class _Fakes:
    """The port state, injected."""

    def __init__(self, holder_pid=None, chain=None, supervisors=None,
                 ours=True, healthy=True):
        self.holder_pid = holder_pid
        self.chain = chain if chain is not None else (
            [{"ProcessId": holder_pid, "ParentProcessId": 1,
              "CommandLine": r"C:\x\pixel\server.py --port 8520"}] if holder_pid else [])
        self.supervisors = supervisors if supervisors is not None else []
        self.ours = ours
        self.healthy = healthy
        self.killed = []
        self.stopped = []


def _install(monkeypatch, fakes):
    monkeypatch.setattr(service_control, "listener_pid", lambda port: fakes.holder_pid)
    monkeypatch.setattr(service_control, "chain_of", lambda pid: fakes.chain)
    monkeypatch.setattr(service_control, "supervisor_pids", lambda marker: fakes.supervisors)
    monkeypatch.setattr(service_control, "command_line_matches_marker",
                        lambda cmd, marker: fakes.ours)
    monkeypatch.setattr(service_control, "chain_belongs_to_service",
                        lambda chain, marker: fakes.ours)
    monkeypatch.setattr(service_control, "_probe",
                        lambda url, contains=None, timeout=6: (fakes.healthy, "healthy"))
    # the port is free once the chain has been killed or stopped
    state = {"freed": False}

    def stop(marker, port):
        fakes.stopped.append((marker, port))
        state["freed"] = True
    monkeypatch.setattr(service_control, "stop", stop)

    def listener(port):
        return None if state["freed"] or fakes.holder_pid is None else fakes.holder_pid
    monkeypatch.setattr(service_control, "listener_pid", listener)
    monkeypatch.setattr(service_control.time, "sleep", lambda s: None)

    def run(cmd, **kw):
        fakes.killed.append(cmd)
        state["freed"] = True
        return _Completed()
    monkeypatch.setattr(service_control.subprocess, "run", run)


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def test_a_healthy_supervised_service_is_left_completely_alone(monkeypatch):
    # the real chain_of() returns the ANCESTORS too, so the supervisor is
    # part of the chain of the port owner
    fakes = _Fakes(holder_pid=100,
                   chain=[{"ProcessId": 100, "ParentProcessId": 10,
                           "CommandLine": r"C:\x\nexus_child.py"},
                          {"ProcessId": 10, "ParentProcessId": 1,
                           "CommandLine": r"C:\x\run_nexus.py"}],
                   supervisors=[{"ProcessId": 10, "ParentProcessId": 1,
                                 "CommandLine": r"C:\x\run_nexus.py"}])
    _install(monkeypatch, fakes)
    assert service_control.prepare(8650, "run_nexus.py", "http://x/health") == 2
    assert fakes.killed == [], "a healthy supervised service was destroyed"
    assert fakes.stopped == []


def test_an_orphan_of_ours_is_replaced(monkeypatch):
    fakes = _Fakes(holder_pid=100, ours=True)
    _install(monkeypatch, fakes)
    assert service_control.prepare(8520, "pixel_supervisor.py", "http://x/state") == 0
    assert fakes.killed, "the orphan was not reclaimed"


def test_a_stranger_is_never_touched(monkeypatch):
    fakes = _Fakes(holder_pid=100, ours=False)
    _install(monkeypatch, fakes)
    assert service_control.prepare(8520, "pixel_supervisor.py", "http://x/state") == 1
    assert fakes.killed == [], "a process that is not ours was killed"
    assert fakes.stopped == []


def test_a_supervised_but_silent_service_is_stopped_rather_than_duplicated(monkeypatch):
    """Two generations of one service is worse than one broken one, so a
    silent chain is stopped first and only then replaced."""
    fakes = _Fakes(holder_pid=100, healthy=False,
                   chain=[{"ProcessId": 100, "ParentProcessId": 10,
                           "CommandLine": r"C:\x\nexus_child.py"},
                          {"ProcessId": 10, "ParentProcessId": 1,
                           "CommandLine": r"C:\x\run_nexus.py"}],
                   supervisors=[{"ProcessId": 10, "ParentProcessId": 1,
                                 "CommandLine": r"C:\x\run_nexus.py"}])
    _install(monkeypatch, fakes)
    assert service_control.prepare(8650, "run_nexus.py", "http://x/health") == 0
    assert fakes.stopped == [("run_nexus.py", 8650)], (
        "the silent chain was not stopped before the launcher started another")


def test_a_free_port_means_start_and_touch_nothing(monkeypatch):
    fakes = _Fakes(holder_pid=None)
    _install(monkeypatch, fakes)
    assert service_control.prepare(8650, "run_nexus.py", "http://x/health") == 0
    assert fakes.killed == []
    assert fakes.stopped == []


def test_the_reclaim_still_answers_with_a_boolean(monkeypatch):
    """The old contract: reclaim() returns True/False. It must not change
    shape underneath the code that already calls it."""
    fakes = _Fakes(holder_pid=100, ours=False)
    _install(monkeypatch, fakes)
    assert service_control.reclaim(8520, "pixel_supervisor.py") is False
