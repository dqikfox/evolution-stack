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
    pem = "REDACTED_PRIVATE_KEY_HEADER\nMIIEow==\n-----END RSA PRIVATE KEY-----"
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
