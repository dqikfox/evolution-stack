"""
history_secret_sweep.py - scan every commit of a repo for secret-shaped values.

The working tree being clean proves nothing about the history: a secret that
was committed and then removed is still in the git objects, and on a public
repo that is a permanent exposure.

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


def sweep(repo: str) -> list[str]:
    r = subprocess.run(["git", "-C", repo, "rev-list", "--all"],
                       capture_output=True, text=True, timeout=600)
    shas = [s for s in r.stdout.split() if s]
    hits: set[str] = set()
    for sha in shas:
        t = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", sha],
                           capture_output=True, text=True, timeout=180)
        for f in t.stdout.splitlines():
            if not f.lower().endswith(TEXTY) or any(s in f for s in SKIP_PATH):
                continue
            c = subprocess.run(["git", "-C", repo, "show", f"{sha}:{f}"],
                               capture_output=True, text=True, timeout=90)
            if c.returncode:
                continue
            for x in scan_text(c.stdout, f"{sha[:8]}:{f}"):
                hits.add(str(x))
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
