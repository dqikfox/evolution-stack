"""Bring the api_server platform up, and the cloud key with it, as soon as
the vault allows it.

The platform was enabled and pointed at env:API_SERVER_KEY, but that
variable was not in the 1Password map, so the adapter refused to start and
:8642 was dead - the TESSERACT dashboard showed a red HERMES API card that
nobody could explain. The mapping is now in the config; it takes effect on
the next gateway start.

The same gap existed for OLLAMA_API_KEY: TESSERACT reads it from its own
environment at import, it was in neither the .env nor the vault map, so the
cloud routing was unreachable and the dashboard nagged about it on every
load. It is mapped now, and TESSERACT is restarted after the gateway so it
inherits the resolved environment.

Why this is a script and not a command:

  * A gateway start re-resolves EVERY mapped secret (22 of them), and
    1Password rate-limits the client. Restarting while the vault is
    limited would take working platforms down to fix one broken one.
  * Every `hermes` CLI call ALSO re-resolves the whole map, so even
    checking the state costs the quota.

So: probe the vault with ONE read. Only when that read succeeds, restart
the gateway, restart TESSERACT, then verify both. The probe is cheap, and
the expensive restarts happen only when it is safe.

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
                                capture_output=True, text=True, timeout=60, env=op_env(),
                                encoding="utf-8", errors="replace")
    except Exception as exc:
        log(f"the probe failed to run: {exc}")
        return False
    if result.returncode != 0:
        log("the vault is still rate-limited")
        return False
    # Belt and braces: a CLI variant that exits 0 while printing an error
    # would make this probe lie, and a lie here restarts a healthy gateway
    # for nothing. The 1Password CLI does exit 1 on a rate limit (verified),
    # so this is the second lock on the same door.
    noise = f"{result.stdout or ''}\n{result.stderr or ''}".upper()
    if "TOO MANY REQUESTS" in noise or "RATE-LIMITED" in noise or "[ERROR]" in noise:
        log("the vault answered with an error - treating it as unavailable")
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


def restart_tesseract() -> bool:
    """TESSERACT reads OLLAMA_API_KEY from its own environment at import.

    It is not in the .env and it was not in the vault map, so the cloud
    routing was unreachable and the dashboard nagged about it on every
    load. The mapping is in the config now, but TESSERACT only sees it on
    a fresh start that resolves the map - so it has to be restarted after
    the gateway, not before.
    """
    log("restarting TESSERACT so it inherits the resolved environment")
    scripts = HERMES / "scripts"
    try:
        subprocess.run([sys.executable, str(scripts / "service_control.py"), "stop",
                        "--marker", r"TESSERACT\start.py", "--port", "8705"],
                       capture_output=True, text=True, timeout=180)
        launcher = scripts / "start_tesseract.cmd"
        result = subprocess.run(["cmd.exe", "/c", str(launcher)],
                                capture_output=True, text=True, timeout=300)
        log(f"  tesseract launcher rc={result.returncode}")
    except Exception as exc:
        log(f"the TESSERACT restart failed: {exc}")
        return False
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8705/health", timeout=5) as response:
                if response.status == 200:
                    log("  TESSERACT is back up")
                    return True
        except Exception:
            pass
        time.sleep(3)
    log("  TESSERACT did not come back up")
    return False


def cloud_key_reached_tesseract() -> bool:
    """Did the resolved OLLAMA_API_KEY actually arrive in TESSERACT?"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8705/api/ollama/cloud/status", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:
        log(f"  could not read the cloud status: {exc}")
        return False
    key_set = bool(payload.get("key_set"))
    log(f"  TESSERACT sees the cloud key: {key_set} | hint: {payload.get('hint')}")
    return key_set


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
            else:
                log("the api_server platform did not come up")
            if restart_tesseract():
                cloud_key_reached_tesseract()
            return 0 if platform_answers() else 1
        else:
            log("the vault is not available yet; the running gateway is left alone")
        if time.time() >= deadline:
            log("giving up for now - the config fix stands and a later gateway start will pick it up")
            return 1
        time.sleep(max(30.0, args.interval))


if __name__ == "__main__":
    sys.exit(main())
