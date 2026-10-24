"""
sweep_secrets.py - scan a set of trees for secret-looking values.

Usage:
    python sweep_secrets.py ROOT [ROOT ...] [--suffix .py,.cmd] [--json]

Exit codes:
    0  clean
    1  findings (printed, one per line, values never printed)
    2  bad usage
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evo.secrets import scan_tree  # noqa: E402

SKIP = {"cache", "logs", "audio_cache", "tools", "state", "data", "docs",
        "imagine_images", "media", "vendor", "output"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    suffixes = (".py", ".cmd", ".bat", ".ps1", ".sh", ".json", ".yaml", ".yml",
                ".env", ".txt", ".cfg", ".ini", ".toml", ".oprefs", ".md")
    for f in flags:
        if f.startswith("--suffix"):
            suffixes = tuple(f.split("=", 1)[1].split(",")) if "=" in f else suffixes
    if not args:
        print(__doc__)
        return 2

    all_findings = []
    t0 = time.time()
    for root in args:
        f = scan_tree(root, suffixes=suffixes, skip_dirs=SKIP)
        print(f"[sweep] {root}: {len(f)} finding(s)", file=sys.stderr)
        all_findings.extend(f)

    if "--json" in flags:
        print(json.dumps([{"file": x.file, "line": x.line, "name": x.name,
                           "kind": x.kind} for x in all_findings], indent=2))
    else:
        for x in all_findings:
            print(str(x))
    print(f"[sweep] {len(all_findings)} finding(s) across {len(args)} root(s) in {time.time()-t0:.1f}s",
          file=sys.stderr)
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
