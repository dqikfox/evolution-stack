"""Pytest entry point for the live launcher contract.

`launcher_contract.py` stops and RESTARTS the live services, so it is
not something a test run should do by accident. It is also not a pytest
module: it used to be named test_launchers.py, which pytest collected
ZERO items from - a file that looked like a passing test and tested
nothing. The name is now honest, and this wrapper makes the contract
visible to pytest without letting it run unattended.

Run it with:
    THRONE_RUN_LAUNCHER_CONTRACT=1 pytest tests/test_launcher_contract.py
or directly:
    python tests/launcher_contract.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
launcher_contract = pytest.importorskip("launcher_contract")


@pytest.mark.skipif(
    os.environ.get("THRONE_RUN_LAUNCHER_CONTRACT") != "1",
    reason="the launcher contract stops and restarts LIVE services; "
           "opt in with THRONE_RUN_LAUNCHER_CONTRACT=1",
)
def test_launcher_contract():
    assert launcher_contract.main() == 0, "the launcher contract failed"
