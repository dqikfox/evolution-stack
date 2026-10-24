"""
safe_commit.py - commit a managed repo without stealing work in progress.

The autonomous evolution worker is allowed to commit a dirty managed repo
(TESSERACT, lumming, pixel, pathwaytoscripture) so the repos do not drift.
That is a good rule, and it has a hole: "dirty" does not mean "finished".
A file that another session is writing right now is dirty too, and
committing it captures a half-written file into history.

So this script refuses to stage anything that was modified recently, and
can run a check command first so the commit is only made against content
that is known to work.

Usage:
    python safe_commit.py --repo C:/Users/KING/Projects/TESSERACT \\
        --message "..." [--push] [--min-age 15] [--check "pytest -q"]

Exit codes:
    0  committed (or nothing to do)
    1  refused: a file is in motion, or the check failed, or git failed
    2  bad usage
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

NEVER_STAGE = {".env", ".env.oprefs", "secrets.json", "credentials.json"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
             "Library", "Temp", "obj", "bin", "build"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=300)


def _changed_files(repo: Path) -> list[Path]:
    out = _git(repo, "status", "--porcelain").stdout
    files: list[Path] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip().strip('"')
        if " -> " in rel:  # renamed
            rel = rel.split(" -> ")[-1].strip().strip('"')
        p = (repo / rel)
        if p.exists():
            files.append(p)
    return files


def _in_motion(paths: list[Path], max_age_minutes: float) -> list[tuple[Path, float]]:
    cutoff = time.time() - (max_age_minutes * 60)
    moving = []
    for p in paths:
        try:
            age = (time.time() - p.stat().st_mtime) / 60.0
        except OSError:
            continue
        if p.stat().st_mtime > cutoff:
            moving.append((p, age))
    return moving


def _should_skip(p: Path) -> bool:
    if p.name in NEVER_STAGE:
        return True
    return any(part in SKIP_DIRS for part in p.parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--message", required=True)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--min-age", type=float, default=15.0,
                    help="refuse to stage a file modified within this many minutes")
    ap.add_argument("--check", default="", help="shell command that must succeed before committing")
    ap.add_argument("--force", action="store_true", help="ignore the in-motion check")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"safe_commit: {repo} is not a git repository", file=sys.stderr)
        return 2

    changed = [p for p in _changed_files(repo) if not _should_skip(p)]
    skipped = [p for p in _changed_files(repo) if _should_skip(p)]
    if not changed:
        print("safe_commit: nothing to commit")
        if skipped:
            print(f"safe_commit: {len(skipped)} file(s) skipped as secrets/build output")
        return 0

    moving = _in_motion(changed, args.min_age)
    if moving and not args.force:
        print("safe_commit: REFUSING - these files were modified in the last "
              f"{args.min_age:g} minute(s) and may be in progress:", file=sys.stderr)
        for p, age in moving:
            print(f"  {p}  ({age:.1f} min old)", file=sys.stderr)
        print("safe_commit: another session is probably writing them. "
              "Wait, or pass --force if you are certain.", file=sys.stderr)
        return 1

    if args.check:
        print(f"safe_commit: running check: {args.check}")
        rc = subprocess.run(args.check, shell=True, cwd=str(repo),
                            capture_output=True, text=True, timeout=1800)
        if rc.returncode != 0:
            print("safe_commit: REFUSING - the check failed", file=sys.stderr)
            print((rc.stdout or "")[-2000:], file=sys.stderr)
            print((rc.stderr or "")[-2000:], file=sys.stderr)
            return 1
        print("safe_commit: check passed")

    # explicit paths only - never `git add -A`
    rels = [str(p.relative_to(repo)).replace("\\", "/") for p in changed]
    add = _git(repo, "add", "--", *rels)
    if add.returncode != 0:
        print("safe_commit: git add failed:\n" + add.stderr, file=sys.stderr)
        return 1

    staged = _git(repo, "diff", "--cached", "--name-only").stdout.split()
    if not staged:
        print("safe_commit: nothing staged")
        return 0

    commit = _git(repo, "commit", "-m", args.message)
    if commit.returncode != 0:
        print("safe_commit: git commit failed:\n" + commit.stderr, file=sys.stderr)
        return 1
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"safe_commit: committed {len(staged)} file(s) as {sha}")
    for s in staged:
        print(f"  {s}")

    if args.push:
        push = _git(repo, "push")
        if push.returncode != 0:
            print("safe_commit: push FAILED:\n" + push.stderr, file=sys.stderr)
            return 1
        print("safe_commit: pushed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
