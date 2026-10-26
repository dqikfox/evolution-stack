#!/usr/bin/env python3
"""Run the selective identity rewrite from a JSON queue.

The paths live in a FILE, not in argv: the MSYS bash layer rewrites "C:/..."
into "/c/..." when it passes an argument to a native program, and native git
cannot read "/c/...". A file sidesteps the argument conversion entirely.

    python rewrite_queue.py <queue.json> [--no-push]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rewrite_local_identities import rewrite  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    push = "--no-push" not in args
    queue_path = [a for a in args if a != "--no-push"][0]
    with open(queue_path, "r", encoding="utf-8") as fh:
        queue = json.load(fh)
    rc = 0
    for entry in queue["repos"]:
        if not rewrite(entry["name"], entry["path"], push=push):
            rc = 1
    print("ALL DONE", flush=True)
    sys.exit(rc)
