#!/usr/bin/env python3
"""Rewrite ONLY the local machine identities to dqikfox, leaving bots alone.

An UNLINKED commit is one GitHub cannot attribute to an account, because the
author email is not a verified address on any account - a local machine
identity like KING@THRONE or ultron@talking.ai. Those are Hitchy's own work
and must read as dqikfox.

A BOT commit is one authored by a GitHub App or a bot account
(Copilot, dependabot, jules, Codex, semgrep, grok-export, manus-ai). Those are
NOT rewritten: the bot really did the work, and relabelling them as dqikfox
would be false attribution. They stay linked to the bot.

A THIRD-PARTY commit (a fork of someone else's project) is left alone
entirely - it is not Hitchy's repo.

git filter-branch, not git filter-repo: the installed filter-repo (2.47.0, the
newest on PyPI) crashes on this host with "TypeError: %b requires a bytes-like
object" in its vendored fast-export writer, on every repo including a trivial
one. Core git's filter-branch has no Python dependency and works.

The env-filter is conditional: it rewrites an identity only when the email is
on the LOCAL_IDENTITIES list.
"""
import os
import subprocess
import sys
import time

LOCAL_IDENTITIES = {
    # local machine identities -> GitHub cannot attribute these to any account
    "king@throne.local",
    "KING@THRONE",
    "ultron@talking.ai",
    "ultron@throne.local",
    "ultron@hermes.local",
    "ultron@local",
    "ultron@tesseract.local",
    "megatron@tesseract.local",
    "Shadow@SHADOW-EOKGST4R",
    "minion@throne.local",
    "dqikfox@local",
}

# build the shell conditional: rewrite only if the email is one of ours.
# one -e per pattern: joining with "|" would make a shell PIPE, not a grep
# alternation, and the filter would silently never fire.
_COND = " ".join("-e '%s'" % e for e in sorted(LOCAL_IDENTITIES))
FILTER = (
    # NOTE: %s must be a single percent. FILTER is built by concatenation, not
    # by %-formatting, so "%%s" would reach printf as a literal %%s and printf
    # would print the characters "%s" instead of the email - the filter would
    # then never match and the rewrite would silently do nothing.
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
# A bash/MSYS shell exports PWD as an MSYS path ("/c/Users/..."). git's
# filter-branch resolves the repository from $PWD, and native git cannot open
# that: "fatal: not a git repository: '/c/Users/.../.git'". Drop the MSYS
# path variables so the resolution uses the native path.
for _msys_var in ("PWD", "OLDPWD"):
    ENV.pop(_msys_var, None)


def _find_native_git():
    """The MSYS git (/usr/bin/git, inherited from a bash shell) cannot open a
    native Windows repository path: filter-branch resolves the repo from $PWD
    and then fails with "fatal: not a git repository: '/c/Users/.../.git'".
    A native git.exe works. Prefer one, in order of preference."""
    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Users\KING\AppData\Local\hermes\tools\git-2.53.0+3-win32-x64\cmd\git.exe",
        r"C:\Users\KING\AppData\Local\hermes\git\cmd\git.exe",
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    # fall back to whatever is on PATH
    return "git"


GIT = _find_native_git()


def git(repo, *args, timeout=1800, cwd=None):
    return subprocess.run([GIT, "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=timeout, env=ENV, encoding="utf-8", errors="replace",
                          cwd=cwd or repo)


def rewrite(name, repo, push=True):
    t0 = time.time()
    before = git(repo, "log", "--format=%ae", "--all").stdout
    ours_before = sum(1 for e in before.splitlines() if e in LOCAL_IDENTITIES)
    # filter-branch re-resolves the repo directory from the CWD, and on this
    # host that resolution produces an MSYS "/c/..." path that native git
    # cannot open - "fatal: not a git repository: '/c/Users/.../.git'".
    # Running it with the cwd already inside the repo avoids that entirely.
    r = subprocess.run([GIT, "filter-branch", "-f", "--env-filter", FILTER, "--", "--all"],
                       cwd=repo, capture_output=True, text=True, timeout=3600, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  %-26s FAILED rc=%s %s" % (name, r.returncode,
              (r.stderr or "").strip()[-200:]), flush=True)
        return False
    # filter-branch leaves refs/original/* behind, keeping the old history
    # reachable, and it removes the origin remote
    orig = git(repo, "for-each-ref", "--format=%(refname)", "refs/original/").stdout.strip()
    for ref in (orig.splitlines() if orig else []):
        git(repo, "update-ref", "-d", ref)
    git(repo, "reflog", "expire", "--expire=now", "--all")
    git(repo, "gc", "--prune=now", "--quiet", timeout=1800)
    after = git(repo, "log", "--format=%ae", "--all").stdout
    ours_after = sum(1 for e in after.splitlines() if e in LOCAL_IDENTITIES)
    print("  %-26s %5.0fs  local-identity commits %d -> %d" % (
        name, time.time() - t0, ours_before, ours_after), flush=True)

    if not push:
        return True

    # restore the remote if filter-branch removed it
    if not git(repo, "remote", "-v").stdout.strip():
        url = git(repo, "config", "--get", "remote.origin.url").stdout.strip()
        if not url:
            print("     no remote to restore - skipping the push", flush=True)
            return True
        git(repo, "remote", "add", "origin", url)
    git(repo, "fetch", "origin", "--prune", timeout=1800)

    # push every branch that exists on the remote, with an explicit lease
    remotes = {}
    for line in git(repo, "ls-remote", "--heads", "origin").stdout.splitlines():
        sha, _, ref = line.partition("\t")
        remotes[ref.replace("refs/heads/", "")] = sha
    ok = True
    for br, sha in remotes.items():
        p = git(repo, "push", "--force-with-lease=%s:%s" % (br, sha), "origin", "%s:%s" % (br, br))
        if p.returncode != 0:
            print("     push %s FAILED: %s" % (br, (p.stderr or "").strip()[-180:]), flush=True)
            ok = False
    print("     pushed %d branches: %s" % (len(remotes), "ok" if ok else "ERRORS"), flush=True)
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    push = "--no-push" not in args
    args = [a for a in args if a != "--no-push"]
    rc = 0
    for arg in args:
        name, _, repo = arg.partition("=")
        if not rewrite(name, repo or name, push=push):
            rc = 1
    print("ALL DONE", flush=True)
    sys.exit(rc)
