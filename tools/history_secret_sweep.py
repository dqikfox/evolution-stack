"""
history_secret_sweep.py - scan every commit of a repo for secret-shaped values.

The working tree being clean proves nothing about the history: a secret that
was committed and then removed is still in the git objects, and on a public
repo that is a permanent exposure.

Why this used to take hours
---------------------------
The first implementation ran `git show <sha>:<path>` once per file per commit.
A repository with 800 mirrored files and 200 commits is 160,000 subprocesses.
The content of a file rarely changes between commits, so the same blob is
re-read over and over.

This version reads each BLOB once (deduplicated by object id, streamed
through `git cat-file --batch`) and then checks it against every commit that
contains it. The same repository takes minutes instead of hours, which is the
difference between a check people run and a check people skip.

Usage: python history_secret_sweep.py <repo> [<repo> ...]
Exit: 0 clean, 1 findings, 2 usage.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evo.secrets import scan_text  # noqa: E402

TEXTY = (".py", ".cmd", ".bat", ".ps1", ".sh", ".json", ".yaml", ".yml", ".env",
         ".txt", ".cfg", ".ini", ".toml", ".md", ".oprefs")
SKIP_PATH = ("node_modules", "package-lock", ".github/", "docs/", "vendor/")


class BlobReader:
    """Read git blobs through a single `git cat-file --batch` process."""

    def __init__(self, repo: str):
        self.proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def read(self, blob: str) -> str:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write((blob + "\n").encode())
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode("utf-8", "replace").strip()
        # "<sha> blob <size>" or "<sha> missing"
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            return ""
        size = int(parts[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)          # trailing newline
        return data.decode("utf-8", "replace")

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _entries(repo: str, sha: str) -> list[tuple[str, str]]:
    """(blob, path) for every text-ish file in a commit."""
    r = subprocess.run(["git", "-C", repo, "ls-tree", "-r", sha],
                       capture_output=True, text=True, timeout=300)
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        if not path.lower().endswith(TEXTY) or any(s in path for s in SKIP_PATH):
            continue
        out.append((parts[2], path))
    return out


def sweep(repo: str) -> list[str]:
    r = subprocess.run(["git", "-C", repo, "rev-list", "--all"],
                       capture_output=True, text=True, timeout=900)
    shas = [s for s in r.stdout.split() if s]
    reader = BlobReader(repo)
    # A blob's findings do not depend on which commit contains it, so each
    # blob is SCANNED once and the result is re-labelled per commit. Without
    # this, a file that is unchanged across 50 commits is scanned 50 times.
    blob_findings: dict[str, list] = {}
    hits: set[str] = set()
    try:
        for sha in shas:
            for blob, path in _entries(repo, sha):
                found = blob_findings.get(blob)
                if found is None:
                    text = reader.read(blob)
                    found = scan_text(text, path)
                    blob_findings[blob] = found
                for x in found:
                    hits.add(f"{sha[:8]}:{x.file}:{x.line} {x.kind} in field '{x.name}'")
    finally:
        reader.close()
    return sorted(hits)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    total = 0
    for repo in sys.argv[1:]:
        hits = sweep(repo)
        total += len(hits)
        print(f"[history-sweep] {repo}: {len(hits)} finding(s)", flush=True)
        for h in hits:
            print("   ", h, flush=True)
    print(f"[history-sweep] total {total}", flush=True)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
