"""The scout:fresh gate must not lie about its own input.

Two real defects were found here:

  1. The scout writes its timestamp in UTC, but the gate parsed the
     naive part with time.mktime(), which reads it as LOCAL time. On a
     UTC+11 host a report written ten minutes ago was reported as
     eleven hours old - the gate hid a fresh report and invented a
     stale one.
  2. The report file lives in a directory another system owns. When the
     file was missing the gate said "no report", which reads as "the
     scout did not run". The append-only log carries the same
     timestamp, so the gate can know the truth.

These tests use a temporary directory and never touch the live report.

Run:  python -m pytest tests/test_bench_scout.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evo import bench, paths  # noqa: E402


def _scout_check(tmp_path: Path, monkeypatch) -> bench.Check:
    report = tmp_path / "evolution_scout.json"
    log = tmp_path / "evolution_scout.log"
    monkeypatch.setattr(paths, "SCOUT_REPORT", report)
    monkeypatch.setattr(paths, "SCOUT_LOG", log)
    for c in bench.check_scout():
        if c.name == "scout:fresh":
            return c
    raise AssertionError("the bench produced no scout:fresh check")


def _write_report(path: Path, ts: str, findings: int = 0) -> None:
    path.write_text(json.dumps({"ts": ts, "finding_count": findings}), encoding="utf-8")


def _write_log(path: Path, ts: str, findings: int = 0) -> None:
    path.write_text(f"[{ts}] findings={findings} high=0\n", encoding="utf-8")


def test_fresh_report_is_not_misread_as_eleven_hours_old(tmp_path, monkeypatch):
    """A report written minutes ago must read as minutes old.

    This is the regression: the timestamp is UTC, the host is UTC+11.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    _write_report(tmp_path / "evolution_scout.json", ts, findings=1)
    c = _scout_check(tmp_path, monkeypatch)
    assert c.passed, c.detail
    assert "0h old" in c.detail, f"a just-written report was misreported: {c.detail}"
    assert "from report" in c.detail, c.detail


def test_missing_report_falls_back_to_the_log(tmp_path, monkeypatch):
    """A deleted report file does not mean the scout did not run."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    _write_log(tmp_path / "evolution_scout.log", ts, findings=2)
    c = _scout_check(tmp_path, monkeypatch)
    assert c.passed, c.detail
    assert "from log" in c.detail, c.detail
    assert "2 findings" in c.detail, c.detail


def test_no_report_and_no_log_is_a_real_failure(tmp_path, monkeypatch):
    c = _scout_check(tmp_path, monkeypatch)
    assert not c.passed
    assert "no report and no log entry" in c.detail, c.detail


def test_stale_report_is_a_failure(tmp_path, monkeypatch):
    ts = datetime.now(timezone.utc) - timedelta(days=4)
    _write_report(tmp_path / "evolution_scout.json",
                  ts.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"))
    c = _scout_check(tmp_path, monkeypatch)
    assert not c.passed, c.detail


def test_stale_log_is_a_failure_when_the_report_is_gone(tmp_path, monkeypatch):
    ts = datetime.now(timezone.utc) - timedelta(days=4)
    _write_log(tmp_path / "evolution_scout.log",
               ts.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"))
    c = _scout_check(tmp_path, monkeypatch)
    assert not c.passed, c.detail


def test_a_timestamp_in_the_future_is_not_fresh(tmp_path, monkeypatch):
    """A clock that is ahead must not buy the gate a pass."""
    ts = datetime.now(timezone.utc) + timedelta(hours=2)
    _write_report(tmp_path / "evolution_scout.json",
                  ts.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"))
    c = _scout_check(tmp_path, monkeypatch)
    assert not c.passed, c.detail
    assert "future" in c.detail, c.detail
