#!/usr/bin/env python
"""
workspace-watchdog.py - File-system watcher for THRONE project repos
On change under C:/Users/KING/Projects/, log + optionally auto-commit/push
"""
import sys, os, json, time, argparse, subprocess
from pathlib import Path
from datetime import datetime

try:
    from watchfiles import watch, Change
except ImportError:
    print("watchfiles not installed", file=sys.stderr); sys.exit(2)

ROOT = Path(os.environ.get("WATCH_ROOT", r"C:\Users\KING\Projects"))
LOG = Path(os.environ.get("WATCH_LOG",
                          r"C:\Users\KING\AppData\Local\hermes\audit\watchdog.log"))
LOG.parent.mkdir(parents=True, exist_ok=True)
EXCLUDE_DIRS = {".git", "node_modules", "Library", "venv", "__pycache__", "dist", "build", ".next"}


def log(msg: str):
    line = f"{datetime.utcnow().isoformat()}Z {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_under(p: Path, excl: set) -> bool:
    return not any(part in excl for part in p.parts)


def git_status(repo: Path):
    try:
        r = subprocess.run(["git", "-C", str(repo), "status", "--short"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR {e}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true",
                   help="scan and emit one report, no watch loop")
    p.add_argument("--dry", action="store_true", help="no logging")
    args = p.parse_args()

    if args.once:
        repos = [d for d in ROOT.iterdir() if d.is_dir() and (d / ".git").exists()]
        log(f"=== WORKSPACE SCAN root={ROOT} repos={len(repos)} ===")
        for r in repos:
            dirty = git_status(r)
            status = "CLEAN" if not dirty else f"{len(dirty.splitlines())} files dirty"
            log(f"  {r.name}: {status}")
            if dirty:
                for line in dirty.splitlines()[:8]:
                    log(f"    {line}")
        return 0

    log(f"start watch root={ROOT}")
    for changes in watch(str(ROOT), recursive=True, step=200):
        for change_type, path_str in changes:
            p = Path(path_str)
            if not is_under(p, EXCLUDE_DIRS):
                continue
            log(f"{change_type.name} {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())