"""Verify the estate still resolves every secret after the hardening.

Loads the environment the way Hermes does (hermes_cli.env_loader), then
reports which secret names are present, their length and a truncated
digest. No value is printed. Also checks the two ElevenLabs agent ids
against the live API to settle which one the estate should be using.
"""
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.expandvars(r"%LOCALAPPDATA%\hermes"), "hermes-agent"))

EXPECTED = [
    "XAI_API_KEY", "ELEVENLABS_API_KEY", "STRIPE_SECRET_KEY", "API_SERVER_KEY",
    "HF_TOKEN", "HUGGINGFACE_TOKEN", "IBM_API_KEY", "DI_APIKEY",
    "ANTHROPIC_API_KEY", "OLLAMA_API_KEY", "TELEGRAM_BOT_TOKEN",
    "TWILIO_AUTH_TOKEN", "NOTION_API_KEY", "TAILSCALE_API_KEY",
    "ELEVENLABS_VOICE_ID", "ELEVENLABS_AGENT_ID", "ELEVENLABS_MODEL_ID",
]


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def main():
    from hermes_cli.env_loader import load_hermes_dotenv
    load_hermes_dotenv()

    print("=== secret names present in the loaded environment ===")
    missing = []
    for name in EXPECTED:
        val = os.environ.get(name)
        if val is None:
            missing.append(name)
            print("  %-24s MISSING" % name)
        else:
            print("  %-24s present len=%-4d sha=%s" % (name, len(val), digest(val)))
    print()
    print("missing:", missing or "none")

    print()
    print("=== .env no longer carries the secrets ===")
    env_path = os.path.expandvars(r"%LOCALAPPDATA%\hermes\.env")
    for line in open(env_path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        name = s.partition("=")[0].strip()
        if name in EXPECTED and name != "OP_SERVICE_ACCOUNT_TOKEN":
            print("  STILL PRESENT:", name)
    print("  (only the bootstrap token should remain)")

    print()
    print("=== which ElevenLabs agent id is live? ===")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("  no ELEVENLABS_API_KEY in the environment")
        return
    config_text = open(os.path.expandvars(r"%LOCALAPPDATA%\hermes\config.yaml"),
                       encoding="utf-8", errors="replace").read()
    import re
    m = re.search(r"ELEVENLABS_AGENT_ID:\s*(\S+)", config_text)
    config_agent = m.group(1).strip('"') if m else ""
    try:
        vault_item = subprocess.run(
            ["op", "item", "get", "ElevenLabs Agent ID", "--vault", "credentials", "--format", "json"],
            capture_output=True, text=True, timeout=90)
        import json
        data = json.loads(vault_item.stdout)
        fields = {f.get("label"): (f.get("value") or "") for f in data.get("fields", [])}
    except Exception:
        fields = {}
    vault_agent = fields.get("ElevenLabs Agent ID", "")

    for label, agent in (("config literal", config_agent), ("vault field", vault_agent)):
        if not agent:
            print("  %-16s (absent)" % label)
            continue
        res = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "-H", "xi-api-key: " + key, "https://api.elevenlabs.io/v1/agents/" + agent],
            capture_output=True, text=True, timeout=90)
        print("  %-16s sha=%s  /v1/agents -> HTTP %s"
              % (label, digest(agent), res.stdout.strip()))


if __name__ == "__main__":
    main()
