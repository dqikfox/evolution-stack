#!/usr/bin/env python3
"""Audit EVERY branch of every dqikfox repo for unlinked local identities.

Why this exists
---------------
An earlier audit checked only the default branch, `master` and `main` of each
repo, and reported "0 unlinked local identities". That was wrong. `vision` has
173 branches; the 29 offending branches were on the others, and the audit
never looked at them. The rewrite had fetched the unrewritten remote branches
into `refs/heads/` and pushed them straight back, so the remote still carried
the old history while every check said "clean".

So the audit must walk every branch, on every repo, and report the offending
BRANCH - not just the repo.

    python verify_all_branches.py            # the whole dqikfox account
    python verify_all_branches.py dqikfox/vision
"""
import json
import os
import subprocess
import sys
import time

BAD = {
    "king@throne.local", "KING@THRONE", "ultron@talking.ai", "ultron@throne.local",
    "ultron@hermes.local", "ultron@local", "ultron@tesseract.local",
    "megatron@tesseract.local", "Shadow@SHADOW-EOKGST4R", "minion@throne.local",
    "dqikfox@local",
}
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)


def gh(*args, timeout=180):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout,
                          env=ENV, encoding="utf-8", errors="replace")


def branches_of(repo: str):
    names = []
    page = 1
    while True:
        r = gh("api", "repos/%s/branches?per_page=100&page=%d" % (repo, page), "--jq", ".[].name")
        if r.returncode != 0:
            return names, (r.stderr or "").strip()[:120]
        got = [l for l in r.stdout.splitlines() if l.strip()]
        names += got
        if len(got) < 100:
            break
        page += 1
    return names, None


def audit_branch(repo: str, branch: str):
    """The offending commits on one branch. Empty means clean."""
    hits = []
    page = 1
    while True:
        r = gh("api", "repos/%s/commits?sha=%s&per_page=100&page=%d" % (repo, branch, page),
               "--jq", ".[] | \"\\(.author.login // \"UNLINKED\")|\\(.commit.author.email)|\\(.sha)\"")
        if r.returncode != 0:
            break
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        for l in lines:
            login, _, rest = l.partition("|")
            email, _, sha = rest.partition("|")
            if login == "UNLINKED" and email in BAD:
                hits.append((email, sha))
        if len(lines) < 100:
            break
        page += 1
    return hits


def audit(repo: str):
    names, err = branches_of(repo)
    if err:
        print("   %-34s SKIPPED (%s)" % (repo, err))
        return 0, 0
    bad = {}
    scanned = 0
    for b in names:
        hits = audit_branch(repo, b)
        scanned += 1
        if hits:
            bad[b] = hits
    if bad:
        total = sum(len(v) for v in bad.values())
        print("   %-34s %d branches, %d OFFENDING" % (repo, len(names), total))
        for b, hits in list(bad.items())[:20]:
            print("      %-64s %d commits" % (b[:64], len(hits)))
        if len(bad) > 20:
            print("      ... and %d more branches" % (len(bad) - 20))
    else:
        print("   %-34s %d branches, clean" % (repo, len(names)))
    return len(bad), scanned


def main(repos):
    t0 = time.time()
    print("=== the per-branch audit of every dqikfox repo ===", flush=True)
    total_bad = 0
    total_branches = 0
    for repo in repos:
        b, n = audit(repo)
        total_bad += b
        total_branches += n
        sys.stdout.flush()
    print("\n   %d repos, %d branches audited, %d branches with local identities  (%.0fs)"
          % (len(repos), total_branches, total_bad, time.time() - t0))
    if total_bad:
        print("   THE ACCOUNT IS NOT CLEAN", flush=True)
    else:
        print("   EVERY BRANCH IS CLEAN", flush=True)
    return 1 if total_bad else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        r = gh("repo", "list", "dqikfox", "--limit", "100", "--json", "name")
        args = ["dqikfox/%s" % n["name"] for n in json.loads(r.stdout or "[]")]
    sys.exit(main(args))
