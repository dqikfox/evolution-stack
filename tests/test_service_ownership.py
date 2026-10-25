"""A service's identity is not always on the process that holds the port.

The house found this at 20:30 on a live estate: TESSERACT's supervisor
had died, leaving its uvicorn child holding :8705. The child was a bare
uv python - no project token anywhere in its command line - and the
reclaim, which only looked at the HOLDER, refused to touch "our own"
orphan. The launcher then failed with "could not reclaim :8705", and the
service could not be restarted at all: a dead supervisor had taken the
whole service down with it, and the tooling refused to clear the corpse.

The identity lives in the ANCESTRY: the venv shim
(TESSERACT\\.venv\\Scripts\\python.exe) is the parent and carries the
project.

But the fix must not become a loophole. A stranger on the port is still
never touched, so the chain check only counts INTERPRETER members - a
shell whose command line merely mentions the project (a transcript
command, a grep) must never make a stranger look like our service.
"""
from __future__ import annotations

import importlib.util
import os
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


service_control = _load("service_control.py")

MARKER = r"TESSERACT\start.py"


def _proc(name: str, cmd: str, pid: int = 100, ppid: int = 1) -> dict:
    return {"Name": name, "CommandLine": cmd, "ProcessId": pid, "ParentProcessId": ppid}


def test_the_holder_itself_still_matches_the_marker():
    assert service_control.command_line_matches_marker(
        r"C:\Users\KING\Projects\TESSERACT\.venv\Scripts\python.exe C:\Users\KING\Projects\TESSERACT\start.py",
        MARKER)


def test_the_project_token_matches_a_bare_interpreter_of_our_project():
    """The marker's project token is enough - it is service specific."""
    assert service_control.command_line_matches_marker(
        r"C:\Users\KING\AppData\Local\hermes\logs\tesseract_logconfig.json", MARKER)


def test_a_stranger_is_still_refused():
    assert not service_control.command_line_matches_marker(
        r"C:\Program Files\Some Other Server\server.exe --port 8705", MARKER)


def test_an_empty_command_line_matches_nothing():
    assert not service_control.command_line_matches_marker("", MARKER)


def test_the_chain_recognises_our_own_orphan():
    """The holder carries no token; its interpreter parent does."""
    chain = [
        _proc("python.exe",
              r"C:\Users\KING\AppData\Roaming\uv\python\cpython-3.14\python.exe -m uvicorn "
              r"server:app --host=127.0.0.1 --port=8705", pid=333480, ppid=296428),
        _proc("python.exe",
              r"C:\Users\KING\Projects\TESSERACT\.venv\Scripts\python.exe -m uvicorn "
              r"server:app --host=127.0.0.1 --port=8705", pid=296428, ppid=1),
    ]
    assert service_control.chain_belongs_to_service(chain, MARKER)


def test_a_stranger_chain_is_refused():
    chain = [
        _proc("python.exe", r"C:\Python311\python.exe some_other_service.py --port 8705", pid=2, ppid=3),
        _proc("cmd.exe", r"C:\Windows\System32\cmd.exe /c other.cmd", pid=3, ppid=4),
    ]
    assert not service_control.chain_belongs_to_service(chain, MARKER)


def test_a_shell_that_merely_mentions_the_project_is_not_enough():
    """A transcript command that mentions TESSERACT must not claim the port."""
    chain = [
        _proc("python.exe", r"C:\Python311\python.exe stranger.py --port 8705", pid=2, ppid=3),
        _proc("bash.exe",
              r"C:\Program Files\Git\bin\bash.exe -c cd /c/Users/KING/Projects/TESSERACT && pytest",
              pid=3, ppid=4),
    ]
    assert not service_control.chain_belongs_to_service(chain, MARKER)
