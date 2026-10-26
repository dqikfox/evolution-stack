"""The history-preserving rewriter must keep the history CONNECTED.

The failure this guards against is expensive and easy to miss. A rewrite
that re-creates every commit - `git filter-branch` does exactly that -
cannot re-sign a GPG-signed commit, so it drops the signature and the SHA
changes even when the author, committer, tree, dates and message are
identical. The rewritten history then shares no commit with the original,
git's push negotiation has nothing to negotiate against, and the push
carries the WHOLE repository. On dqikfox/faraday that was 1,177 MB for a
branch that had nothing to fix.

So the rewriter must:
  - replace the local identity,
  - leave every third-party commit's authorship alone,
  - REUSE the original commit object for anything whose metadata did not
    change, so the shared ancestors keep their SHAs,
  - keep a common ancestor between the old and the new history,
  - leave a branch with nothing to fix at its original SHA.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

GIT = r"C:\Program Files\Git\cmd\git.exe"
REWRITER = Path(__file__).resolve().parents[1] / "surface-mirror" / "scripts" / \
    "git_identity" / "rewrite_keep_history.py"
if not REWRITER.exists():
    REWRITER = Path("C:/Users/KING/AppData/Local/hermes/scripts/git_identity/"
                     "rewrite_keep_history.py")

ENV = dict(os.environ)
ENV.update({
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00",
    "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
})
for _v in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
    ENV.pop(_v, None)


def _git(repo, *args, check=True):
    r = subprocess.run([GIT, "-C", str(repo)] + list(args), capture_output=True, text=True,
                       timeout=600, env=ENV, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), (r.stderr or "").strip()[-300:]))
    return r


def _commit(repo, name, email, filename, content, message):
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    e = dict(ENV)
    e["GIT_AUTHOR_NAME"] = name
    e["GIT_AUTHOR_EMAIL"] = email
    e["GIT_COMMITTER_NAME"] = name
    e["GIT_COMMITTER_EMAIL"] = email
    r = subprocess.run([GIT, "-C", str(repo), "commit", "-m", message],
                       capture_output=True, text=True, timeout=600, env=e,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    # 1. a third-party commit at the very bottom
    base = _commit(d, "Third Party", "third@example.com", "a.txt", "1", "the base")
    # 2. a local-identity commit in the middle
    mid = _commit(d, "KING@THRONE", "KING@THRONE", "b.txt", "2", "the offender")
    # 3. a third-party commit on top
    top = _commit(d, "Third Party", "third@example.com", "c.txt", "3", "the top")
    # 4. a branch that never had a local identity
    _git(d, "checkout", "-q", "-b", "clean", base)
    clean = _commit(d, "Third Party", "third@example.com", "d.txt", "4", "clean work")
    _git(d, "checkout", "-q", "main")
    return d, {"base": base, "mid": mid, "top": top, "clean": clean}


def _rewrite(repo):
    r = subprocess.run([sys.executable, str(REWRITER), str(repo)],
                       capture_output=True, text=True, timeout=3600, env=ENV,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr or r.stdout
    return r.stdout


def test_the_local_identity_is_gone(repo):
    d, shas = repo
    _rewrite(d)
    out = _git(d, "log", "--format=%ae", "--branches").stdout
    assert "KING@THRONE" not in out
    assert "dqikfox@users.noreply.github.com" in out


def test_the_third_party_authorship_is_untouched(repo):
    d, shas = repo
    _rewrite(d)
    emails = _git(d, "log", "--format=%ae", "--branches").stdout.split()
    assert "third@example.com" in emails
    assert "test@example.com" not in emails


def test_the_shared_ancestor_keeps_its_sha(repo):
    """The commit BELOW the offender is unchanged, so its SHA must be too."""
    d, shas = repo
    _rewrite(d)
    new_base = _git(d, "rev-list", "--max-parents=0", "main").stdout.strip()
    assert new_base == shas["base"], (
        "the base commit was re-created - the history is no longer connected")


def test_the_history_keeps_a_common_ancestor(repo):
    d, shas = repo
    _rewrite(d)
    r = subprocess.run([GIT, "-C", str(d), "merge-base", shas["top"],
                        _git(d, "rev-parse", "main").stdout.strip()],
                       capture_output=True, text=True, timeout=600, env=ENV,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0 and r.stdout.strip(), (
        "no common ancestor - a push would have to carry the whole repository")


def test_a_clean_branch_is_left_at_its_original_sha(repo):
    d, shas = repo
    _rewrite(d)
    assert _git(d, "rev-parse", "clean").stdout.strip() == shas["clean"]


def test_the_commit_above_the_offender_is_re_created(repo):
    d, shas = repo
    _rewrite(d)
    new_top = _git(d, "rev-parse", "main").stdout.strip()
    assert new_top != shas["top"], (
        "the commit above the offender must get a new parent, so a new SHA")


def test_the_trees_and_messages_survive(repo):
    d, shas = repo
    _rewrite(d)
    assert (d / "a.txt").read_text(encoding="utf-8") == "1"
    assert (d / "b.txt").read_text(encoding="utf-8") == "2"
    assert (d / "c.txt").read_text(encoding="utf-8") == "3"
    msgs = _git(d, "log", "--format=%s", "main").stdout.splitlines()
    assert "the offender" in msgs and "the top" in msgs and "the base" in msgs


def test_the_dated_metadata_is_preserved(repo):
    d, shas = repo
    _rewrite(d)
    # git renders the ISO date in UTC with a Z; the instant must be the same
    out = _git(d, "log", "--format=%aI", "main").stdout
    assert "2020-01-01T00:00:00" in out, "the author date was lost: %r" % out[:200]
    out2 = _git(d, "log", "--format=%cI", "main").stdout
    assert "2020-01-01T00:00:00" in out2, "the committer date was lost: %r" % out2[:200]


def test_the_offender_keeps_its_own_name_when_it_is_not_local(repo):
    d, shas = repo
    _rewrite(d)
    out = _git(d, "log", "--format=%an", "main").stdout
    assert "Third Party" in out
    assert "dqikfox" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
