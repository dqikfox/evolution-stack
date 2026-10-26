"""
chatgpt_worker.py - hand a real task to ChatGPT and let it do the work.

The Codex CLI is a full agent: it can read and write files, run commands, and
work inside a sandbox. Pointed at a working directory, it becomes a worker
that can finish a task rather than only answer a question.

The ChatGPT Plus session is already authenticated in ~/.codex/auth.json, so
this needs no API key and costs no marginal money.

Usage:
    chatgpt_worker.py "add a --version flag to the CLI"            # in the cwd
    chatgpt_worker.py "fix the failing test" --cwd C:/project/x
    chatgpt_worker.py "write the report" --cwd C:/out --json
    chatgpt_worker.py "check the repo" --read-only

Safety:
    * The default sandbox is workspace-write: the worker may change files
      inside --cwd and nowhere else.
    * --read-only forces the read-only sandbox, so the worker can only
      inspect and report.
    * The session is ephemeral: no session files are left behind.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

CODEX_BIN = r"C:\Users\KING\.codex\plugins\.plugin-appserver\codex.exe"
CODEX_BIN_FALLBACK = r"C:\Users\KING\.codex\.sandbox-bin\codex.exe"
DEFAULT_TIMEOUT = 900


def _binary() -> str:
    for b in (CODEX_BIN, CODEX_BIN_FALLBACK):
        if pathlib.Path(b).is_file():
            return b
    raise SystemExit("the Codex CLI is not installed at %s" % CODEX_BIN)


def _env() -> dict:
    env = dict(os.environ)
    # The child must not inherit a foreign Python or virtualenv state.
    for k in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        env.pop(k, None)
    return env


def run(task: str, cwd: str | None = None, read_only: bool = False,
        model: str = "gpt-6-astra", timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run one task with ChatGPT. Returns a result dict."""
    binary = _binary()
    work = pathlib.Path(cwd).resolve() if cwd else pathlib.Path.cwd()
    if not work.is_dir():
        raise SystemExit("the working directory does not exist: %s" % work)

    sandbox = "read-only" if read_only else "workspace-write"
    cmd = [binary, "exec", "--skip-git-repo-check", "--sandbox", sandbox,
           "--ephemeral", "--json", "-m", model, "-C", str(work), task]

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=_env(), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout after %ss" % timeout,
                "elapsed": round(time.time() - t0, 2), "cwd": str(work), "text": ""}

    events, text, usage, errors = [], "", None, []
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        events.append(ev)
        t = ev.get("type")
        if t == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message":
                text = str(item.get("text", "")).strip()
            if item.get("type") == "command_execution":
                cmd_out = item.get("aggregated_output") or ""
                if cmd_out.strip():
                    text += ("\n[command] " + cmd_out.strip()[:4000])
        if t == "turn.completed" and isinstance(ev.get("usage"), dict):
            usage = ev["usage"]
        if t == "error":
            errors.append(json.dumps(ev)[:300])
    if not text:
        text = (r.stderr or r.stdout or "").strip()[-4000:]

    return {
        "ok": r.returncode == 0 and bool(text),
        "returncode": r.returncode,
        "model": model,
        "cwd": str(work),
        "sandbox": sandbox,
        "elapsed": round(time.time() - t0, 2),
        "text": text,
        "usage": usage,
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Hand a task to ChatGPT and let it work")
    ap.add_argument("task", help="what you want done")
    ap.add_argument("--cwd", default=None, help="the working directory")
    ap.add_argument("--model", default="gpt-6-astra")
    ap.add_argument("--read-only", action="store_true",
                    help="forbid changes; the worker may only inspect and report")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true", help="print the raw result")
    a = ap.parse_args()

    res = run(a.task, cwd=a.cwd, read_only=a.read_only, model=a.model, timeout=a.timeout)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(res["text"])
        print("\n--- %s | %s | %.1fs | sandbox=%s | rc=%s" % (
            res["model"], res["cwd"], res["elapsed"], res["sandbox"], res["returncode"]),
            file=sys.stderr)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
