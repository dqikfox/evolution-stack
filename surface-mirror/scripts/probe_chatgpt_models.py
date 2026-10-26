"""Probe which models the ChatGPT Plus session can actually serve.

Codex CLI carries a ChatGPT OAuth session (auth_mode: chatgpt), so it reaches
OpenAI on the user's Plus subscription - no API key, no credit balance. This
proves which models that session can serve, with a FRESH NONCE per model, so
the answer cannot be echoed from the prompt.

    python probe_chatgpt_models.py
"""
import json
import os
import pathlib
import secrets
import string
import subprocess
import sys

B = r"C:\Users\KING\.codex\plugins\.plugin-appserver\codex.exe"
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)

CANDIDATES = ["gpt-6-astra", "gpt-5.1-codex-max", "gpt-5.1-codex", "gpt-5-codex",
              "gpt-6", "gpt-5.1"]


def nonce():
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


def run(prompt, model, timeout=420):
    cmd = [B, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-m", model, prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=ENV,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", 124
    return (r.stdout or ""), (r.stderr or ""), r.returncode


def main():
    results = []
    for model in CANDIDATES:
        n = nonce()
        out, err, rc = run("Reply with exactly this token and nothing else: " + n, model)
        ok = n in out
        tokens = ""
        for l in out.splitlines():
            if "tokens used" in l:
                tokens = l.strip().split("tokens used")[-1].strip()
        errmsg = ""
        for l in out.splitlines():
            if "ERROR" in l:
                errmsg = l[:180]
                break
        results.append({"model": model, "ok": ok, "tokens": tokens, "error": errmsg})
        print("   %-20s %-6s tokens=%-10s %s" % (model, "OK" if ok else "FAIL",
                                                  tokens or "-", errmsg[:110]), flush=True)
        if ok:
            break
    out_path = pathlib.Path(r"C:\Users\KING\AppData\Local\hermes\state\chatgpt_models.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\n   written to %s" % out_path)
    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
