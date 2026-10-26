#!/usr/bin/env python3
"""Rewrite every commit's author/committer to the dqikfox GitHub identity.

git filter-branch, not git filter-repo: the installed filter-repo (2.47.0)
crashes on this git version with "TypeError: %b requires a bytes-like object"
in its vendored fast-export writer, on EVERY repo including a trivial one.
Core git's filter-branch has no Python dependency and works.

This runs in-process, one repo at a time, and it removes refs/original/* after
each repo: those refs keep the OLD identity reachable and would otherwise be
pushed as duplicate history.
"""
import os
import subprocess
import sys
import time

FILTER = (
    "export GIT_AUTHOR_NAME='dqikfox'; "
    "export GIT_AUTHOR_EMAIL='dqikfox@users.noreply.github.com'; "
    "export GIT_COMMITTER_NAME='dqikfox'; "
    "export GIT_COMMITTER_EMAIL='dqikfox@users.noreply.github.com'"
)

ENV = dict(os.environ)
ENV["FILTER_BRANCH_SQUELCH_WARNING"] = "1"


def git(repo, *args, timeout=280):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=timeout, env=ENV, encoding="utf-8", errors="replace")


def rewrite(name, repo):
    t0 = time.time()
    r = git(repo, "filter-branch", "-f", "--env-filter", FILTER, "--", "--all")
    # clean up: filter-branch leaves refs/original/* behind
    orig = git(repo, "for-each-ref", "--format=%(refname)", "refs/original/").stdout.strip()
    for ref in (orig.splitlines() if orig else []):
        git(repo, "update-ref", "-d", ref)
    git(repo, "reflog", "expire", "--expire=now", "--all")
    git(repo, "gc", "--prune=now", "--quiet", timeout=280)
    ids = {}
    for line in git(repo, "log", "--format=%an <%ae>", "--all").stdout.splitlines():
        ids[line] = ids.get(line, 0) + 1
    print("  %-16s rc=%-3s %5.0fs  %s" % (name, r.returncode, time.time() - t0, ids), flush=True)
    if r.returncode != 0:
        print("     err: %s" % (r.stderr or "").strip()[-400:], flush=True)
    return r.returncode


if __name__ == "__main__":
    rc = 0
    for arg in sys.argv[1:]:
        name, _, repo = arg.partition("=")
        rc |= rewrite(name, repo or name)
    print("ALL DONE", flush=True)
    sys.exit(0 if rc == 0 else 1)
