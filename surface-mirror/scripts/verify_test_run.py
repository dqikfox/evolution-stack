"""Decide whether a background test result is CURRENT before you act on it.

A background notification can report a result from a tree that no longer
exists. That has happened three times in one session:

  * a NEXUS run reporting 39 passed while the live tree collected 54
  * a TESSERACT run reporting 325 passed while the live tree collected 337
  * a TESSERACT run reporting 325 passed and one warning, written 14
    hours earlier, for a bug fixed 7 hours before that

In every case the reported warning named a defect that was already gone.
Acting on the number would mean chasing a ghost.

This tool answers the only question that matters: is this result about the
tree that is on disk RIGHT NOW?

    python verify_test_run.py --log /tmp/tess.log --repo C:/path/to/repo

It compares three things and prints a verdict:

  1. the count in the log   (passed + skipped) against the count the live
     tree collects right now
  2. the log's mtime against the repo's most recent commit time - a result
     written before the last commit cannot describe the current tree
  3. the warnings in the log, so a CURRENT result still gets its warnings
     read

Exit codes:
  0  the result is CURRENT - the tree has not moved since the run
  1  the result is STALE   - the tree moved; the numbers describe another tree
  2  the result could not be judged (no summary line, unreadable log, or the
     repo does not look like a python project)
"""
from __future__ import annotations

import argparse
import os
import datetime
import re
import subprocess
import sys
from pathlib import Path

# "336 passed, 1 skipped in 274.36s (0:04:34)"
# "325 passed, 1 skipped, 1 warning in 273.28s (0:04:33)"
# "12 failed, 300 passed, 2 skipped in 61.0s"      <- pytest prints failures FIRST
SUMMARY = re.compile(r"^(?P<body>.*?)\s+in\s+(?P<seconds>[\d.]+)s")
COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped|warning|error|errors|xfailed|xpassed)")


def parse_summary(text: str) -> dict | None:
    """The LAST summary line - pytest prints one per run.

    The counts are read by keyword, not by position: pytest writes failures
    before passes ("12 failed, 300 passed"), and a tool that only matches
    the passing order silently returns nothing on exactly the runs you most
    need to read.
    """
    for line in reversed(text.splitlines()):
        m = SUMMARY.search(line.strip())
        if not m:
            continue
        counts = {}
        for number, word in COUNT.findall(m.group("body")):
            word = "warning" if word.startswith("warning") else (
                "error" if word.startswith("error") else word)
            counts[word] = counts.get(word, 0) + int(number)
        if not counts:
            continue
        out = {"passed": counts.get("passed", 0),
               "failed": counts.get("failed", 0),
               "skipped": counts.get("skipped", 0),
               "warnings": counts.get("warning", 0),
               "errors": counts.get("error", 0)}
        out["seconds"] = float(m.group("seconds"))
        return out
    return None


def collect_count(repo: Path) -> int | None:
    """How many tests does the tree collect right now?"""
    for exe in (repo / ".venv/Scripts/python.exe", repo / "venv/Scripts/python.exe"):
        if exe.is_file():
            break
    else:
        exe = None
    cmd = [str(exe) if exe else sys.executable, "-m", "pytest", "-q", "--collect-only",
           "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    m = re.search(r"(\d+)\s+tests? collected", proc.stdout)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+tests? collected", proc.stderr)
    return int(m.group(1)) if m else None


def last_commit_time(repo: Path) -> datetime.datetime | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=str(repo),
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return None
    if not out:
        return None
    try:
        return datetime.datetime.fromisoformat(out)
    except ValueError:
        return None


