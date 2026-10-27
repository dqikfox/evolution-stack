"""Show the final state of the Hermes secret map.

Reads config.yaml's secrets.<source>.env mapping and reports, per name,
whether the value is an op:// reference or a literal, plus the count of
op:// references that actually resolve. No secret value is printed.
"""
import os
import re
import subprocess
import sys

HOME = os.path.expandvars(r"%LOCALAPPDATA%\hermes")
CONFIG = os.path.join(HOME, "config.yaml")


def op_read(ref):
    try:
        res = subprocess.run(["op", "read", ref], capture_output=True, text=True, timeout=90)
    except Exception:
        return None
    return res.stdout.strip("\r\n") if res.returncode == 0 else None


def main():
    text = open(CONFIG, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()

    in_secrets = False
    env_indent = None
    entries = []
    for line in lines:
        if re.match(r"^secrets:\s*$", line):
            in_secrets = True
            continue
        if not in_secrets:
            continue
        if line.strip() and not line[0].isspace():
            break
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if re.match(r"^\s*env:\s*$", line) and env_indent is None:
            env_indent = indent
            continue
        if env_indent is None:
            continue
        if indent <= env_indent:
            env_indent = None
            continue
        m = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\S+)\s*$", line)
        if m:
            entries.append((m.group(1), m.group(2).strip('"')))

    refs = [(n, v) for n, v in entries if v.startswith("op://")]
    lits = [(n, v) for n, v in entries if not v.startswith("op://")]
    print("secrets map entries : %d  (op:// %d, literal %d)" % (len(entries), len(refs), len(lits)))
    print()
    print("literal entries still in the map:")
    for n, v in lits:
        print("   %-24s %s" % (n, v[:70]))
    if not lits:
        print("   (none)")

    print()
    print("resolving every op:// reference:")
    ok = bad = 0
    for n, v in refs:
        val = op_read(v)
        if val is None:
            bad += 1
            print("   UNRESOLVED %-24s %s" % (n, v))
        else:
            ok += 1
    print("   %d resolved, %d unresolved" % (ok, bad))

    print()
    print("selected references:")
    for n, v in refs:
        if "ELEVENLABS" in n or n in ("XAI_API_KEY", "IBM_API_KEY", "DI_APIKEY", "HF_TOKEN",
                                      "HUGGINGFACE_TOKEN", "STRIPE_SECRET_KEY", "API_SERVER_KEY"):
            print("   %-24s -> %s" % (n, v))


if __name__ == "__main__":
    main()
