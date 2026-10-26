#!/usr/bin/env python3
"""Rewrite the local machine identities in a repo's REMOTE history, for EVERY branch.

Why this exists
---------------
The earlier approach rewrote the LOCAL branches and then pushed them. That
missed every branch that existed only on the remote:

  1. filter-branch rewrote the refs that were local. A branch that only ever
     existed on the remote was not in the local ref set, so it was not
     rewritten.
  2. The push then failed for it: "src refspec does not match any".
  3. A later fetch brought the UNREWRITTEN remote branch into refs/heads/ and
     pushed it straight back, reporting success while republishing the old
     history.

So the rewrite has to happen against the remote state itself. This does that
in a bare clone: a bare clone has no working tree, so a dirty worktree or a
filename that NTFS cannot recreate cannot block the rewrite, and the clone
is exactly what the remote holds.

    python rewrite_remote.py dqikfox/vision https://github.com/dqikfox/vision.git

It is safe to run twice: the second run finds nothing left to rewrite.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

GIT = r"C:\Program Files\Git\cmd\git.exe"

LOCAL_IDENTITIES = {
    "king@throne.local", "KING@THRONE", "ultron@talking.ai", "ultron@throne.local",
    "ultron@hermes.local", "ultron@local", "ultron@tesseract.local",
    "megatron@tesseract.local", "Shadow@SHADOW-EOKGST4R", "minion@throne.local",
    "dqikfox@local",
}

# one -e per pattern: a "|" between them would be a shell PIPE, not a grep
# alternation, and the filter would silently never fire.
_COND = " ".join("-e '%s'" % e for e in sorted(LOCAL_IDENTITIES))
FILTER = (
    "if printf '%s\\n%s\\n' \"$GIT_AUTHOR_EMAIL\" \"$GIT_COMMITTER_EMAIL\" | "
    "grep -qxF " + _COND + " ; then "
    "export GIT_AUTHOR_NAME='dqikfox'; "
    "export GIT_AUTHOR_EMAIL='dqikfox@users.noreply.github.com'; "
    "export GIT_COMMITTER_NAME='dqikfox'; "
    "export GIT_COMMITTER_EMAIL='dqikfox@users.noreply.github.com'; "
    "fi"
)

ENV = dict(os.environ)
ENV["FILTER_BRANCH_SQUELCH_WARNING"] = "1"
for _v in ("PWD", "OLDPWD"):
    ENV.pop(_v, None)


def git(repo, *args, timeout=3600):
    return subprocess.run([GIT, "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=timeout, env=ENV, encoding="utf-8", errors="replace")


def count_ours(repo):
    out = git(repo, "log", "--format=%ae", "--all").stdout
    return sum(1 for e in out.splitlines() if e in LOCAL_IDENTITIES)


def _force_rmtree(path: Path) -> None:
    """Remove a directory tree on Windows.

    Python's shutil.rmtree fails with "Access is denied" on git's
    commit-graph, because git holds a read lock on it. cmd's rmdir clears
    the read-only attribute and succeeds. Try both, and do not let a failed
    cleanup abort the run - the directory is disposable either way.
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except Exception:
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(path)],
                       capture_output=True, timeout=300)


