"""
Tests for the branch audit that decides whether the GitHub account is clean.

The rule these tests protect: an audit that CANNOT DETECT an offender must
never be trusted to CLEAR one. The bug this suite exists for was a jq
expression that failed to parse; the call returned non-zero, the pagination
loop broke, and every branch was reported clean. A broken query can only
ever produce a false all-clear, which is the most dangerous possible
failure for the tool that certifies the account.

    pytest tests/test_git_identity_audit.py -q
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

AUDIT_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/git_identity/verify_all_branches.py"
spec = importlib.util.spec_from_file_location("verify_all_branches", AUDIT_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_all_branches"] = mod
spec.loader.exec_module(mod)


# ------------------------------------------------------------------ the query

def test_the_jq_expression_is_defined_once_and_named():
    """The expression lives in a constant, so it cannot be escaped wrong twice."""
    assert hasattr(mod, "JQ_COMMIT")
    src = Path(AUDIT_PATH).read_text(encoding="utf-8", errors="replace")
    # the expression must be USED from the constant, not re-typed
    assert '"--jq", JQ_COMMIT' in src


def test_the_jq_expression_has_no_double_escaped_quotes():
    """The old bug: '\\"' inside a jq string is a parse error in jq.

    jq rejects it with "unexpected token" and gh exits non-zero, which the
    old script mistook for a clean branch.
    """
    assert '\\"' not in mod.JQ_COMMIT, "the jq expression must not contain an escaped quote"
    assert "UNLINKED" in mod.JQ_COMMIT
    # exactly one set of field selectors
    assert mod.JQ_COMMIT.count("author.login") == 1
    assert mod.JQ_COMMIT.count("commit.author.email") == 1


def test_the_commits_call_uses_the_constant():
    src = Path(AUDIT_PATH).read_text(encoding="utf-8", errors="replace")
    # no inline jq for the commits query
    assert not re.search(r'--jq", "\.\\[\\]', src), \
        "the commits query must use the JQ_COMMIT constant, not an inline expression"


# ------------------------------------------------------------------ the failure mode

def test_an_api_error_is_never_reported_as_a_clean_branch(monkeypatch):
    """A refusal must be an ERROR, not an empty hit list."""
    calls = []

    def fake_retry(*args, **kw):
        calls.append(args)
        return "", "the API refused: rate limit"

    monkeypatch.setattr(mod, "gh_retry", fake_retry)
    hits, err = mod.audit_branch("dqikfox/x", "some-branch")
    assert err is not None, "an API error was swallowed"
    assert "rate limit" in err
    # a clean branch and an un-auditable branch must never look the same
    assert hits == []


def test_a_branch_listing_error_is_reported(monkeypatch):
    def fake_retry(*args, **kw):
        return "", "the API refused"

    monkeypatch.setattr(mod, "gh_retry", fake_retry)
    names, err = mod.branches_of("dqikfox/x")
    assert err is not None
    assert names == []


def test_a_rate_limit_is_retried_not_given_up_on(monkeypatch):
    """A rate limit is an infrastructure condition, not a verdict."""
    attempts = []

    def fake_gh(*args, **kw):
        attempts.append(args)
        if len(attempts) < 3:
            class R:
                returncode = 1
                stdout = ""
                stderr = "API rate limit exceeded"
            return R
        class R:
            returncode = 0
            stdout = "dqikfox\n"
            stderr = ""
        return R

    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    out, err = mod.gh_retry("api", "whatever")
    assert err is None
    assert out.strip() == "dqikfox"
    assert len(attempts) == 3


def test_a_rate_limit_is_recognised():
    assert mod._is_rate_limited("API rate limit exceeded for user")
    assert mod._is_rate_limited("You have exceeded a secondary rate limit")
    assert not mod._is_rate_limited("Not Found")


# ------------------------------------------------------------------ the verdict

def test_the_verdict_distinguishes_clean_from_incomplete(monkeypatch, capsys):
    """An incomplete audit must NOT say 'EVERY BRANCH IS CLEAN'."""
    monkeypatch.setattr(mod, "audit", lambda repo: (0, 5, 3))  # 3 branches un-audited
    mod.main(["dqikfox/a", "dqikfox/b"])
    out = capsys.readouterr().out
    assert "EVERY BRANCH IS CLEAN" not in out
    assert "COULD NOT BE AUDITED" in out
    assert "NOT A CLEAN BILL OF HEALTH" in out


def test_a_verdict_with_offenders_is_not_clean(monkeypatch, capsys):
    monkeypatch.setattr(mod, "audit", lambda repo: (2, 5, 0))
    mod.main(["dqikfox/a"])
    out = capsys.readouterr().out
    assert "THE ACCOUNT IS NOT CLEAN" in out
    assert "EVERY BRANCH IS CLEAN" not in out


def test_a_fully_clean_audit_says_so(monkeypatch, capsys):
    monkeypatch.setattr(mod, "audit", lambda repo: (0, 5, 0))
    mod.main(["dqikfox/a"])
    out = capsys.readouterr().out
    assert "EVERY BRANCH IS CLEAN" in out


# ------------------------------------------------------------------ the self-test

def test_the_self_test_exists_and_is_reachable():
    """The tool must be able to prove it can detect an offender."""
    assert callable(mod.selftest)
    src = Path(AUDIT_PATH).read_text(encoding="utf-8", errors="replace")
    assert "--selftest" in src
    # the self-test must use a branch that is KNOWN to be offending
    assert "QHYSICS" in src
    assert "reality-engine" in src


def test_the_self_test_fails_when_the_detector_is_broken(monkeypatch, capsys):
    """If the detector finds nothing where an offender is known, it FAILS."""
    monkeypatch.setattr(mod, "audit_branch", lambda repo, branch: ([], None))
    monkeypatch.setattr(mod, "gh", lambda *a, **k: type("R", (), {
        "returncode": 0, "stdout": "a|b|c", "stderr": ""})())
    rc = mod.selftest()
    out = capsys.readouterr().out
    assert rc != 0, "a broken detector was allowed to pass the self-test"
    assert "NOT TRUSTWORTHY" in out


def test_the_self_test_passes_when_the_detector_works(monkeypatch, capsys):
    monkeypatch.setattr(mod, "audit_branch", lambda repo, branch: ([("KING@THRONE", "abc")], None))
    monkeypatch.setattr(mod, "gh", lambda *a, **k: type("R", (), {
        "returncode": 0, "stdout": "a|b|c", "stderr": ""})())
    rc = mod.selftest()
    out = capsys.readouterr().out
    assert rc == 0
    assert "TRUSTWORTHY" in out
