"""Bring the api_server platform up as soon as the vault allows it.

The platform was enabled and pointed at env:API_SERVER_KEY, but that
variable was not in the 1Password map, so the adapter refused to start and
:8642 was dead - the TESSERACT dashboard showed a red HERMES API card that
nobody could explain. The mapping is now in the config; it takes effect on
the next gateway start.

Why this is a script and not a command:

  * A gateway start re-resolves EVERY mapped secret (21 of them), and
    1Password rate-limits the client. Restarting while the vault is
    limited would take working platforms down to fix one broken one.
  * Every `hermes` CLI call ALSO re-resolves the whole map, so even
    checking the state costs the quota.

So: probe the vault with ONE read. Only when that read succeeds, restart
the gateway, then verify the platform answers. The probe is cheap, and the
expensive restart happens only when it is safe.

    python fix_api_server_platform.py            # one attempt
    python fix_api_server_platform.py --wait 45  # poll for up to 45 minutes
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERMES = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes"
HEALTH = "http://127.0.0.1:8642/health"
TOKEN_FILE = Path.home() / ".ultron" / ".op_service_account"
VAULT = "credentials"
ITEM = "API_SERVER_KEY"
PROBE_ITEM = "TAILSCALE_API_KEY"   # a cheap, always-present item


def find_op() -> str | None:
    """The resolver uses shutil.which; fall back to the known installs."""
    found = shutil.which("op")
    if found:
        return found
    for candidate in (Path.home() / "bin" / "op.exe",
                      Path(os.environ.get("LOCALAPPDATA", "")) /
                      "Microsoft" / "WinGet" / "Links" / "op.exe"):
        if candidate.is_file():
            return str(candidate)
    return None


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def op_env() -> dict:
    env = dict(os.environ)
    try:
        env["OP_SERVICE_ACCOUNT_TOKEN"] = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return env


def vault_reachable() -> bool:
    """ONE read. A successful read means the quota is available."""
    op = find_op()
    if not op:
        log("the op binary is not on PATH - cannot probe the vault")
        return False
    try:
        result = subprocess.run([op, "item", "get", PROBE_ITEM, "--vault", VAULT,
                                 "--format", "json"],
                                capture_output=True, text=True, timeout=60, env=op_env())
    except Exception as exc:
        log(f"the probe failed to run: {exc}")
        return False
    if result.returncode != 0:
        log("the vault is still rate-limited")
        return False
    return True


def platform_answers(timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH, timeout=5) as response:
                if response.status == 200:
                    return True
        except urllib.error.HTTPError:
            return True          # it answered, even if it refused
        except Exception:
            pass
        time.sleep(3)
    return False


def restart_gateway() -> bool:
    log("restarting the gateway so the new mapping takes effect")
    try:
        result = subprocess.run(["hermes", "gateway", "restart"],
                                capture_output=True, text=True, timeout=300)
    except Exception as exc:
        log(f"the restart command failed: {exc}")
        return False
    log(f"  gateway restart rc={result.returncode}")
    for line in (result.stdout or "").strip().splitlines()[-4:]:
        log(f"    {line}")
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=float, default=0.0,
                        help="keep probing for up to this many minutes (0 = one attempt)")
    parser.add_argument("--interval", type=float, default=180.0,
                        help="seconds between probes")
    args = parser.parse_args()

    deadline = time.time() + args.wait * 60
    attempt = 0
    while True:
        attempt += 1
        log(f"attempt {attempt}: probing the vault")
        if vault_reachable():
            log("the vault is reachable")
            restart_gateway()
            if platform_answers():
                log(f"PASS: the api_server platform answers on :8642 ({HEALTH})")
                return 0
            log("the platform did not come up - it will be retried")
        else:
            log("the vault is not available yet; the running gateway is left alone")
        if time.time() >= deadline:
            log("giving up for now - the config fix stands and a later gateway start will pick it up")
            return 1
        time.sleep(max(30.0, args.interval))


if __name__ == "__main__":
    sys.exit(main())
