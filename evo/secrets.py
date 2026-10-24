"""
secrets.py - detect secret-looking values in text before they get published.

This exists because of a real incident: the Evolution Stack's surface mirror
copied a launcher that contained a plaintext N8N_ENCRYPTION_KEY into a PUBLIC
git repository. A mirror that copies files verbatim will eventually copy a
secret, so the mirror has to be able to say no.

Design notes:
  * Deliberately narrow. A scanner that cries wolf gets switched off, and a
    switched-off scanner is worse than none. We only flag assignments whose
    NAME says "this is a secret" and whose VALUE looks like a real secret.
  * Values that are obviously not secrets (ports, hosts, paths, booleans,
    short words, known placeholders) are never flagged.
  * The scanner reports the file, the line and the NAME of the field. It never
    prints the value.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# a field name that means "this is a secret"
SECRET_NAME = re.compile(
    r"(?i)(pass(word|wd)?|secret|token|api[_-]?key|apikey|access[_-]?key|"
    r"private[_-]?key|encryption[_-]?key|credential|auth[_-]?key|session[_-]?key|"
    r"client[_-]?secret|bearer|signature|salt|seed)")

# assignment forms: NAME=value, NAME: value, "name": "value", set NAME=value
ASSIGN = re.compile(
    r"""(?x)
    (?P<name>[A-Za-z_][A-Za-z0-9_.\-]{1,48})
    \s*(?P<op>=|:)\s*
    (?P<quote>["']?)
    (?P<value>[^\s"',;#}\]]{6,200})
    """)
# PowerShell/batch style: set NAME=value
SET_ASSIGN = re.compile(r"(?i)\bset\s+(?P<name>[A-Za-z_][A-Za-z0-9_.\-]{1,48})=(?P<value>\S{6,200})")
# JSON style: "name": "value"
JSON_ASSIGN = re.compile(r'"(?P<name>[A-Za-z_][A-Za-z0-9_.\-]{1,48})"\s*:\s*"(?P<value>[^"]{6,200})"')

# high-confidence value shapes
PATTERNS = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("stripe_key", re.compile(r"\b[sr]k_(live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("hex_secret_32", re.compile(r"\b[0-9a-fA-F]{32,64}\b")),
    ("base64_secret_32", re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")),
    ("urlsafe_40", re.compile(r"\b[A-Za-z0-9_-]{40,}\b")),
]

# values that are never secrets
SAFE_VALUES = {
    "true", "false", "yes", "no", "none", "null", "undefined", "local",
    "localhost", "127.0.0.1", "0.0.0.0", "changeme", "change_me", "password",
    "example", "placeholder", "redacted", "***", "xxx", "todo", "fixme",
}
PLACEHOLDER = re.compile(r"(?i)^(?:<[^>]*>|\{\{.*\}\}|\$[A-Z_]+|%[A-Z_]+%|\.\.\.|"
                          r"\*\*\*|redacted|placeholder|example|your[_-]?\w+|"
                          r"changeme|xxx+|todo|none|null|true|false)$")
# a token-shaped value whose body is ONE repeated character is a
# documentation placeholder, not a credential: `ghp_` + 20 x's matches
# \bgh[pousr]_[A-Za-z0-9]{20,}\b perfectly, and a real token with 8+
# identical characters in a row is astronomically unlikely (~1e-13).
# The prefix may itself contain separators (sk-, sk-ant-, xoxb-), so allow
# a short word-ish prefix and require the RUN of x/star characters to be
# the tail of the value.
REDACTION_RUN = re.compile(r"(?i)^[A-Za-z0-9._-]{0,24}(?:x{8,}|\*{8,})$")
# a real PEM header (uppercase words only - a regex literal like
# "-----BEGIN [A-Z ]*PRIVATE KEY-----" is not a key)
PEM_HEADER = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
# a line that defines a detector, not a secret
DEFINES_PATTERN = re.compile(
    r"(?i)\b(re\.compile|re\.match|re\.search|re\.findall|re\.sub|"
    r"PATTERN|REGEX|re\.IGNORECASE)\b")

# a name that says the value is NOT a secret
SAFE_NAME = re.compile(r"(?i)(port|host|url|path|dir|file|user|email|name|"
                       r"timeout|interval|limit|size|version|model|log|"
                       r"level|count|index|width|height|charset|encoding)$")


@dataclass
class Finding:
    file: str
    line: int
    name: str
    kind: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} {self.kind} in field '{self.name}'"


def _is_env_reference(value: str) -> bool:
    """A value that reads its secret from somewhere else is not a secret."""
    v = value.strip()
    if v.startswith(("%", "$", "${", "op://", "env:", "op ")):
        return True
    if re.match(r"(?i)^(os\.environ|process\.env|getenv)", v):
        return True
    return False


def _value_is_secret(name: str, value: str) -> str | None:
    """Return the kind of secret this value looks like, or None."""
    v = value.strip().strip('"\'`,;')
    if len(v) < 8:
        return None
    if PLACEHOLDER.match(v):
        return None
    if REDACTION_RUN.match(v):
        return None
    if v.lower() in SAFE_VALUES:
        return None
    if _is_env_reference(v):
        return None
    # a path, a url, a date, a version, a number
    if re.match(r"^[A-Za-z]:\\", v) or v.startswith(("\\\\", "/", "./", "../")):
        return None
    if re.match(r"^https?://", v, re.I):
        return None
    if re.match(r"^[\d.]+$", v):
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return None
    if re.match(r"^v?\d+\.\d+(\.\d+)?", v) and "key" not in name.lower():
        return None
    # a space-separated sentence is prose, not a key
    if " " in v and not re.match(r"^\S+\s\S+$", v):
        return None
    for kind, pat in PATTERNS:
        if pat.search(v):
            return kind
    return None


def scan_text(text: str, file: str = "<text>") -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//", "REM ", "*")) and "=" not in stripped:
            continue
        if DEFINES_PATTERN.search(line):
            continue
        for m in list(ASSIGN.finditer(line)) + list(SET_ASSIGN.finditer(line)) + list(JSON_ASSIGN.finditer(line)):
            name = m.group("name")
            value = m.group("value")
            if not SECRET_NAME.search(name) or SAFE_NAME.search(name):
                continue
            kind = _value_is_secret(name, value)
            if kind:
                finding = Finding(file, i, name, kind)
                if finding not in findings:      # a line can match two patterns
                    findings.append(finding)
    # private key blocks anywhere - a real PEM header, not a regex that
    # merely mentions one (the scanner's own patterns must not flag itself)
    for i, line in enumerate(text.splitlines(), 1):
        if PEM_HEADER.search(line):
            findings.append(Finding(file, i, "private_key", "private_key_block"))
    return findings


def scan_file(path, max_bytes: int = 2_000_000) -> list[Finding]:
    from pathlib import Path
    p = Path(path)
    try:
        if p.stat().st_size > max_bytes:
            return []
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return scan_text(text, str(p))


DEFAULT_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
                "Library", "Temp", "dist", "build", ".pytest_cache",
                ".mypy_cache", "site-packages", ".next", "vendor"}


def scan_tree(root, suffixes=(".py", ".cmd", ".bat", ".ps1", ".sh", ".json", ".yaml",
                               ".yml", ".env", ".txt", ".cfg", ".ini", ".toml", ".md"),
              skip_dirs=None, max_files: int = 20000) -> list[Finding]:
    """Walk a tree and report secret-looking assignments.

    skip_dirs is a set of directory names to prune anywhere in the path.
    max_files bounds the walk so a pathological tree cannot hang a scan.
    """
    from pathlib import Path
    root = Path(root)
    skip = DEFAULT_SKIP | set(skip_dirs or ())
    out: list[Finding] = []
    if not root.exists():
        return out
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            seen += 1
            if seen > max_files:
                return out
            if Path(fn).suffix.lower() not in suffixes:
                continue
            out.extend(scan_file(Path(dirpath) / fn))
    return out