def _as_aware(dt: datetime.datetime | None) -> datetime.datetime | None:
    """Make a datetime comparable, whatever it arrived as.

    A naive datetime is interpreted as LOCAL time, which is what
    `fromtimestamp` produces on this host. The rule is the same one the
    estate gate follows: a UTC timestamp must never be read as local, and
    two datetimes must never be compared until both are the same kind of
    thing.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.astimezone()
    return dt


def mtime(path: Path) -> datetime.datetime | None:
    """The file's modification time, TIMEZONE-AWARE.

    The commit time comes from git as an aware datetime (%cI carries the
    offset), so a naive mtime cannot be compared with it: `naive < aware`
    raises TypeError. A verifier that crashes instead of judging is worse
    than no verifier, because the caller sees a stack trace and no
    verdict - and the temptation is to trust the run anyway.
    """
    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError:
        return None


def scratch_dir() -> Path:
    """Where the house keeps its scratch files. Overridable so it can be tested."""
    override = os.environ.get("HERMES_SCRATCH")
    if override:
        return Path(override)
    return Path.home() / "AppData/Local/hermes/cache/scratch"


def resolve_log(path: Path) -> Path | None:
    """Find the log, whatever shape the caller wrote it in.

    A shell hands out POSIX-looking paths (TMPDIR=/tmp/...), but a native
    Windows program reads /tmp as C:\\tmp and finds nothing. The Hermes
    scratch directory is the real home of these logs, so look there too.
    """
    if path.is_file():
        return path
    home = scratch_dir()
    candidates = [home / path.name]
    for env in ("TMPDIR", "TEMP", "TMP"):
        raw = os.environ.get(env)
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute() or candidate.parts[0] == "/":
            candidate = home / path.name
        else:
            candidate = candidate / path.name
        candidates.append(candidate)
    for c in candidates:
        if c.is_file():
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True, type=Path, help="the pytest output log to judge")
    ap.add_argument("--repo", required=True, type=Path, help="the repository the run was against")
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = ap.parse_args()

    log_path = resolve_log(args.log)
    if not log_path:
        print(f"no such log: {args.log} (looked in the Hermes scratch dir too)")
        return 2
    if not args.repo.is_dir():
        print(f"no such repo: {args.repo}")
        return 2

    text = log_path.read_text(encoding="utf-8", errors="replace")
    summary = parse_summary(text)
    if not summary:
        print(f"no pytest summary line in {args.log}")
        return 2

    ran = summary.get("passed", 0) + summary.get("skipped", 0) + summary.get("failed", 0)
    live = collect_count(args.repo)
    log_time = mtime(args.log)
    commit_time = last_commit_time(args.repo)

    reasons = []
    if live is not None and live != ran:
        reasons.append(f"the log reports {ran} tests, the live tree collects {live}")
    if log_time and commit_time and _as_aware(log_time) < _as_aware(commit_time):
        reasons.append(
            f"the log was written {log_time:%Y-%m-%d %H:%M}, before the last commit "
            f"({commit_time:%Y-%m-%d %H:%M})")
    if summary.get("failed"):
        reasons.append(f"the run had {summary['failed']} failures")

    stale = bool(reasons)
    warnings = summary.get("warnings", 0)
    if not stale and warnings:
        reasons.append(f"the run reported {warnings} warning(s) - read them, the tree has not moved")

    verdict = "STALE" if stale else "CURRENT"
    payload = {
        "verdict": verdict,
        "log": str(args.log),
        "repo": str(args.repo),
        "reported": summary,
        "collected_now": live,
        "log_mtime": log_time.isoformat() if log_time else None,
        "last_commit": commit_time.isoformat() if commit_time else None,
        "reasons": reasons,
    }
    if args.json:
        import json
        print(json.dumps(payload, indent=1))
    else:
        print(f"  verdict : {verdict}")
        print(f"  log     : {args.log}  ({ran} tests reported, {warnings} warning(s))")
        print(f"  tree    : {args.repo}  ({live if live is not None else '?'} tests collected now)")
        for r in reasons:
            print(f"  - {r}")
        if stale:
            print("  -> the numbers describe an older tree. Do not act on them;")
            print("     re-run the suite against the current tree instead.")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
