#!/usr/bin/env python3
"""Push the rewritten branches of a repo, with an explicit lease.

    python push_rewritten.py <repo-path>

A --force-with-lease needs a lease to compare against. After a filter-branch
the remote-tracking refs may be stale or gone, so the SHA is read with
ls-remote and named explicitly in the lease.
"""
import os
import subprocess
import sys

GIT = r"C:\Program Files\Git\cmd\git.exe"
ENV = dict(os.environ)
for _v in ("PWD", "OLDPWD"):
    ENV.pop(_v, None)


def git(repo, *args, timeout=280):
    return subprocess.run([GIT, "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=timeout, env=ENV, encoding="utf-8", errors="replace")


if __name__ == "__main__":
    repo = sys.argv[1]
    git(repo, "fetch", "origin", "--prune", timeout=280)
    remotes = {}
    for line in git(repo, "ls-remote", "--heads", "origin").stdout.splitlines():
        sha, _, ref = line.partition("\t")
        remotes[ref.replace("refs/heads/", "")] = sha
    print("remote branches: %d" % len(remotes), flush=True)
    ok = 0
    for br, sha in remotes.items():
        r = git(repo, "push", "--force-with-lease=%s:%s" % (br, sha), "origin", "%s:%s" % (br, br))
        status = "ok" if r.returncode == 0 else "FAILED " + (r.stderr or "").strip()[-140:]
        print("  %-46s %s" % (br, status), flush=True)
        ok += r.returncode == 0
    print("pushed %d/%d" % (ok, len(remotes)), flush=True)
