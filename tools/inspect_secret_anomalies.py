"""Inspect the three secret-map anomalies without printing any value.

1. ANTHROPIC_API_KEY resolves to 11 characters. A real Anthropic key
   starts with 'sk-ant-' and is ~100 chars, so an 11-char value is a
   placeholder. Report whether it LOOKS like a placeholder and whether
   the vault holds a real key under another title.

2. ELEVENLABS_VOICE_ID is a literal in the config map, and its 1Password
   item has only a notesPlain field. Check whether the note CONTAINS the
   bare id, and whether a dedicated field can be used instead.

3. The .env carries five secrets that are not in the map at all
   (XAI_API_KEY, HF_TOKEN, HUGGINGFACE_TOKEN, IBM_API_KEY, DI_APIKEY).
   Check whether the vault already holds each under an obvious title, and
   whether it resolves to the SAME value the .env holds.

Only lengths, verdicts and truncated digests are printed.
"""
import hashlib
import json
import os
import re
import subprocess

HOME = os.path.expandvars(r"%LOCALAPPDATA%\hermes")
ENV = os.path.join(HOME, ".env")
VAULT = "credentials"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def env_values(path):
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.strip().strip('"')
        if v:
            out[k.strip()] = v
    return out


def op_json(args):
    try:
        res = subprocess.run(["op"] + args + ["--vault", VAULT, "--format", "json"],
                             capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except Exception:
        return None


def op_read(ref):
    try:
        res = subprocess.run(["op", "read", ref], capture_output=True, text=True, timeout=90)
    except Exception:
        return None
    return res.stdout.strip("\r\n") if res.returncode == 0 else None


def main():
    env = env_values(ENV)

    print("=== 1. ANTHROPIC_API_KEY (11 chars from the vault) ===")
    ref = "op://credentials/ANTHROPIC_API_KEY/credential"
    val = op_read(ref)
    if val is None:
        print("  reference did not resolve")
    else:
        low = val.lower()
        placeholder_words = ("placeholder", "replace", "changeme", "todo", "redacted",
                              "dummy", "example", "your", "xxxx", "none", "null")
        is_placeholder = any(w in low for w in placeholder_words)
        print("  len              :", len(val))
        print("  looks placeholder:", is_placeholder)
        print("  starts 'sk-ant-' :", val.startswith("sk-ant-"))
        print("  charset          :", "".join(sorted(set(c for c in val if not c.isalnum()))))
        print("  sha              :", digest(val))
    items = op_json(["item", "list"]) or []
    anth = [i.get("title") for i in items if "anthropic" in i.get("title", "").lower()]
    print("  vault items matching 'anthropic':", anth or "(none)")

    print()
    print("=== 2. ELEVENLABS_VOICE_ID ===")
    cfg = open(os.path.join(HOME, "config.yaml"), encoding="utf-8", errors="replace").read()
    m = re.search(r"ELEVENLABS_VOICE_ID:\s*(\S+)", cfg)
    literal = m.group(1).strip('"') if m else ""
    item = op_json(["item", "get", "ELEVENLABS_VOICE_ID"]) or {}
    fields = {f.get("label"): (f.get("value") or "") for f in item.get("fields", [])}
    note = fields.get("notesPlain", "")
    print("  config literal   : len=%d sha=%s" % (len(literal), digest(literal)))
    print("  item fields      :", {k: len(v) for k, v in fields.items()})
    if note:
        print("  note contains id :", literal in note)
        if literal and literal in note:
            idx = note.index(literal)
            print("  note prefix      : len=%d %r" % (idx, note[max(0, idx - 12):idx][-12:]))
    agent_item = op_json(["item", "get", "ElevenLabs Agent ID"]) or {}
    agent_fields = {f.get("label"): (f.get("value") or "") for f in agent_item.get("fields", [])}
    m2 = re.search(r"ELEVENLABS_AGENT_ID:\s*(\S+)", cfg)
    agent_literal = m2.group(1).strip('"') if m2 else ""
    for label, val in agent_fields.items():
        if val and val == agent_literal:
            print("  agent id field   : %r matches the literal exactly" % label)

    print()
    print("=== 3. .env secrets absent from the map ===")
    candidates = {
        "XAI_API_KEY": "XAI_API_KEY",
        "HF_TOKEN": "HF_TOKEN",
        "HUGGINGFACE_TOKEN": "HF_TOKEN",
        "IBM_API_KEY": "IBM_API_KEY",
        "DI_APIKEY": "IBM_API_KEY",
    }
    for env_name, item_title in candidates.items():
        if env_name not in env:
            print("  %-20s not in .env" % env_name)
            continue
        plain = env[env_name]
        resolved = op_read("op://credentials/%s/credential" % item_title)
        if resolved is None:
            print("  %-20s .env len=%-4d | vault: no credential field" % (env_name, len(plain)))
            continue
        same = digest(plain) == digest(resolved)
        print("  %-20s .env len=%-4d sha=%s | vault len=%-4d sha=%s  => %s"
              % (env_name, len(plain), digest(plain), len(resolved), digest(resolved),
                 "MATCH" if same else "DIFFERENT"))


if __name__ == "__main__":
    main()
