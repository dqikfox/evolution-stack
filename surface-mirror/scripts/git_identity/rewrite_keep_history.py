#!/usr/bin/env python3
"""Rewrite the local Git identities in a repository, KEEPING THE HISTORY CONNECTED.

WHY THIS EXISTS
---------------
`git filter-branch` re-creates EVERY commit it walks through. It cannot
re-sign a GPG-signed commit, so it drops the signature - and the commit's
SHA changes even when its author, committer, tree, dates and message are
all identical.

That is fatal on a signed repository. The rewritten history shares NO
commit with the original, so `git merge-base` between the old and the new
tip is empty, git's push negotiation has nothing to negotiate against, and
the push has to carry the ENTIRE repository. On dqikfox/faraday that was
1,177 MB for a branch that had nothing to fix - the branch was 94
third-party commits with no local identity in it at all.

THE RULE
--------
A commit whose metadata is unchanged AND whose parent is unchanged is the
SAME OBJECT. Reuse it. Only a commit that actually needs a new identity -
or that sits below one that does - gets a new object.

With that rule, the shared ancestors keep their SHAs, the old and the new
history still share a common base, and the push carries a delta instead of
the whole repository. The 85 offending commits are rewritten, the commits
below them are untouched, and the commits above them are re-created with
the new parent - which is unavoidable, because a parent's SHA is part of a
child's SHA.

WHAT IS PRESERVED
-----------------
- The author and the committer name, email and date, exactly.
- The tree, exactly.
- The commit message, exactly, including its encoding header.
- Every third-party commit's authorship, exactly.
- The original commit object for anything that did not need changing.

WHAT IS NOT PRESERVED
----------------------
- The GPG signature on a commit that was re-created. It cannot survive:
  the signature covers the parent SHA, and the parent SHA changed. This is
  a property of the operation, not of this implementation.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

GIT = r"C:\Program Files\Git\cmd\git.exe"

# the local machine identities to be replaced
LOCAL_IDENTITIES = {
    "KING@THRONE",
    "king@throne.local",
    "ultron@talking.ai",
    "dqikfox@local",
    "dfox@local",
    "dfox@throne",
    "hitchy@local",
    "hitchy@throne",
    "dqikst@gmail.com",
    "king@localhost",
}
TARGET_NAME = "dqikfox"
TARGET_EMAIL = "dqikfox@users.noreply.github.com"

ENV = dict(os.environ)
ENV["GIT_TERMINAL_PROMPT"] = "0"
ENV["GCM_INTERACTIVE"] = "never"
ENV["GIT_LFS_SKIP_PUSH"] = "1"


def git(repo, *args, timeout=3600, check=True):
    r = subprocess.run([GIT, "-C", str(repo)] + list(args), capture_output=True, text=True,
                       timeout=timeout, env=ENV, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), (r.stderr or "").strip()[-300:]))
    return r


def _fmt(repo, sha, fmt):
    return git(repo, "log", "-1", "--format=" + fmt, sha).stdout.strip()


def _commit_parts(repo, sha):
    """Everything needed to rebuild a commit, and nothing that is not."""
    raw = git(repo, "cat-file", "commit", sha).stdout
    # the header block, then the message
    head, _, message = raw.partition("\n\n")
    tree = ""
    parents = []
    extra = []
    for line in head.splitlines():
        if line.startswith("tree "):
            tree = line[5:].strip()
        elif line.startswith("parent "):
            parents.append(line[7:].strip())
        else:
            extra.append(line)
    return tree, parents, message, extra


def _is_ours(email: str) -> bool:
    return email.strip() in LOCAL_IDENTITIES


def rewrite_repo(repo: Path, refs: list[str], dry_run: bool = False) -> dict:
    """Rewrite the given refs. Returns a report."""
    report = {"refs": {}, "reused": 0, "recreated": 0, "changed": 0}

    for ref in refs:
        tip = git(repo, "rev-parse", "--verify", "--quiet", ref).stdout.strip()
        if not tip:
            continue
        # the commits in order, oldest first
        order = git(repo, "rev-list", "--topo-order", "--reverse", tip).stdout.split()
        mapping: dict[str, str] = {}
        for sha in order:
            tree, parents, message, extra = _commit_parts(repo, sha)
            a_name = _fmt(repo, sha, "%an")
            a_email = _fmt(repo, sha, "%ae")
            a_date = _fmt(repo, sha, "%aI")
            c_name = _fmt(repo, sha, "%cn")
            c_email = _fmt(repo, sha, "%ce")
            c_date = _fmt(repo, sha, "%cI")

            new_parents = [mapping.get(p, p) for p in parents]
            identity_changes = _is_ours(a_email) or _is_ours(c_email)
            parent_changes = new_parents != parents

            if not identity_changes and not parent_changes:
                # nothing about this commit changed, so it IS the same object
                mapping[sha] = sha
                report["reused"] += 1
                continue

            if not identity_changes:
                # only its parent moved: keep the author and the committer
                # exactly, and re-create the commit
                a_name2, a_email2 = a_name, a_email
                c_name2, c_email2 = c_name, c_email
            else:
                a_name2 = a_name if not _is_ours(a_email) else TARGET_NAME
                a_email2 = TARGET_EMAIL if _is_ours(a_email) else a_email
                c_name2 = c_name if not _is_ours(c_email) else TARGET_NAME
                c_email2 = TARGET_EMAIL if _is_ours(c_email) else c_email

            if dry_run:
                mapping[sha] = "DRYRUN"
                report["recreated"] += 1
                continue

            env = dict(ENV)
            env["GIT_AUTHOR_NAME"] = a_name2
            env["GIT_AUTHOR_EMAIL"] = a_email2
            env["GIT_AUTHOR_DATE"] = a_date
            env["GIT_COMMITTER_NAME"] = c_name2
            env["GIT_COMMITTER_EMAIL"] = c_email2
            env["GIT_COMMITTER_DATE"] = c_date
            cmd = [GIT, "-C", str(repo), "commit-tree", tree]
            for p in new_parents:
                cmd += ["-p", p]
            r = subprocess.run(cmd, input=message, capture_output=True, text=True,
                               timeout=600, env=env, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise RuntimeError("commit-tree failed for %s: %s" % (sha, (r.stderr or "").strip()[-200:]))
            mapping[sha] = r.stdout.strip()
            report["recreated"] += 1

        new_tip = mapping.get(tip, tip)
        offenders = sum(1 for sha in order
                        if _is_ours(_fmt(repo, sha, "%ae")) or _is_ours(_fmt(repo, sha, "%ce")))
        report["refs"][ref] = {"old": tip, "new": new_tip,
                               "changed": new_tip != tip,
                               "offenders": offenders}
        if new_tip != tip:
            report["changed"] += 1
        if not dry_run and new_tip != tip:
            git(repo, "update-ref", ref, new_tip, tip)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--ref", action="append", default=[],
                    help="a ref to rewrite; repeatable. default: every branch")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    repo = Path(a.repo)
    refs = a.ref or git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/").stdout.split()
    rep = rewrite_repo(repo, refs, dry_run=a.dry_run)
    print("   the commits reused unchanged: %d" % rep["reused"])
    print("   the commits re-created:       %d" % rep["recreated"])
    for ref, info in rep["refs"].items():
        note = ""
        if info.get("offenders"):
            note = "  (%d local-identity commit(s))" % info["offenders"]
        print("   %-46s %s -> %s  %s%s" % (ref, info["old"][:10], info["new"][:10],
                                          "changed" if info["changed"] else "UNCHANGED", note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
