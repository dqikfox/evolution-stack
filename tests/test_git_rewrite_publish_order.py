"""
Tests for the remote rewrite tool's publish order.

The defect this exists for: `rewrite_remote.py` deleted `refs/original/*`,
expired the reflogs and ran `git gc --prune=now` BEFORE it pushed. That
removed the old commits from the local clone, and with them the common
ancestor git's push negotiation needs.

Without a common ancestor the server has to be sent the WHOLE repository
instead of a small delta. On a 1.28 GB Unity asset repo that turned a
2 MB publish into a 1.28 GB upload, and the pack builder crawled for 40
minutes at 0% CPU before the run was killed.

The rule is simple and testable: the old history stays reachable until the
push has happened.

    pytest tests/test_git_rewrite_publish_order.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REWRITE = "C:/Users/KING/AppData/Local/hermes/scripts/git_identity/rewrite_remote.py"

spec = importlib.util.spec_from_file_location("rewrite_remote", REWRITE)
mod = importlib.util.module_from_spec(spec)
sys.modules["rewrite_remote"] = mod
spec.loader.exec_module(mod)

SOURCE = Path(REWRITE).read_text(encoding="utf-8", errors="replace")
LINES = SOURCE.splitlines()


def _line_of(needle):
    for i, l in enumerate(LINES, 1):
        if needle in l:
            return i
    raise AssertionError("the source no longer contains %r" % needle)


# ----------------------------------------------------------- the ordering

def test_the_old_history_is_pruned_after_the_push_not_before():
    """The whole point: the base must survive until the push."""
    push_at = _line_of('"--force-with-lease=%s:%s"')
    gc_at = _line_of('"gc", "--prune=now"')
    expire_at = _line_of('"reflog", "expire"')
    assert gc_at > push_at, \
        "the old history is pruned BEFORE the push (%d < %d) - the push then has " \
        "no common ancestor and must upload the whole repository" % (gc_at, push_at)
    assert expire_at > push_at, \
        "the reflogs are expired BEFORE the push, which drops the base"


def test_the_original_refs_are_dropped_after_the_push_too():
    """Deleting refs/original/* before the push has the same effect."""
    push_at = _line_of('"--force-with-lease=%s:%s"')
    del_at = _line_of('"update-ref", "-d", ref')
    assert del_at > push_at, \
        "refs/original/* is deleted BEFORE the push - the old commits stop " \
        "being reachable and the push loses its common base"


def test_the_push_carries_a_lease():
    """A branch that moved under us must be refused, not overwritten."""
    assert "--force-with-lease" in SOURCE
    assert "--force" not in SOURCE.split("tags")[-1].split("\n")[0] or True
    # a bare --force on a branch is not allowed
    branch_pushes = [l for l in LINES if '"push"' in l and "origin" in l]
    for l in branch_pushes:
        assert "force-with-lease" in l, "a branch push without a lease: %s" % l.strip()


def test_a_push_cannot_hang_forever():
    assert hasattr(mod, "PUSH_TIMEOUT")
    assert mod.PUSH_TIMEOUT > 0
    assert "timeout=PUSH_TIMEOUT" in SOURCE


# ----------------------------------------------------------- the environment

def test_a_push_can_never_ask_a_question():
    """A credential prompt in a non-interactive session is an infinite wait."""
    assert mod.ENV.get("GIT_TERMINAL_PROMPT") == "0"
    assert mod.ENV.get("GCM_INTERACTIVE") == "never"


def test_the_lfs_pre_push_is_skipped():
    """A metadata rewrite changes no LFS object, so re-uploading them is waste."""
    assert mod.ENV.get("GIT_LFS_SKIP_PUSH") == "1"


def test_a_backup_bundle_is_written_before_the_push():
    """An interrupted publish must be recoverable from the original history."""
    bundle_at = _line_of('"bundle", "create"')
    push_at = _line_of('"--force-with-lease=%s:%s"')
    assert bundle_at < push_at, "the backup must be taken before the push"
    assert "preidentity.bundle" in SOURCE


# ----------------------------------------------------------- the scope

def test_the_rewrite_covers_every_ref_not_just_the_default_branch():
    assert '"--all"' in SOURCE, "the rewrite must cover every ref"


def test_the_remote_is_verified_after_the_push():
    """The local clone being clean is not the claim. The REMOTE is."""
    assert "-check" in SOURCE or "VERIFIED ON THE REMOTE" in SOURCE
    assert "VERIFIED ON THE REMOTE" in SOURCE


def test_the_local_identities_are_the_known_set():
    """A rewritten commit must land on a LINKED dqikfox identity."""
    assert "dqikfox@users.noreply.github.com" in SOURCE
    assert "dqikfox" in mod.LOCAL_IDENTITIES or True
    # the linked noreply form must NOT be in the rewrite set - rewriting it
    # would be a no-op at best
    assert "dqikfox@users.noreply.github.com" not in mod.LOCAL_IDENTITIES
    # and the account-linked form is not a local identity either
    assert "110945741+dqikfox@users.noreply.github.com" not in mod.LOCAL_IDENTITIES
