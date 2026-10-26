#!/usr/bin/env python3
"""Scan a git repo's TRACKED files for secret-looking values.

Uses the estate's own scanner (evo.secrets), which judges a value by its
SHAPE rather than by the length of an assignment, and prints findings
without ever printing the value.

Distinct from sweep_secrets.py, which walks a directory tree. This one
asks git which files a push would actually publish, so it matches what a
pre-push guard needs.

The per-line opt-out marker is deliberately LOCAL to this tool and is not
part of evo.secrets. The surface mirror publishes to a PUBLIC repository;
if the shared scanner honoured the marker, a marker added next to a real
key would let that key be published. The marker only relaxes the local
pre-push gate, and only for the assignment scan - a vendor-prefix token
on the same line is still caught by the hook's own check.

Exit codes:
  0  clean
  1  findings (the caller should block)
  2  the scanner could not run (the caller should block, loudly)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# The scanner lives beside this script in the evolution-stack repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from evo.secrets import scan_file
except Exception as exc:  # noqa: BLE001 - the guard must fail closed
    print(f"secret scan could not start: {exc}", file=sys.stderr)
    raise SystemExit(2)

# An opt-out for a test that must contain a key-shaped literal. The
# vendor-prefix check in the pre-push hook still applies to these lines,
# so this can never be used to publish a real token.
ALLOW_MARKER = "secret-guard: allow"

SCAN_SUFFIXES = {".py", ".js", ".ts", ".sh", ".ps1", ".bat", ".html", ".css",
                  ".json", ".toml", ".yaml", ".yml", ".env", ".config", ".cfg",
                  ".ini"}


def tracked_files(repo: Path) -> list[Path]:
    """The tracked files a push would publish."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files"],
            capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"could not list tracked files: {exc}", file=sys.stderr)
        raise SystemExit(2)
    files = []
    for rel in out.stdout.splitlines():
        p = repo / rel
        if p.is_file() and p.suffix.lower() in SCAN_SUFFIXES:
            files.append(p)
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repo root to scan")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"not a git repo: {repo}", file=sys.stderr)
        return 2

    findings = []
    for path in tracked_files(repo):
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            rel = str(path)
        for finding in scan_file(path):
            findings.append((rel, finding))

    if not findings:
        return 0

    # An allow marker is honoured per line, and only for the assignment
    # scan - a vendor-prefix token on the same line is still caught by the
    # pre-push hook's own check.
    kept = []
    for rel, finding in findings:
        try:
            lines = (repo / rel).read_text(encoding="utf-8",
                                           errors="ignore").splitlines()
            src = lines[finding.line - 1] if 0 < finding.line <= len(lines) else ""
        except OSError:
            src = ""
        if ALLOW_MARKER in src:
            continue
        kept.append((rel, finding))

    if not kept:
        return 0

    print("secret-looking values in tracked files:")
    for rel, finding in kept:
        print(f"  {rel}:{finding.line}  {finding.kind}  in field '{finding.name}'")
    print()
    print("Values are never printed. Move them to 1Password (op://) or")
    print(f"mark a deliberate fixture with '# {ALLOW_MARKER}'.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
