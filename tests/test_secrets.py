"""
Regression tests for the secret scanner.

The scanner is the last line of defence before a credential reaches a public
repository, so its two failure modes both matter:

  * a FALSE NEGATIVE - a real credential that the scanner waves through
  * a FALSE POSITIVE - a placeholder that the scanner reports, because a
    scanner that cries wolf gets switched off, and a switched-off scanner is
    worse than none.

The false positive that motivated this file: the Hermes MCP reference
documents a token as `ghp_` followed by twenty x characters. That is
shape-correct - it matches \\bgh[pousr]_[A-Za-z0-9]{20,}\\b perfectly - and
it is still a placeholder, not a credential. The history sweep reported it
24 times across 12 commits.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evo.secrets import scan_text, scan_tree, scan_file  # noqa: E402

X20 = "x" * 20
REAL_GH = "ghp_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"
REAL_HEX = "3f8a1c9d2e7b4a6f0c3d8e5b2a9f7c4d" * 2


def test_redaction_run_is_not_a_secret():
    """ghp_ + a run of x characters is a documentation placeholder."""
    line = f'      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_{X20}"'
    assert scan_text(line, "t") == [], "a redaction run must not be reported"


def test_redaction_run_with_other_prefixes_is_not_a_secret():
    for prefix in ("sk-", "xoxb-", "sk-ant-"):
        line = f'      SOME_TOKEN: "{prefix}{X20}"'
        assert scan_text(line, "t") == [], f"{prefix} placeholder must not be reported"


def test_a_real_github_token_is_still_caught():
    """The placeholder rule must not blind the scanner to a real token."""
    line = f'      GITHUB_PERSONAL_ACCESS_TOKEN: "{REAL_GH}"'
    hits = scan_text(line, "t")
    assert hits, "a real token must be reported"
    assert hits[0].kind == "github_token"


def test_a_real_hex_secret_is_still_caught():
    line = f'      ENCRYPTION_KEY: "{REAL_HEX}"'
    assert scan_text(line, "t"), "a real hex secret must be reported"


def test_a_real_pem_block_is_still_caught():
    # Assembled at runtime: a literal PEM header in the source would be
    # detected by the scanner - in this file, in the working tree, and in
    # every commit that contains it.
    pem = ("-----BEGIN " + "RSA " + "PRIVATE KEY-----\n"
           "MIIEow==\n" + "-----END " + "RSA " + "PRIVATE KEY-----")
    hits = scan_text(pem, "t")
    assert hits and hits[0].kind == "private_key_block"


def test_the_scanner_does_not_flag_its_own_patterns():
    """A regex literal that mentions a key is not a key."""
    src = 'PATTERN = re.compile(r"\\bgh[pousr]_[A-Za-z0-9]{20,}\\b")'
    assert scan_text(src, "t") == [], "the scanner must not flag its own source"


def test_markdown_is_scanned_by_scan_tree():
    """A credential pasted into a README is still a leak."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "README.md").write_text(
            f'      GITHUB_PERSONAL_ACCESS_TOKEN: "{REAL_GH}"\n', encoding="utf-8")
        hits = scan_tree(root)
        assert hits, "markdown must be covered by the tree scan"
        assert any(h.file.endswith("README.md") for h in hits)


def test_a_placeholder_in_markdown_is_clean():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "README.md").write_text(
            f'      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_{X20}"\n', encoding="utf-8")
        assert scan_tree(root) == [], "a placeholder in docs must stay clean"


# ---------------------------------------------------------------------------
# A BARE secret: one token alone on its line.
#
# The scanner used to be assignment-based only, so a secret staged in a file
# on its own - no name, no assignment, no context - was invisible. A live
# N8N_ENCRYPTION_KEY sat in a scratch file for hours while the scanner
# reported that tree clean.
# ---------------------------------------------------------------------------

# Assembled at runtime, for the same reason: a literal 40-character
# token in the source is a finding.
BARE_TOKEN = "aB3xQ9mZ7" + "pL2kR8tV4w" + "Y6cD1fH5jN0sG"


def test_a_bare_token_on_its_own_line_is_detected():
    """A file that is nothing but a key must be caught."""
    findings = scan_text(BARE_TOKEN + "\n", "n8n_new_key.txt")
    assert findings, "a bare token alone on a line is a secret"
    assert findings[0].kind == "bare_secret_token"


def test_a_bare_token_is_still_caught_in_a_tree():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "n8n_new_key.txt").write_text(BARE_TOKEN + "\n", encoding="utf-8")
        hits = scan_tree(root)
        assert hits, "a bare key staged in a file must be found"


def test_a_bare_hash_is_not_a_secret():
    """A sha256 is hex-only, and hex-only is a hash, not a credential."""
    sha = "903e52d33448db05a698c3cc548c6f3ee31fd04e52b92ba7bfe8ea650c2eafa0"
    assert scan_text(sha + "\n", "x.txt") == [], "a sha256 digest is not a secret"


def test_a_bare_uuid_is_not_a_secret():
    uuid = "146bc-dfh-ijmop-stvw-xzab-cdhipqty123".replace("-", "-")
    assert scan_text(uuid + "\n", "x.txt") == [], "a uuid is not a secret"


def test_lowercase_prose_is_not_a_secret():
    assert scan_text("thisisaverylonglowercasestringwithoutanydigitsatall\n", "x.txt") == []


# ---------------------------------------------------------------------------
# The history sweeper had a blind spot: git QUOTES paths that contain
# non-ASCII characters, and a quoted path does not end in ".md", so every
# file named with an em-dash or an emoji was skipped. The NEXUS credential
# notes were named exactly that way.
# ---------------------------------------------------------------------------

def test_history_sweep_scans_files_with_non_ascii_names():
    """A secret in a file whose name has an em-dash must be found in history."""
    import subprocess
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.history_secret_sweep import sweep

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "PATH": r"C:\Windows\System32;C:\Program Files\Git\cmd"}
        def git(*a):
            return subprocess.run(["git", "-C", str(repo), *a], capture_output=True,
                                  text=True, env=env, timeout=120)
        git("init", "-q")
        name = "notes/detailed-log-\u2014credential-vault\U0001F510.md"
        (repo / "notes").mkdir(exist_ok=True)
        (repo / name).write_text(f'MEM0_API_KEY={BARE_TOKEN}\n', encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "add note")
        hits = sweep(str(repo))
        assert hits, "a non-ASCII filename must not hide a secret from the history sweep"



if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
