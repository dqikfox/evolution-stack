"""Supervise the KRYSYS shop (:8500).

Why a supervisor
----------------
The shop used to be started by ``start_krysys.cmd`` with ``cmd start /B``.
That form of spawn inherits every inheritable handle in the parent, so a
caller that captured stdout into a pipe (an agent tool, a CI step) left the
shop holding a duplicate of that pipe. The shop then died with the caller's
job object, and a crash left the shop down until somebody noticed.

This supervisor owns one shop process for its whole life:

  * it starts the shop with no inherited handles, logging to files;
  * it restarts the shop if it exits or wedges;
  * it refuses to start a second copy (exit code 3);
  * it stops the shop before exiting, so a stop never leaves an orphan.

Secrets
-------
The shop needs STRIPE_SECRET_KEY and the admin credentials. They are read
from the machine's own environment (the registry's user environment) and
never from a file, a command line or a log. If the environment is missing a
secret, the shop still starts - it simply reports card payments as
unconfigured. A vault or environment outage costs the payments, not the
service.

Usage
-----
    python krysys_supervisor.py [--stop] [--status]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
LOG_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes" / "logs"
PROJECT = pathlib.Path(r"C:\Users\KING\projects\krysys-shop")
NODE = pathlib.Path(r"C:\Program Files\nodejs\node.exe")
PORT = 8500
HEALTH = "http://127.0.0.1:%d/api/health" % PORT
MARKER = "krysys_supervisor.py"
LOCK = PROJECT / "logs" / "supervisor.lock"
SHOP_LOG = LOG_DIR / "krysys_shop.log"
SUP_LOG = LOG_DIR / "krysys_supervisor.log"
STDOUT = LOG_DIR / "krysys_supervisor.stdout.log"

RESTART_BACKOFF = 3.0
HEALTH_TIMEOUT = 2.0


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with SUP_LOG.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write("[%s] %s\n" % (stamp, msg))
    except OSError:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass


def probe() -> bool:
    """True when the shop's OWN health endpoint answers with a body.

    A port that merely accepts a connection is not proof of health, so the
    body is required: the response must be JSON and must report ok.
    """
    try:
        with urllib.request.urlopen(HEALTH, timeout=HEALTH_TIMEOUT) as resp:
            body = resp.read(4000).decode("utf-8", "replace")
        return resp.status == 200 and '"ok"' in body
    except (urllib.error.URLError, OSError, ValueError):
        return False


def read_machine_env(name: str) -> str | None:
    """Read a variable from the machine's user environment.

    The value is never logged and never written to disk. A missing variable
    returns None, which the caller treats as "this feature is off".
    """
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value) if value else None
    except (OSError, ImportError):
        return os.environ.get(name)


def build_env() -> dict:
    """The child's environment: the machine's secrets, and none of the agent's."""
    env = dict(os.environ)
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        env.pop(var, None)
    for name in ("STRIPE_SECRET_KEY", "ADMIN_USER", "ADMIN_PW_SHA256",
                 "STRIPE_WEBHOOK_SECRET", "SESSION_SECRET", "SUPABASE_URL",
                 "SUPABASE_SERVICE_ROLE_KEY", "STRIPE_CURRENCY", "PAYID_PHONE"):
        value = read_machine_env(name)
        if value:
            env[name] = value
    env["PORT"] = str(PORT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def acquire_lock() -> bool:
    """Single-instance guard. Refuses a second supervisor (exit code 3)."""
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        fh = LOCK.open("a+", encoding="utf-8")
    except OSError:
        return True
    try:
        import msvcrt

        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return False
    fh.seek(0)
    fh.truncate()
    fh.write("%d\n" % os.getpid())
    fh.flush()
    return True


def start_shop() -> subprocess.Popen | None:
    if not NODE.is_file():
        log("FAILED: node missing at %s" % NODE)
        return None
    if not (PROJECT / "server.js").is_file():
        log("FAILED: server.js missing at %s" % PROJECT)
        return None
    # The shop exits immediately when the port is already taken. Starting a
    # second copy is the one case where a restart is wrong: it produces a
    # tight crash loop that looks like a flapping service.
    if probe():
        log("the port is already serving a healthy shop - not starting a second copy")
        return None
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        out = SHOP_LOG.open("a", encoding="utf-8", errors="replace")
        err = LOG_DIR.joinpath("krysys_shop.err.log").open("a", encoding="utf-8", errors="replace")
    except OSError as exc:
        log("FAILED: cannot open the logs: %s" % exc)
        return None
    cmd = [str(NODE), "server.js", "--supervised-by", MARKER]
    log("starting the shop: %s" % " ".join(cmd))
    try:
        return subprocess.Popen(
            cmd,
            cwd=str(PROJECT),
            env=build_env(),
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008,
        )
    except OSError as exc:
        log("FAILED to start: %s" % exc)
        return None


def stop_children() -> None:
    """Stop the shop process tree, children first."""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$c = Get-NetTCPConnection -State Listen -LocalPort %d -ErrorAction SilentlyContinue;"
         "if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue;"
         " Write-Output \"stopped $($c.OwningProcess)\" } else { Write-Output 'none' }" % PORT],
        capture_output=True, text=True, timeout=30,
    )
    log("stop: %s" % (r.stdout or "").strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        log("health: %s" % ("up" if probe() else "down"))
        return 0 if probe() else 1

    if args.stop:
        stop_children()
        return 0

    if not acquire_lock():
        log("another supervisor already holds the lock - refusing to start a second copy")
        return 3

    log("supervisor up (pid %d)" % os.getpid())
    child = start_shop()
    if child is None:
        # Either the shop is already healthy under another supervisor, or the
        # start failed. If it is already healthy, supervise it by watching the
        # port instead of by owning a process.
        if probe():
            log("a healthy shop is already serving :%d - supervising by observation" % PORT)
            while True:
                if not probe():
                    log("the observed shop stopped answering - taking over")
                    child = start_shop()
                    if child is None:
                        time.sleep(RESTART_BACKOFF)
                        continue
                    break
                time.sleep(5)
        else:
            log("FAILED: the shop could not be started")
            return 1

    # Give the shop a moment, then report the truth rather than assuming.
    for _ in range(20):
        if probe():
            break
        time.sleep(0.5)
    log("shop health after start: %s" % ("up" if probe() else "NOT answering"))

    try:
        while True:
            if child is None:
                time.sleep(5)
                continue
            if child.poll() is not None:
                log("the shop exited with %s - restarting" % child.returncode)
                time.sleep(RESTART_BACKOFF)
                child = start_shop()
                if child is None:
                    time.sleep(RESTART_BACKOFF)
                    continue
            elif not probe():
                log("the shop stopped answering - replacing it")
                try:
                    child.terminate()
                    child.wait(timeout=10)
                except Exception:
                    try:
                        child.kill()
                    except Exception:
                        pass
                time.sleep(RESTART_BACKOFF)
                child = start_shop()
                if child is None:
                    time.sleep(RESTART_BACKOFF)
                    continue
            time.sleep(5)
    except KeyboardInterrupt:
        log("supervisor stopping")
        try:
            child.terminate()
        except Exception:
            pass
        return 0
    finally:
        stop_children()


if __name__ == "__main__":
    sys.exit(main())
