"""
Spawn a long-lived service as a fully detached child, with no inherited
handles.

Why this exists
---------------
On Windows, a process started with bInheritHandles=TRUE receives copies of
every inheritable handle in its parent - not just the three std handles. If
the parent was started by a caller that captured stdout into a pipe (an agent
tool, a CI step, ``$(...)`` in a shell), the write end of that pipe is
inheritable, so the child keeps it open for its whole life. The caller then
blocks in read() until the *service* exits, not until the launcher exits.

``cmd start`` and PowerShell ``Start-Process`` both inherit handles this way.
Python's ``subprocess`` does not, provided ``close_fds=True``: it builds an
explicit handle-inheritance list containing only the handles it means to pass.
So the fix is to do the spawn in Python, with ``close_fds=True``, and to
redirect the child's stdio to files rather than to the caller's streams.

Usage
-----
    python spawn_detached.py --log <file> [--err <file>] -- <command> [args...]

Exits 0 once the child is running, 1 if it could not be started.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Detach from the caller's console and give the child its own process group,
# so it survives the launcher and does not receive console control events.
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def spawn(command: list[str], cwd: str | None, log: str, err: str | None) -> int:
    log_path = Path(log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    err_path = Path(err) if err else Path(str(log_path) + ".err")
    err_path.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # A child service must not inherit the agent runtime's Python environment:
    # a shadowed PYTHONPATH makes a project venv load foreign packages.
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        env.pop(var, None)
    # UTF-8 for the child's own streams. The console code page on this host
    # is cp1252, so a child that writes a character outside it (the
    # 1Password CLI's error text, an emoji in a log line) dies with
    # UnicodeEncodeError - and a launcher that dies means a dead service.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    out_fh = open(log_path, "a", encoding="utf-8", errors="replace")
    err_fh = open(err_path, "a", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=out_fh,
            stderr=err_fh,
            env=env,
            close_fds=True,           # <- the whole point: no inherited handles
            creationflags=DETACHED | CREATE_NEW_GROUP | CREATE_NO_WINDOW,
        )
    finally:
        out_fh.close()
        err_fh.close()

    print(f"[spawn] pid={proc.pid} log={log_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Spawn a detached service with no inherited handles.")
    ap.add_argument("--log", required=True, help="stdout log file")
    ap.add_argument("--err", help="stderr log file (default: <log>.err)")
    ap.add_argument("--cwd", help="working directory for the child")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- <command> [args...]")
    args = ap.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("usage: spawn_detached.py --log <file> -- <command> [args...]", file=sys.stderr)
        return 1

    try:
        return spawn(command, args.cwd, args.log, args.err)
    except Exception as exc:  # noqa: BLE001 - launcher must report, not traceback
        print(f"[spawn] FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
