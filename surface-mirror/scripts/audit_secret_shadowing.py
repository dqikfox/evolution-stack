"""Audit whether the plaintext .env shadows the 1Password vault.

The Hermes env loader applies dotenv with override=True BEFORE the
external secret sources run, and a source SKIPS a name that already
exists in the environment. So a literal value in ~/.hermes/.env silently
wins over the op:// reference in config.yaml's secrets map, and the vault
of record stops being authoritative for that name.

This compares, by SHA-256, the value each op:// reference actually
resolves to against the plaintext .env / config literal for the same
name. No secret value is ever printed: only lengths, verdict and a
truncated digest.
"""
import hashlib
import os
import re
import subprocess
import sys

HOME = os.path.expandvars(r"%LOCALAPPDATA%\hermes")
ENV = os.path.join(HOME, ".env")
CONFIG = os.path.join(HOME, "config.yaml")
VAULT = "credentials"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def read_env_literals(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            val = val.strip().strip('"')
            if val:
                out[key.strip()] = val
    return out


def read_secret_map(path):
    """Pull the secrets.onepassword.env mapping out of config.yaml.

    Only the names inside the `env:` mapping are real variables. Keys
    such as `onepassword`, `enabled` or `cache_ttl_seconds` are YAML
    structure and must not be reported as literal secrets.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    out = {}
    in_secrets = False
    env_indent = None
    for line in lines:
        if re.match(r"^secrets:\s*$", line):
            in_secrets = True
            continue
        if in_secrets:
            if line.strip() and not line[0].isspace():
                break
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            m = re.match(r"^(\s*)env:\s*$", line)
            if m and env_indent is None:
                env_indent = indent
                continue
            if env_indent is None:
                continue
            if indent <= env_indent:
                env_indent = None
                continue
            m = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\S.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"')
    return out


def op_read(ref):
    """Resolve an op:// reference to its value, or None."""
    try:
        res = subprocess.run(
            ["op", "read", ref],
            capture_output=True, text=True, timeout=90,
        )
    except Exception:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip("\r\n")


def main():
    env_literals = read_env_literals(ENV)
    secret_map = read_secret_map(CONFIG)

    print("op:// references in config.yaml :", sum(1 for v in secret_map.values() if v.startswith("op://")))
    print("literal entries in config.yaml  :", sum(1 for v in secret_map.values() if not v.startswith("op://")))
    print()

    shadowed, matching, diverging, unresolvable = [], [], [], []

    for name, ref in sorted(secret_map.items()):
        if not ref.startswith("op://"):
            continue
        resolved = op_read(ref)
        if resolved is None:
            unresolvable.append(name)
            continue
        if name not in env_literals:
            matching.append((name, "vault-only", len(resolved)))
            continue
        plain = env_literals[name]
        if digest(plain) == digest(resolved):
            shadowed.append((name, len(plain), digest(plain)))
        else:
            diverging.append((name, len(plain), len(resolved), digest(plain), digest(resolved)))

    print("=== .env literal == vault value (SAFE TO STRIP) ===")
    for name, ln, dg in shadowed:
        print("  %-26s len=%-4d sha=%s" % (name, ln, dg))
    if not shadowed:
        print("  (none)")

    print()
    print("=== .env literal != vault value (VAULT IS STALE) ===")
    for name, pl, rl, pd, rd in diverging:
        print("  %-26s .env len=%-4d sha=%s   |  vault len=%-4d sha=%s" % (name, pl, pd, rl, rd))
    if not diverging:
        print("  (none)")

    print()
    print("=== vault only (no .env literal) ===")
    for name, kind, ln in matching:
        print("  %-26s %-12s len=%d" % (name, kind, ln))
    if not matching:
        print("  (none)")

    print()
    print("=== unresolvable reference ===")
    for name in unresolvable:
        print("  ", name)
    if not unresolvable:
        print("  (none)")

    print()
    print("=== literal entries in the config map (not op://) ===")
    for name, val in sorted(secret_map.items()):
        if not val.startswith("op://"):
            print("  %-26s literal len=%d sha=%s" % (name, len(val), digest(val)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
