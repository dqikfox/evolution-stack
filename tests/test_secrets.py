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



# ---------------------------------------------------------------------------
# NAME-INDEPENDENT rules: a credential in prose.
#
# The scanner was assignment-based, so it needed a field name that looked
# secret-ish. A credential pasted into a note has no field name, and a
# webhook URL ends in "_URL", so the name looked harmless too. The history
# sweep reported 0 findings across 247 commits while a live Telegram token
# sat in prose in one of them.
#
# Assembled at runtime, for the same reason as every other fixture here: a
# literal token in the source is itself a finding.
# ---------------------------------------------------------------------------
TG_TOKEN = str(123456789) + ":" + "Aq7" + "b" * 32
HF_TOKEN = "hf_" + "c" * 34
NOTION_TOKEN = "secret_" + "d" * 40
XAI_KEY = "xai-" + "e" * 40
DISCORD_HOOK = ("https://discord.com/api/webhooks/" + "1" * 18 + "/" + "f" * 68)


def test_a_telegram_token_in_prose_is_detected():
    """A token in a sentence has no field name; the shape is the credential."""
    line = "the bot token for the throne bot is " + TG_TOKEN + " keep it safe"
    hits = scan_text(line, "note.md")
    assert hits, "a telegram token in prose must be detected"
    assert hits[0].kind == "telegram_bot_token"


def test_a_telegram_token_under_a_safe_looking_name_is_detected():
    """'*_URL' looks harmless, but a webhook URL is a credential."""
    line = 'DISCORD_WEBHOOK_URL = "' + DISCORD_HOOK + '"'
    hits = scan_text(line, "cfg.py")
    assert hits, "a webhook URL must be detected even when the name says url"
    assert hits[0].kind == "discord_webhook"


def test_a_huggingface_token_in_prose_is_detected():
    hits = scan_text("use " + HF_TOKEN + " for the model pull", "note.md")
    assert hits, "a huggingface token must be detected"
    assert hits[0].kind == "huggingface_token"


def test_a_notion_token_in_prose_is_detected():
    hits = scan_text("notion integration " + NOTION_TOKEN, "note.md")
    assert hits, "a notion token must be detected"
    assert hits[0].kind == "notion_token"


def test_an_xai_key_in_prose_is_detected():
    hits = scan_text("XAI_API_KEY is " + XAI_KEY, "note.md")
    assert hits, "an xai key must be detected"
    assert hits[0].kind == "xai_api_key"


def test_a_placeholder_token_is_not_reported():
    """A run of x characters is documentation, not a credential."""
    line = "the token is " + str(123456789) + ":" + "A" + "x" * 34
    assert scan_text(line, "doc.md") == [], "a placeholder token must stay clean"


def test_the_prose_rules_do_not_flag_their_own_source():
    """The scanner's own pattern literals must not read as credentials."""
    src = ('PROSE = re.compile(r"\\b\\d{8,10}:[A-Za-z0-9_-]{35}\\b")\n'
           'HOOK = re.compile(r"discord(?:app)?\\.com/api/webhooks/\\d+/[A-Za-z0-9_-]{60,}")\n')
    assert scan_text(src, "t") == [], "the scanner must not flag its own source"


def test_ordinary_prose_is_not_a_secret():
    """The prose rules must not turn a note into a finding."""
    line = ("we talked about the schedule for tuesday and the cost of the "
            "hardware was about 12 hundred dollars in total")
    assert scan_text(line, "note.md") == [], "ordinary prose must stay clean"


def test_a_refusal_is_reported_not_silent():
    """A file the mirror refuses must be visible in the command output.

    The mirror refuses a file that holds a secret-shaped value and
    records it in mirror.REFUSED. If the command does not surface that,
    a refusal is indistinguishable from a clean run - the file is simply
    missing from the public repository and the credential stays in the
    clear in the working tree.
    """
    import io
    import json as _json
    import sys as _sys
    from contextlib import redirect_stderr, redirect_stdout
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from evo import mirror
    from evo.loop import cmd_mirror

    class _Args:
        diff = False
        all = True

    # plant a file with a prose credential in the mirrored source tree
    root = mirror.paths.SKILLS_DIR / "control-refusal-probe"
    root.mkdir(parents=True, exist_ok=True)
    probe = root / "SKILL.md"
    probe.write_text(
        "---\nname: control-refusal-probe\ndescription: Use when testing refusals.\n---\n\n"
        "the throne bot token is " + str(123456789) + ":" + "Aq7" + "b" * 32 + "\n",
        encoding="utf-8")
    published = mirror.MIRROR / "skills" / "control-refusal-probe" / "SKILL.md"
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            cmd_mirror(_Args())
        payload = _json.loads(out.getvalue())
        assert payload.get("refused"), "a refusal must be reported in the output"
        assert any("control-refusal-probe" in r["file"] for r in payload["refused"]), \
            "the refused file must be named"
        assert "REFUSED" in err.getvalue(), "a refusal must be printed to stderr"
        assert not published.exists(), "a file with a secret must never be published"
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        if published.exists():
            published.unlink()


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
