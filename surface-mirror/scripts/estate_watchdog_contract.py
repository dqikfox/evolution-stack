"""The estate's automatic recovery must actually run.

The house found this the hard way: BOTH scheduled tasks ran a bare
`python`, and a Scheduled Task runs with a minimal environment where
`python` does not resolve. Both had been failing with 0x80070002 (file
not found) while the scripts sat right there on disk. The only symptom
was a `Last Result` nobody read - and an outage that sat unattended.

These tests are the guard rail:

  * the tasks must name an ABSOLUTE interpreter (no PATH, no guessing),
  * the task wrappers must refuse to run with a missing interpreter or a
    missing script, rather than exiting 0 and looking healthy,
  * the watchdog's budget must EXCEED the launcher's own budget, or it
    kills the launcher mid-wait and the service never comes up,
  * and the watchdog must not fail the run for an operator-level service
    that has no start path - that is a task for a human, not an error.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERMES = Path(r"C:\Users\KING\AppData\Local\hermes")
SCRIPTS = HERMES / "scripts"
WATCHDOG = SCRIPTS / "estate_watchdog.py"
TASKS = ("THRONE_Watchdog_5min", "THRONE_Self_Evolution_Daemon")
ABSOLUTE_PYTHON = re.compile(r"[A-Za-z]:\\[\w\\\.\- ]*python\.exe", re.IGNORECASE)


def _task_action(name: str) -> str | None:
    """The 'Task To Run' line of a scheduled task, or None if unavailable."""
    if not shutil.which("schtasks"):
        return None
    result = subprocess.run(["schtasks", "/query", "/tn", name, "/fo", "LIST", "/v"],
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "Task To Run" in line:
            return line.split(":", 1)[1].strip()
    return None


def test_the_estate_watchdog_exists_and_is_valid_python():
    assert WATCHDOG.is_file(), f"the estate watchdog is missing: {WATCHDOG}"
    compile(WATCHDOG.read_text(encoding="utf-8"), str(WATCHDOG), "exec")


def test_the_watchdog_budget_exceeds_the_launcher_budget():
    """A watchdog that times out first kills the launcher mid-wait."""
    text = WATCHDOG.read_text(encoding="utf-8")
    match = re.search(r"^HEAL_WAIT\s*=\s*(\d+)", text, re.MULTILINE)
    assert match, "the watchdog must declare its heal budget"
    budget = int(match.group(1))
    # start_tesseract.cmd waits up to 180s for the health endpoint.
    assert budget > 180, (
        f"the watchdog's heal budget ({budget}s) must exceed the launcher's "
        f"own 180s wait, or the watchdog kills the launcher while it is still "
        f"waiting and the service never comes up"
    )


def test_the_watchdog_does_not_fail_the_run_for_an_operator_level_service():
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "operator-level" in text, (
        "a service with no start path is an operator task, not a failure - "
        "failing the run for it makes the task result meaningless"
    )


def test_the_task_wrappers_use_an_absolute_interpreter():
    for wrapper in ("watchdog_5min.cmd", "self_evolution_daemon.cmd"):
        path = SCRIPTS / wrapper
        assert path.is_file(), f"the task wrapper is missing: {path}"
        text = path.read_text(encoding="utf-8", errors="replace")
        assert ABSOLUTE_PYTHON.search(text), (
            f"{wrapper} must name an absolute interpreter - a Scheduled Task "
            f"runs with a minimal environment where a bare 'python' does not "
            f"resolve, and the task then fails with 0x80070002"
        )
        assert "if not exist" in text, (
            f"{wrapper} must refuse to run with a missing interpreter or "
            f"script instead of exiting 0 and looking healthy"
        )


def test_the_scheduled_tasks_name_an_absolute_interpreter():
    for name in TASKS:
        action = _task_action(name)
        if action is None:
            continue                       # schtasks unavailable here
        assert ABSOLUTE_PYTHON.search(action) or action.lower().endswith(".cmd"), (
            f"{name} runs {action!r} - a bare 'python' cannot be resolved by "
            f"a Scheduled Task, so the task dies with 0x80070002 and the "
            f"estate loses its automatic recovery"
        )
