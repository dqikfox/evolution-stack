#!/usr/bin/env python
"""Hold the vector-rebuild lock, exclusively, for as long as the caller lives.

THE PROBLEM THIS SOLVES
------------------------
The rebuild lock is a signal that says "a rebuild is running, do not
start the server". The consumer of that signal is
tools/rebuild_lock_guard.py, which decides whether the lock is LIVE or
STALE by asking two questions:

  1. is the recorded pid still alive?
  2. is any rebuild process running?

Question 1 is the one that matters BETWEEN passes. The wrapper runs
each pass as a separate short-lived reindex_vectors.py process, with a
twenty-second gap between them. During that gap there is NO rebuild
process running - question 2 answers no - so the lock's liveness rests
entirely on question 1: is the recorded pid alive?

So the recorded pid must be a process alive for the WHOLE sequence. It
cannot be the process that takes the lock, because that process exits
immediately.

THE FIRST TWO ATTEMPTS AT THAT, AND WHY THEY FAILED
---------------------------------------------------
Attempt one: record the pid of the process that took the lock. It
exits immediately, so the recorded pid was dead the instant the lock
was written. The guard declared the lock stale, cleared it, and
started NEXUS onto a half-built index. Observed on 2026-10-28, in the
middle of a real rebuild.

Attempt two: record the parent's pid. On Windows os.getppid() does not
change when the parent dies - Windows does not reparent the way POSIX
does - and the wrapper's cmd.exe is not the keeper's direct parent
anyway, because "start /b" interposes one. The venv python is itself a
shim that re-executes the real interpreter, so the "parent" the keeper
sees is the shim, and the shim lives as long as the keeper does. The
keeper therefore outlived the wrapper, kept the lock, and kept the
caller's output pipe open. The maintenance script hung on a rebuild
that had already succeeded. Observed on 2026-10-28.

THE SECOND HALF OF THE PROBLEM: THE INHERITED PIPE
---------------------------------------------------
"start /b" runs the child in the same console with the same handles.
The maintenance script captures the wrapper's output, so it waits for
the output pipe to close - and the keeper holds a duplicate of that
pipe open for as long as it lives. So even with the keeper's own
stdout redirected, the child still inherited the pipe handle, because
Windows handle inheritance passes EVERY inheritable handle, not just
the ones that were redirected.

So the holder is spawned DETACHED: DETACHED_PROCESS, a new process
group, DEVNULL for all three standard handles, and close_fds. It
inherits nothing from the wrapper at all.

HOW IT WORKS
------------
  1. The caller takes the lock with O_CREAT|O_EXCL - atomically, so
     exactly one caller can win and every other caller is told the
     lock is held and stops. "if not exist" is not a lock, it is a
     hint: two wrappers started in the same second both saw no file,
     both created one, and both ran their passes against the same
     Chroma file, the second dropping the collection the first was
     filling.
  2. The caller spawns the DETACHED HOLDER, which writes its pid to
     <lock>.pid and waits.
  3. The caller waits for <lock>.pid, then writes the holder's pid
     into the lock file. From that moment the lock names a process
     that is alive for the whole sequence.
  4. The holder watches the lock file. When it is gone - the wrapper
     deletes it when the rebuild finishes - the holder releases and
     exits. That is the signal, and it is race-free.

Usage
-----
    nexus_reindex_lock.py <lockfile>              take the lock, then exit
    nexus_reindex_lock.py <lockfile> --hold       take the lock, spawn
                                                  the detached holder,
                                                  and return
    nexus_reindex_lock.py <lockfile> --hold-child the holder itself

Exit codes
----------
  0  the lock is held (and, with --hold, a holder is holding it)
  3  the lock is already held by somebody else - do not proceed
  4  the lock could not be taken
"""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_LOCK = Path(r"E:\ultron-memory\nexus-core\data\REBUILD.lock")

# How often the holder checks whether the lock is still there.
POLL_SECONDS = 2.0


# --------------------------------------------------------------------------
# The holder.
# --------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    """Is this pid still running?

    os.getppid() is NOT a liveness check on Windows: when the parent
    dies, Windows does not reparent the child the way POSIX does, so
    getppid() keeps returning the dead parent's pid forever. The
    parent's liveness is asked of Windows directly, the same way
    tools/rebuild_lock_guard.py asks it: tasklist.
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # If the check itself fails, assume the pid is alive. The
        # failure mode is a lock held a little too long, not a lock
        # lost, and the guard reclaims a stale lock anyway.
        return True
    return str(pid) in out


