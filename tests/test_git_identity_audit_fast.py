"""
Tests for the FAST branch auditor and the rule it shares with the API one.

Why a second auditor
--------------------
The API auditor walks every commit of every branch through the GitHub
commits endpoint, 100 at a time. That is authoritative but it is
O(branches x history) HTTP round trips: `open-webui` alone pages through
95+ pages on a single dependabot branch, and the account has 68
repositories. The fast auditor does the same WORK in one local pass per
repository - a treeless bare clone plus a single `git log --all` - and
visits the API only for the proof and the control.

The rules these tests protect
-----------------------------
1. The offence is the email AND the link, not either one. An UNLINKED
   author is not automatically an offence: a third party's commit by an
   author with no GitHub account is unlinked too - the Manus AI fix bot,
   for instance. Flagging "unlinked" on its own produced four false
   positives on the largest repository in the account before it was fixed.

2. A branch name is URL-ENCODED before it goes into an API path. A branch
   carrying an emoji came back as an HTML error page, the JSON parser
   failed on it, and one branch of the largest repository could not be
   audited at all. A branch that could not be audited is not a clean
   branch.

3. The local scan must find a PLANTED offender before its negative results
   mean anything. A scan that cannot see a known offender proves nothing
   about the ones it did not see.

    pytest tests/test_git_identity_audit_fast.py -q
"""
import importlib.util
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

FAST_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/git_identity/verify_all_branches_fast.py"
API_PATH = "C:/Users/KING/AppData/Local/hermes/scripts/git_identity/verify_all_branches.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fast = _load("verify_all_branches_fast", FAST_PATH)
api = _load("verify_all_branches_api", API_PATH)


# ---------------------------------------------------------------- the rule

def test_a_local_identity_is_an_offence():
    assert "king@throne.local" in fast.BAD
    assert "ultron@throne.local" in fast.BAD
    assert "megatron@tesseract.local" in fast.BAD


def test_the_owners_own_public_identity_is_never_an_offence():
    """dqikfox@users.noreply.github.com IS the owner. Flagging it is absurd."""
    assert "dqikfox@users.noreply.github.com" not in fast.BAD
    assert "dqikfox@users.noreply.github.com" in fast.ALLOWED_EMAILS
    assert "110945741+dqikfox@users.noreply.github.com" not in fast.BAD


def test_the_api_auditor_uses_the_same_bad_set():
    """Two auditors, one rule. A drift here means two different verdicts."""
    assert fast.BAD == api.BAD


def test_unlinked_alone_is_not_an_offence():
    """The false positive that had to be undone.

    A commit by the Manus AI fix bot has no GitHub account, so its
    `author.login` is null and the expression substitutes UNLINKED. It is
    a third party and it is not the owner. It is not an offence.
    """
    login, email = "UNLINKED", "manus-ai@fix.bot"
    assert email.lower() not in fast.BAD
    # the rule is the email AND the link
    assert not (login == "UNLINKED" and email.lower() in fast.BAD)
    # a local identity that is unlinked IS an offence
    assert "king@throne.local" in fast.BAD


def test_the_api_auditors_hit_rule_keeps_the_link_in_the_judgement():
    """The API auditor's own rule: UNLINKED **and** a local email."""
    src = Path(API_PATH).read_text(encoding="utf-8", errors="replace")
    assert 'login == "UNLINKED" and email.lower() in BAD' in src
    # and it must NOT have the loose or-form
    assert 'login == "UNLINKED" or email' not in src


# ------------------------------------------------------------- encoding

def test_a_branch_name_is_url_encoded():
    """The emoji branch. Unencoded, the path returns an HTML error page."""
    branch = "\U0001f3a8-palette-add-aria-labels-8780607795307209901"
    q = urllib.parse.urlencode({"sha": branch, "per_page": 100, "page": 1})
    assert "%F0%9F%8E%A8" in q
    assert branch not in q


def test_both_auditors_encode_the_branch():
    for path in (API_PATH, FAST_PATH):
        src = Path(path).read_text(encoding="utf-8", errors="replace")
        assert "urllib.parse.urlencode" in src, path
        assert "import urllib.parse" in src, path


# ------------------------------------------------------- the local scan

def _git(*args, cwd):
    return subprocess.run([fast.GIT, "-C", str(cwd)] + list(args),
                          capture_output=True, text=True, timeout=300,
                          env=fast.ENV, encoding="utf-8", errors="replace")


def test_the_local_scan_finds_a_planted_offender(tmp_path):
    """The positive control, as a test.

    A commit authored by a local machine identity must be found by the
    same code path the audit uses. If this fails, every "clean" result
    the audit produces is worthless.
    """
    d = tmp_path / "repo"
    d.mkdir()
    _git("init", "-q", "-b", "main", cwd=d)
    with open(d / "a.txt", "w", encoding="utf-8") as f:
        f.write("planted\n")
    _git("add", "a.txt", cwd=d)
    r = subprocess.run(
        [fast.GIT, "-C", str(d), "-c", "user.name=THRONE",
         "-c", "user.email=king@throne.local", "commit", "-q", "-m", "planted"],
        capture_output=True, text=True, timeout=300, env=fast.ENV,
        encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    hits, err = fast.scan_local("control", str(d))
    assert err is None
    assert hits, "the planted local identity was not found - the scan is blind"
    assert any(h["email"].lower() in fast.BAD for h in hits)


def test_the_local_scan_does_not_flag_a_third_party(tmp_path):
    """A third party's unlinked author is not the owner."""
    d = tmp_path / "repo"
    d.mkdir()
    _git("init", "-q", "-b", "main", cwd=d)
    with open(d / "a.txt", "w", encoding="utf-8") as f:
        f.write("theirs\n")
    _git("add", "a.txt", cwd=d)
    subprocess.run(
        [fast.GIT, "-C", str(d), "-c", "user.name=Manus AI",
         "-c", "user.email=manus-ai@fix.bot", "commit", "-q", "-m", "theirs"],
        capture_output=True, text=True, timeout=300, env=fast.ENV,
        encoding="utf-8", errors="replace")
    hits, err = fast.scan_local("control", str(d))
    assert err is None
    assert not hits, "a third party was flagged as a local identity"


def test_the_local_scan_does_not_flag_the_owners_noreply(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    _git("init", "-q", "-b", "main", cwd=d)
    with open(d / "a.txt", "w", encoding="utf-8") as f:
        f.write("mine\n")
    _git("add", "a.txt", cwd=d)
    subprocess.run(
        [fast.GIT, "-C", str(d), "-c", "user.name=dqikfox",
         "-c", "user.email=dqikfox@users.noreply.github.com", "commit", "-q", "-m", "mine"],
        capture_output=True, text=True, timeout=300, env=fast.ENV,
        encoding="utf-8", errors="replace")
    hits, err = fast.scan_local("control", str(d))
    assert err is None
    assert not hits, "the owner's own public identity was flagged"


# ---------------------------------------------------------- the progress

def test_the_fast_auditor_writes_to_its_own_progress_file():
    assert "branch_audit_fast.json" in fast.PROGRESS
    assert fast.PROGRESS != api.PROGRESS


def test_the_fast_auditor_does_not_touch_the_api_auditors_progress():
    """Two auditors must not share a progress file - the second would clobber the first."""
    assert fast.PROGRESS != api.PROGRESS
    assert "branch_audit.json" not in fast.PROGRESS
