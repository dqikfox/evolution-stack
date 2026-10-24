"""
n8n_launcher.py - start n8n with its encryption key resolved from 1Password.

Why this exists: the key used to live in plaintext inside start_n8n.cmd,
and the Evolution Stack's surface mirror copied that file into a public
Git repository. A secret that is in a launcher is a secret that leaks.

This launcher:
  * resolves N8N_ENCRYPTION_KEY from 1Password (DPAPI-cached fallback),
  * passes it to n8n in the child environment only - never on a command
    line, never in a file,
  * starts n8n detached, with its output in a log file and with
    close_fds=True so the child never inherits the launching session's
    stdout pipe (a long-lived service holding that pipe keeps the session
    alive forever and replays its stale buffer as endless heartbeats).

Usage: python n8n_launcher.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_resolver import resolve  # noqa: E402

NODE_EXE = Path(r"C:\Users\KING\AppData\Local\hermes\node\node.exe")
N8N_BIN = Path(r"C:\Users\KING\AppData\Local\npm-cache\_npx\ce64108ad803af1c\node_modules\n8n\bin\n8n")
N8N_USER_FOLDER = Path(r"C:\Users\KING\.n8n")
LOG = Path(r"C:\Users\KING\AppData\Local\hermes\logs\n8n.log")
OP_REF = "op://credentials/N8N_ENCRYPTION_KEY/credential"


def main() -> int:
    if not NODE_EXE.exists():
        print(f"n8n_launcher: node missing at {NODE_EXE}", file=sys.stderr)
        return 1
    if not N8N_BIN.exists():
        print(f"n8n_launcher: n8n missing at {N8N_BIN}", file=sys.stderr)
        return 1

    try:
        key = resolve("n8n_encryption_key", OP_REF)
    except RuntimeError as e:
        print(f"n8n_launcher: {e}", file=sys.stderr)
        return 1

    env = dict(os.environ)
    env["N8N_ENCRYPTION_KEY"] = key
    env["N8N_USER_FOLDER"] = str(N8N_USER_FOLDER)
    env["N8N_PORT"] = "5678"
    env["N8N_HOST"] = "127.0.0.1"
    # keep the child off the agent's python environment
    for var in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(var, None)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n--- n8n start {__import__('time').strftime('%Y-%m-%d %H:%M:%S')} "
                  f"(key from 1Password, not logged) ---\n")
        log.flush()
        proc = subprocess.Popen(
            [str(NODE_EXE), str(N8N_BIN), "start"],
            cwd=str(N8N_USER_FOLDER),
            stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    print(f"n8n_launcher: started n8n pid={proc.pid} on :5678 (log: {LOG})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
