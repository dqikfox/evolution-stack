#!/usr/bin/env python3
"""Fetch every remote branch as a local branch, then push the rewritten history.

After a filter-branch the local repo may not have a local branch for every
branch on the remote, so "git push origin br:br" fails with "src refspec does
not match any". This fetches each remote branch into refs/heads/ first, then
pushes with an explicit lease.

    python push_all_branches.py <repo-path> [<repo-path> ...]
"""
import os
import subprocess
import sys

GIT = r"C:\Program Files\Git\cmd\git.exe"
ENV = dict(os.environ)
for _v in ("PWD", "OLDPWD"):
    ENV.pop(_v, None)


def git(repo, *args, timeout=1800):
    return subprocess.run([GIT, "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=timeout, env=ENV, encoding="utf-8", errors="replace")


def local_branches(repo):
    out = {}
    for line in git(repo, "branch", "--format=%(refname:short) %(objectname)").stdout.splitlines():
        name, _, sha = line.partition(" ")
        if name:
            out[name] = sha
    return out


def do(repo):
    print("=== %s ===" % repo, flush=True)
    git(repo, "fetch", "origin", "--prune")
    remotes = {}
    for line in git(repo, "ls-remote", "--heads", "origin").stdout.splitlines():
        sha, _, ref = line.partition("\t")
        remotes[ref.replace("refs/heads/", "")] = sha
    print("  remote branches: %d" % len(remotes), flush=True)

    # fetch every remote branch into a local branch
    have = local_branches(repo)
    made = 0
    for br in remotes:
        if br in have:
            continue
        r = git(repo, "fetch", "origin", "%s:refs/heads/%s" % (br, br))
        if r.returncode == 0:
            made += 1
        else:
            print("    fetch %s FAILED: %s" % (br, (r.stderr or "").strip()[-110:]), flush=True)
    print("  fetched %d missing branches (now %d local)" % (
        made, len(local_branches(repo))), flush=True)

    # push each one with an explicit lease
    have = local_branches(repo)
    ok = 0
    for br, sha in remotes.items():
        if br not in have:
            print("    %-56s NO LOCAL BRANCH" % br, flush=True)
            continue
        r = git(repo, "push", "--force-with-lease=%s:%s" % (br, sha), "origin", "%s:%s" % (br, br))
        if r.returncode == 0:
            ok += 1
        else:
            print("    %-56s FAILED %s" % (br, (r.stderr or "").strip()[-110:]), flush=True)
    print("  pushed %d/%d" % (ok, len(remotes)), flush=True)
    return ok, len(remotes)


if __name__ == "__main__":
    for repo in sys.argv[1:]:
        do(repo)
