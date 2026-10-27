"""Make the 1Password vault the single source of truth for the estate's secrets.

Two defects are corrected here.

DEFECT 1 - shadowing. The env loader applies dotenv with override=True
BEFORE the external secret sources run, and a source skips a name that
already exists in the environment. A literal in ~/.hermes/.env therefore
wins over the op:// reference in config.yaml, and the vault stops being
authoritative. Every value removed from .env is first proven byte-identical
to the value the vault reference resolves to.

DEFECT 2 - literal entries in the secret map. A handful of names are
plaintext inside config.yaml's secrets.onepassword.env map, so the
1Password source skips them with "is not an op:// secret reference" and
they never rotate. They become real op:// references, backed by a
dedicated 1Password field so the reference resolves to the bare value and
not to a note.

Edits to config.yaml are surgical line edits, never a YAML round-trip:
a round-trip would reformat the whole 331-key file.

Nothing is printed except lengths, verdicts and truncated digests.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOME = os.path.expandvars(r"%LOCALAPPDATA%\hermes")
ENV_PATH = os.path.join(HOME, ".env")
CONFIG_PATH = os.path.join(HOME, "config.yaml")
VAULT = "credentials"

# Never removed from .env: the 1Password source needs the service account
# token to authenticate in the first place, so it is the bootstrap.
BOOTSTRAP = {"OP_SERVICE_ACCOUNT_TOKEN"}

# .env name -> (1Password item title, 1Password field)
NEW_MAP_ENTRIES = {
    "XAI_API_KEY": ("XAI_API_KEY", "credential"),
    "HF_TOKEN": ("HF_TOKEN", "credential"),
    "HUGGINGFACE_TOKEN": ("HF_TOKEN", "credential"),
    "IBM_API_KEY": ("IBM_API_KEY", "credential"),
    "DI_APIKEY": ("IBM_API_KEY", "credential"),
}

# config map literal -> (item title, field to create/use)
LITERAL_TO_REF = {
    "ELEVENLABS_VOICE_ID": ("ELEVENLABS_VOICE_ID", "ELEVENLABS_VOICE_ID"),
    "ELEVENLABS_AGENT_ID": ("ElevenLabs Agent ID", "ElevenLabs Agent ID"),
}


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def op(args, timeout=120):
    try:
        res = subprocess.run(["op"] + args, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        print("   op %s failed: %s" % (args[0], exc))
        return None
    if res.returncode != 0:
        print("   op %s -> rc=%d %s" % (args[0], res.returncode, res.stderr.strip()[:120]))
        return None
    return res.stdout


def op_read(ref):
    out = op(["read", ref])
    return out.strip("\r\n") if out is not None else None


def op_item(title):
    out = op(["item", "get", title, "--vault", VAULT, "--format", "json"])
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def backup(path, label):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = "%s.bak-%s-%s" % (path, label, stamp)
    shutil.copy2(path, dest)
    print("   backup -> %s" % os.path.basename(dest))
    return dest


def read_env(path):
    """Return (ordered lines, {key: value})."""
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    values = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        values[k.strip()] = v.strip().strip('"')
    return lines, values


def main():
    config_text = open(CONFIG_PATH, encoding="utf-8", errors="replace").read()
    config_lines = config_text.splitlines()
    env_lines, env_values = read_env(ENV_PATH)

    print("== step 1: give the two literal map entries a real 1Password field ==")
    for map_name, (item_title, field_name) in LITERAL_TO_REF.items():
        match = re.search(r"^\s+%s:\s*(\S+)\s*$" % re.escape(map_name), config_text, re.M)
        if not match:
            print("   %-22s not found in the config map" % map_name)
            continue
        literal = match.group(1).strip('"')
        item = op_item(item_title)
        if item is None:
            print("   %-22s vault item %r not found" % (map_name, item_title))
            continue
        fields = {f.get("label"): (f.get("value") or "") for f in item.get("fields", [])}
        if fields.get(field_name) == literal:
            print("   %-22s field %r already holds the value" % (map_name, field_name))
            continue
        # Is the literal recoverable from a note? Only then promote it.
        recovered = None
        for label, val in fields.items():
            if val and literal in val:
                recovered = val
                print("   %-22s found inside field %r" % (map_name, label))
                break
        if recovered is None:
            print("   %-22s value not recoverable from the item; left alone" % map_name)
            continue
        op(["item", "edit", item_title, "%s=%s" % (field_name, literal),
            "--vault", VAULT])
        check = op_item(item_title) or {}
        now = {f.get("label"): (f.get("value") or "") for f in check.get("fields", [])}
        ok = now.get(field_name) == literal
        print("   %-22s field %r written: %s" % (map_name, field_name, "OK" if ok else "FAILED"))

    print()
    print("== step 2: the 1Password source must resolve every map entry ==")
    resolved_map = {}
    for line in config_lines:
        m = re.match(r"^\s{6}([A-Za-z0-9_]+):\s*(\S+)\s*$", line)
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip('"')
        if not val.startswith("op://"):
            continue
        resolved = op_read(val)
        if resolved is None:
            print("   %-24s UNRESOLVABLE %s" % (name, val))
            continue
        resolved_map[name] = (val, resolved)
    print("   resolvable references: %d" % len(resolved_map))

    print()
    print("== step 3: add the .env-only secrets to the map, proven identical ==")
    for env_name, (item_title, field) in NEW_MAP_ENTRIES.items():
        if env_name not in env_values:
            print("   %-20s not in .env" % env_name)
            continue
        ref = "op://%s/%s/%s" % (VAULT, item_title, field)
        vault_value = op_read(ref)
        if vault_value is None:
            print("   %-20s vault has no %r field" % (env_name, field))
            continue
        plain = env_values[env_name]
        if digest(plain) != digest(vault_value):
            print("   %-20s DIFFERS from the vault - not added" % env_name)
            continue
        if env_name in resolved_map:
            print("   %-20s already in the map" % env_name)
            continue
        # Insert next to the other API key entries.
        anchor = None
        for i, line in enumerate(config_lines):
            if re.match(r"^\s+API_SERVER_KEY:\s*", line):
                anchor = i + 1
                break
        if anchor is None:
            for i, line in enumerate(config_lines):
                if re.match(r"^\s+YANDEX_FOLDER_ID:\s*", line):
                    anchor = i + 1
                    break
        if anchor is None:
            print("   %-20s no anchor line found" % env_name)
            continue
        config_lines.insert(anchor, "      %s: %s" % (env_name, ref))
        resolved_map[env_name] = (ref, vault_value)
        print("   %-20s added -> %s" % (env_name, ref))

    print()
    print("== step 4: turn the two config literals into references ==")
    for map_name, (item_title, field_name) in LITERAL_TO_REF.items():
        for i, line in enumerate(config_lines):
            m = re.match(r"^(\s+)%s:\s*(\S+)\s*$" % re.escape(map_name), line)
            if not m:
                continue
            indent, val = m.group(1), m.group(2).strip('"')
            if val.startswith("op://"):
                print("   %-22s already a reference" % map_name)
                break
            ref = "op://%s/%s/%s" % (VAULT, item_title, field_name)
            vault_value = op_read(ref)
            if vault_value is None or vault_value != val:
                print("   %-22s reference does not resolve to the same value - left as literal"
                      % map_name)
                break
            config_lines[i] = "%s%s: %s" % (indent, map_name, ref)
            resolved_map[map_name] = (ref, vault_value)
            print("   %-22s -> %s" % (map_name, ref))
            break

    print()
    print("== step 5: strip the shadowed literals from .env ==")
    backup(CONFIG_PATH, "secrets")
    backup(ENV_PATH, "secrets")
    new_config = "\n".join(config_lines) + "\n"
    with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_config)

    removable = []
    for name, (ref, vault_value) in resolved_map.items():
        if name in BOOTSTRAP or name not in env_values:
            continue
        if digest(env_values[name]) == digest(vault_value):
            removable.append(name)
        else:
            print("   %-22s .env differs from the vault - kept" % name)
    for name in removable:
        print("   %-22s removed from .env (vault identical)" % name)
    keep = []
    for line in env_lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.partition("=")[0].strip()
            if key in removable:
                continue
        keep.append(line)
    with open(ENV_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(keep) + "\n")
    print("   .env: %d -> %d lines" % (len(env_lines), len(keep)))

    print()
    print("== step 6: the Anthropic key ==")
    item = op_item("ANTHROPIC_API_KEY") or {}
    fields = {f.get("label"): (f.get("value") or "") for f in item.get("fields", [])}
    note = fields.get("notesPlain", "")
    real = re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", note)
    if real:
        key = real.group(0)
        op(["item", "edit", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY=%s" % key, "--vault", VAULT])
        check = op_item("ANTHROPIC_API_KEY") or {}
        now = {f.get("label"): (f.get("value") or "") for f in check.get("fields", [])}
        print("   promoted a real key from the note into the field: %s"
              % ("OK" if now.get("ANTHROPIC_API_KEY") == key else "FAILED"))
    else:
        print("   no real key in the note - the vault holds a placeholder only")
        print("   action needed: issue a key in the Anthropic console and store it as")
        print("   ANTHROPIC_API_KEY in the %s vault" % VAULT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
