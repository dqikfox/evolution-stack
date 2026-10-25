"""A background test result can describe a tree that no longer exists.

It happened three times in one session: a NEXUS run reported 39 passed
while the live tree collected 54; a TESSERACT run reported 325 passed
while the live tree collected 337; and a TESSERACT run reported a warning
that had been fixed seven hours earlier. Every one of them looked like a
live problem, and every one of them was a ghost.

`verify_test_run.py` exists so that judgement is made by a tool and
recorded, rather than re-derived from scratch each time a notification
arrives. These tests pin the three decisions it makes:

  1. the count in the log against the count the tree collects now
  2. the log's write time against the repo's last commit
  3. warnings are surfaced when - and only when - the result is current

Hermetic: no repository is touched. The tree facts are injected.
"""
from __future__ import annotations

import importlib.util
import os
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


vtr = _load("verify_test_run.py")


# ---------------------------------------------------------------- parsing

def test_parses_a_plain_summary():
    got = vtr.parse_summary("336 passed, 1 skipped in 274.36s (0:04:34)")
    assert got["passed"] == 336
    assert got["skipped"] == 1
    assert got["warnings"] == 0
    assert got["failed"] == 0
    assert got["seconds"] == pytest.approx(274.36)


def test_parses_a_summary_with_warnings():
    got = vtr.parse_summary("325 passed, 1 skipped, 1 warning in 273.28s (0:04:33)")
    assert (got["passed"], got["skipped"], got["warnings"]) == (325, 1, 1)


def test_parses_a_summary_with_failures():
    got = vtr.parse_summary("12 failed, 300 passed, 2 skipped in 61.0s")
    assert got["failed"] == 12
    assert got["passed"] == 300


def test_takes_the_last_summary_line():
    """pytest prints a summary per run; the last one is the one that counts."""
    text = "336 passed in 10.0s\n325 passed, 1 skipped, 1 warning in 273.28s\n"
    assert vtr.parse_summary(text)["passed"] == 325


def test_no_summary_is_none():
    assert vtr.parse_summary("collection error, no tests ran") is None


# -------------------------------------------------------------- log lookup

def test_resolve_log_finds_a_file_reached_by_a_posix_style_path(tmp_path, monkeypatch):
    """TMPDIR is handed to shells as /tmp/..., which native python reads as C:\\tmp."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    log = scratch / "run.log"
    log.write_text("336 passed in 1.0s", encoding="utf-8")
    monkeypatch.setenv("TMPDIR", "/tmp/")
    monkeypatch.setenv("HERMES_SCRATCH", str(scratch))

    got = vtr.resolve_log(Path("/tmp/run.log"))
    assert got is not None and got.name == "run.log"


def test_resolve_log_returns_none_for_a_missing_log(tmp_path):
    assert vtr.resolve_log(tmp_path / "nope.log") is None


# ----------------------------------------------------------------- verdict

def _run(monkeypatch, tmp_path: Path, log_text: str, collected: int | None,
        commit_time=None, log_time=None):
    """Drive main() with the tree facts injected, so no repo is touched."""
    import datetime
    log = tmp_path / "run.log"
    log.write_text(log_text, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)

    monkeypatch.setattr(vtr, "collect_count", lambda _repo: collected)
    monkeypatch.setattr(vtr, "last_commit_time",
                        lambda _r: commit_time or datetime.datetime(2026, 10, 25, 12, 0))
    monkeypatch.setattr(vtr, "mtime", lambda _p: log_time or datetime.datetime(2026, 10, 25, 18, 0))
    monkeypatch.setattr(vtr, "resolve_log", lambda p: p if p.is_file() else None)
    monkeypatch.setattr(sys, "argv", ["verify_test_run.py", "--log", str(log), "--repo", str(repo)])
    return vtr.main()


def test_a_count_mismatch_is_stale(monkeypatch, tmp_path):
    code = _run(monkeypatch, tmp_path, "325 passed, 1 skipped, 1 warning in 273.28s", collected=337)
    assert code == 1


def test_a_matching_count_is_current(monkeypatch, tmp_path):
    code = _run(monkeypatch, tmp_path, "336 passed, 1 skipped in 274.36s", collected=337)
    assert code == 0


def test_a_log_written_before_the_last_commit_is_stale(monkeypatch, tmp_path):
    """Same count, but the tree moved afterwards: the result is still history."""
    import datetime
    code = _run(monkeypatch, tmp_path, "337 passed in 10.0s", collected=337,
                commit_time=datetime.datetime(2026, 10, 25, 19, 0),
                log_time=datetime.datetime(2026, 10, 25, 18, 0))
    assert code == 1


def test_a_failure_is_never_current(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, "12 failed, 300 passed in 61.0s", collected=337) == 1


def test_an_unreadable_log_is_exit_two(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, "no summary here", collected=337) == 2


def test_warnings_are_surfaced_when_the_result_is_current(monkeypatch, tmp_path, capsys):
    """A current result's warnings must still be read, not swallowed."""
    code = _run(monkeypatch, tmp_path, "336 passed, 1 skipped, 2 warnings in 10.0s", collected=337)
    assert code == 0
    assert "warning" in capsys.readouterr().out


# ------------------------------------------------------------- time zones
# The thirteen tests above injected NAIVE datetimes on both sides, so the
# comparison worked in the test and CRASHED in production: git returns an
# aware commit time (%cI carries the offset) while a file mtime is naive.
# `naive < aware` raises TypeError, so the verifier produced a stack trace
# instead of a verdict - and a caller holding a stack trace is a caller
# who ends up trusting the run anyway.

def test_a_naive_log_time_against_an_aware_commit_time_does_not_crash(monkeypatch, tmp_path):
    """The real production combination must return a verdict, not raise."""
    import datetime
    aware = datetime.datetime(2026, 10, 25, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=10)))
    code = _run(monkeypatch, tmp_path, "337 passed in 10.0s", collected=337,
                commit_time=aware,
                log_time=datetime.datetime(2026, 10, 25, 18, 0))
    assert code in (0, 1), "the verifier must judge, not crash"


def test_a_naive_log_before_an_aware_commit_is_stale(monkeypatch, tmp_path):
    import datetime
    aware = datetime.datetime(2026, 10, 25, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=10)))
    code = _run(monkeypatch, tmp_path, "337 passed in 10.0s", collected=337,
                commit_time=aware,
                log_time=datetime.datetime(2026, 10, 25, 18, 0))
    assert code == 1, "the tree moved after the log was written"


def test_mtime_is_timezone_aware(tmp_path):
    """A file mtime must be aware, because git's commit time is."""
    log = tmp_path / "run.log"
    log.write_text("337 passed in 10.0s", encoding="utf-8")
    got = vtr.mtime(log)
    assert got is not None
    assert got.tzinfo is not None, "a naive mtime cannot be compared with git's aware time"


def test_as_aware_normalizes_a_naive_datetime():
    import datetime
    naive = datetime.datetime(2026, 10, 25, 18, 0)
    assert vtr._as_aware(naive).tzinfo is not None
    assert vtr._as_aware(None) is None


def test_two_datetimes_of_mixed_awareness_can_be_compared():
    import datetime
    naive = datetime.datetime(2026, 10, 25, 18, 0)
    aware = datetime.datetime(2026, 10, 25, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=10)))
    assert vtr._as_aware(naive) < vtr._as_aware(aware)