def _holder(lock: Path) -> int:
    """Hold the lock until it is released, then exit.

    The lock file's disappearance is the signal. The wrapper deletes
    it when the rebuild finishes - on the completed path and on the
    exhausted path alike - so the file going away is an unambiguous
    statement that the rebuild is over, and it is race-free.
    """
    pidfile = lock.with_suffix(lock.suffix + ".pid")
    try:
        pidfile.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    print(f"[reindex] holding the rebuild lock at {lock} "
          f"(holder pid {os.getpid()})", flush=True)

    def _release(*_args) -> None:
        for p in (pidfile, lock):
            try:
                p.unlink()
            except OSError:
                pass

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGBREAK):
        try:
            signal.signal(sig, lambda *_: _release())
        except (ValueError, OSError, AttributeError):
            pass
    atexit.register(_release)

    while True:
        time.sleep(POLL_SECONDS)
        if not lock.exists():
            print("[reindex] the lock was released - the rebuild is over",
                  flush=True)
            break
    _release()
    return 0


# --------------------------------------------------------------------------
# Taking the lock.
# --------------------------------------------------------------------------

def _take(lock: Path) -> int:
    """Take the lock exclusively. Returns 0 on success, 3 if held."""
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[reindex] could not create {lock.parent}: {exc}", file=sys.stderr)
        return 4

    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Somebody else holds it. Read what they wrote so the operator
        # can see who, and refuse.
        try:
            held = lock.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            held = "unknown"
        print(f"[reindex] the rebuild lock is already held: {lock}")
        print(f"[reindex]   contents : {held}")
        print("[reindex] refusing to start - two rebuilds against one "
              "Chroma file deadlock each other.")
        return 3
    except OSError as exc:
        print(f"[reindex] could not take {lock}: {exc}", file=sys.stderr)
        return 4

    try:
        body = (f"vector index rebuild started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(holder pending)")
        os.write(fd, body.encode("utf-8"))
    finally:
        os.close(fd)
    return 0


def _spawn_holder(lock: Path) -> int:
    """Spawn the detached holder and name it in the lock file."""
    pidfile = lock.with_suffix(lock.suffix + ".pid")
    try:
        pidfile.unlink()
    except OSError:
        pass

    # DETACHED_PROCESS: a new console, not this one. CREATE_NEW_PROCESS_GROUP:
    # so a Ctrl-C to the wrapper's group does not take the holder with it.
    # DEVNULL on all three standard handles: the holder inherits no pipe
    # from the wrapper, so the caller's captured output closes when the
    # wrapper exits. close_fds: no other handle is inherited either.
    flags = 0
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    try:
        child = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), str(lock), "--hold-child"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )
    except OSError as exc:
        print(f"[reindex] could not start the lock holder: {exc}", file=sys.stderr)
        return 4

    # Wait for the holder to publish its pid, so the lock can name a
    # process that is definitely alive.
    holder_pid = None
    for _ in range(50):
        time.sleep(0.2)
        try:
            holder_pid = int(pidfile.read_text(encoding="utf-8").strip())
            break
        except (OSError, ValueError):
            continue
    if holder_pid is None:
        print("[reindex] the lock holder never reported its pid", file=sys.stderr)
        return 4

    # Name the holder in the lock. The file already exists and was
    # created exclusively, so this is a rewrite, not a second lock.
    try:
        lock.write_text(
            f"vector index rebuild started {time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(holder, pid {holder_pid})\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[reindex] could not record the holder pid: {exc}", file=sys.stderr)
        return 4

    print(f"[reindex] holding the rebuild lock at {lock} (holder pid {holder_pid})")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    hold = "--hold" in argv[1:]
    child = "--hold-child" in argv[1:]
    lock = Path(args[0]) if args else DEFAULT_LOCK

    if child:
        return _holder(lock)

    rc = _take(lock)
    if rc != 0:
        return rc

    if hold:
        rc = _spawn_holder(lock)
        if rc != 0:
            # The lock was taken but no holder owns it. Give it back
            # rather than leave a lock nobody will release.
            try:
                lock.unlink()
            except OSError:
                pass
        return rc

    print(f"[reindex] holding the rebuild lock at {lock}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
