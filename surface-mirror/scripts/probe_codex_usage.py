"""Read the token usage out of a Codex CLI JSONL run.

The CLI reports usage in a turn.completed event. The router needs it so the
ledger can distinguish providers by their token signature.

    python probe_codex_usage.py
"""
import json
import os
import pathlib
import secrets
import string
import subprocess
import tempfile

B = r"C:\Users\KING\.codex\plugins\.plugin-appserver\codex.exe"
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)


def main():
    n = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    with tempfile.TemporaryDirectory() as tmp:
        last = pathlib.Path(tmp) / "l.txt"
        r = subprocess.run([B, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                            "--ephemeral", "--json", "-m", "gpt-6-astra", "-o", str(last),
                            "Reply with exactly this token and nothing else: " + n],
                           capture_output=True, text=True, timeout=900, env=ENV,
                           encoding="utf-8", errors="replace")
        print("rc=%s  the nonce echoed=%s" % (r.returncode, n in (r.stdout or "")))
        print("\n=== the event stream ===")
        usage = None
        for line in (r.stdout or "").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = ev.get("type")
            if t in ("turn.completed", "thread.started", "error", "item.completed"):
                print("   %-22s %s" % (t, json.dumps(ev)[:260]))
            u = ev.get("usage")
            if isinstance(u, dict):
                usage = u
            if t == "turn.completed" and isinstance(ev.get("usage"), dict):
                usage = ev["usage"]
        print("\n=== the usage ===\n   %s" % json.dumps(usage, indent=2)[:600])
        out = pathlib.Path(r"C:\Users\KING\AppData\Local\hermes\state\codex_usage.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"usage": usage, "nonce_ok": n in (r.stdout or "")},
                                  indent=2), encoding="utf-8")
        print("   written to %s" % out)


if __name__ == "__main__":
    main()