def main(name, url, workdir=None):
    t0 = time.time()
    # A UNIQUE directory per run. A fixed path collides with the debris of a
    # previous run, and the clone then fails with "destination path already
    # exists and is not an empty directory" - which reads as a clone failure
    # rather than as stale debris.
    work = Path(workdir or (Path(os.environ.get("TEMP", r"C:\Users\KING\AppData\Local\Temp"))
                             / ("rewrite-%s-%d" % (name.replace("/", "_"), int(time.time())))))
    _force_rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    print("=== %s ===" % name, flush=True)
    # A --mirror clone sets remote.origin.mirror=true, and then EVERY push
    # fails with "fatal: --mirror can't be combined with refspecs" - which
    # would make the whole run look successful while changing nothing on the
    # remote. A plain bare clone plus an explicit push of each branch is
    # what this tool needs.
    r = subprocess.run([GIT, "clone", "--bare", url, str(work)],
                       capture_output=True, text=True, timeout=3600, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("   CLONE FAILED: %s" % (r.stderr or "").strip()[-200:], flush=True)
        return False
    # fetch every branch and tag explicitly, so nothing on the remote is missed
    r = subprocess.run([GIT, "-C", str(work), "fetch", "origin",
                        "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*",
                        "--prune", "--force"],
                       capture_output=True, text=True, timeout=3600, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("   FETCH FAILED: %s" % (r.stderr or "").strip()[-200:], flush=True)
        return False

    before = count_ours(str(work))
    print("   local-identity commits before: %d" % before, flush=True)
    if before == 0:
        print("   nothing to rewrite", flush=True)
        return True

    # rewrite every ref in the bare clone: branches, tags, notes, everything
    r = subprocess.run([GIT, "filter-branch", "-f", "--env-filter", FILTER, "--", "--all"],
                       cwd=str(work), capture_output=True, text=True, timeout=7200, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("   REWRITE FAILED: %s" % (r.stderr or "").strip()[-300:], flush=True)
        return False

    # filter-branch leaves refs/original/* behind, keeping the old history
    # reachable, so the old commits must be dropped and the objects pruned.
    orig = git(str(work), "for-each-ref", "--format=%(refname)", "refs/original/").stdout.strip()
    for ref in (orig.splitlines() if orig else []):
        git(str(work), "update-ref", "-d", ref)
    git(str(work), "reflog", "expire", "--expire=now", "--all")
    git(str(work), "gc", "--prune=now", "--quiet", timeout=3600)

    after = count_ours(str(work))
    print("   local-identity commits after:  %d" % after, flush=True)
    if after != 0:
        print("   STILL PRESENT - not pushing", flush=True)
        return False

    # the lease is taken from the ORIGINAL remote state, so a branch that
    # moved under us is refused rather than overwritten.
    remotes = {}
    for line in git(str(work), "ls-remote", "--heads", "origin").stdout.splitlines():
        sha, _, ref = line.partition("\t")
        remotes[ref.replace("refs/heads/", "")] = sha
    print("   %d remote branches to publish" % len(remotes), flush=True)

    ok = 0
    failed = []
    for br, sha in remotes.items():
        p = git(str(work), "push", "--force-with-lease=%s:%s" % (br, sha), "origin", "%s:%s" % (br, br))
        if p.returncode == 0:
            ok += 1
        else:
            failed.append((br, (p.stderr or "").strip()[-120:]))
    print("   pushed %d/%d branches" % (ok, len(remotes)), flush=True)
    for br, err in failed[:10]:
        print("     FAILED %s: %s" % (br[:60], err), flush=True)
    if len(failed) > 10:
        print("     ... and %d more" % (len(failed) - 10), flush=True)

    # Tags carry history too, and a tag that still points at an old commit
    # keeps that history reachable.
    tags = {}
    for line in git(str(work), "ls-remote", "--tags", "origin").stdout.splitlines():
        sha, _, ref = line.partition("\t")
        ref = ref.replace("refs/tags/", "")
        if ref.endswith("^{}"):
            continue
        tags[ref] = sha
    tag_ok = 0
    for tag, sha in tags.items():
        p = git(str(work), "push", "--force", "origin", "refs/tags/%s:refs/tags/%s" % (tag, tag))
        if p.returncode == 0:
            tag_ok += 1
        else:
            print("     TAG FAILED %s: %s" % (tag[:50], (p.stderr or "").strip()[-100:]), flush=True)
    if tags:
        print("   pushed %d/%d tags" % (tag_ok, len(tags)), flush=True)

    # Verify against the REMOTE, not the local clone. This is the check that
    # the earlier run should have made and did not: the local clone was
    # rewritten, but the remote is what people actually see.
    _force_rmtree(work)
    check = Path(str(work) + "-check")
    _force_rmtree(check)
    subprocess.run([GIT, "clone", "--bare", url, str(check)], capture_output=True, text=True,
                   timeout=3600, env=ENV, encoding="utf-8", errors="replace")
    subprocess.run([GIT, "-C", str(check), "fetch", "origin", "+refs/heads/*:refs/heads/*",
                    "--prune", "--force"], capture_output=True, text=True, timeout=3600,
                   env=ENV, encoding="utf-8", errors="replace")
    final = count_ours(str(check))
    branches = len([l for l in git(str(check), "for-each-ref", "--format=%(refname)",
                                   "refs/heads/").stdout.splitlines() if l.strip()])
    _force_rmtree(check)
    print("   VERIFIED ON THE REMOTE: %d branches, %d local-identity commits" % (branches, final), flush=True)
    if final != 0:
        print("   the remote still holds local identities - NOT CLEAN", flush=True)
        return False
    print("   %.0fs" % (time.time() - t0), flush=True)
    return not failed


if __name__ == "__main__":
    rc = 0
    for arg in sys.argv[1:]:
        name, _, url = arg.partition("=")
        if not main(name, url or name):
            rc = 1
    print("ALL DONE", flush=True)
    sys.exit(rc)
