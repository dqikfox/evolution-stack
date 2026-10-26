"""Prove the ChatGPT provider in the router, with a fresh nonce.

The router's `chatgpt` provider rides the Codex CLI's ChatGPT Plus OAuth
session. The proof must be a NONCE the router itself generated, so the answer
cannot have been echoed from the prompt.

    python probe_router_chatgpt.py
"""
import importlib.util
import json
import os
import pathlib
import secrets
import string
import sys

ROUTER = r"C:\Users\KING\AppData\Local\hermes\scripts\provider_router.py"
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)


def load():
    spec = importlib.util.spec_from_file_location("pr_chatgpt_probe", ROUTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    pr = load()
    p = pr.Provider("chatgpt", "codex", "", "gpt-6-astra",
                    cost_tier="chatgpt", priority=25, local=True)

    nonce = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    print("the router-generated nonce: %s" % nonce)

    text, meta = pr.call(p, "Reply with exactly this token and nothing else: " + nonce,
                          max_tokens=32, timeout=420)
    ok = nonce in text
    print("served provider: %s   model: %s" % (meta.get("provider"), meta.get("model")))
    print("elapsed: %ss   tokens_in: %s   tokens_out: %s   cost: $%s"
          % (meta.get("elapsed"), meta.get("tokens_in"), meta.get("tokens_out"),
             meta.get("cost_usd")))
    print("the nonce was echoed: %s" % ok)
    print("the answer: %s" % text.strip()[:200])

    # the health probe path, which is what the estate gate uses
    probe = pr.probe(p, timeout=420)
    print("\nthe health probe: %s" % json.dumps(
        {k: probe.get(k) for k in ("provider", "model", "status", "elapsed", "error")}))

    out = {"nonce_echoed": bool(ok), "meta": {k: v for k, v in meta.items() if k != "error"},
           "probe": {k: probe.get(k) for k in ("provider", "status", "elapsed", "error")}}
    p_out = pathlib.Path(r"C:\Users\KING\AppData\Local\hermes\state\chatgpt_router_proof.json")
    p_out.parent.mkdir(parents=True, exist_ok=True)
    p_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\nwritten to %s" % p_out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
