"""
secret_resolver.py - fetch a secret from 1Password, with a DPAPI fallback.

Rules this module exists to enforce:
  * A secret is never written to disk in plaintext.
  * A secret is never passed on a command line (it would be visible to every
    process on the box while it runs).
  * A 1Password outage degrades a dependent job, it does not kill it: the
    value is cached with Windows DPAPI (CurrentUser scope) so it can be
    recovered without the vault.

Resolution order: 1Password -> DPAPI cache -> (refresh cache if the vault
answered) -> fail loudly.
"""
from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

OP_EXE = r"C:\Users\KING\AppData\Local\Microsoft\WinGet\Links\op.EXE"
OP_SERVICE_ACCOUNT = Path(r"C:\Users\KING\.ultron\.op_service_account")
VAULT = "credentials"
VAULT_DIR = Path(r"C:\Users\KING\AppData\Local\hermes\vault")


def _dpapi(plain: str, protect: bool = True) -> str:
    """Windows DPAPI (CurrentUser). The plaintext travels in an env var."""
    script = (
        "try{Add-Type -AssemblyName System.Security}catch{};"
        "try{Add-Type -AssemblyName System.Security.Cryptography.ProtectedData}catch{};"
        "$b=[System.Text.Encoding]::UTF8.GetBytes($env:PLAIN);"
        "$p=[System.Security.Cryptography.ProtectedData]::Protect($b,$null,"
        "[System.Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[Convert]::ToBase64String($p)"
        if protect else
        "try{Add-Type -AssemblyName System.Security}catch{};"
        "try{Add-Type -AssemblyName System.Security.Cryptography.ProtectedData}catch{};"
        "$b=[Convert]::FromBase64String($env:CIPHER);"
        "$p=[System.Security.Cryptography.ProtectedData]::Unprotect($b,$null,"
        "[System.Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[System.Text.Encoding]::UTF8.GetString($p)"
    )
    env = dict(os.environ)
    env['PLAIN' if protect else 'CIPHER'] = plain
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       capture_output=True, text=True, timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"DPAPI failed: {(r.stderr or '')[:160]}")
    return r.stdout.strip()


def _op_env() -> dict:
    env = dict(os.environ)
    if OP_SERVICE_ACCOUNT.exists():
        token = OP_SERVICE_ACCOUNT.read_text(encoding="utf-8").strip()
        if token:
            env["OP_SERVICE_ACCOUNT_TOKEN"] = token
    return env


def op_read(ref: str, timeout: int = 45) -> str | None:
    """Read one secret from 1Password. Returns None if the vault is unusable."""
    if not Path(OP_EXE).exists():
        return None
    try:
        # NB: the op:// reference already names the vault; adding --vault here
        # makes the service account reject the call.
        r = subprocess.run([OP_EXE, "read", ref, "--no-newline"],
                           env=_op_env(), capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    val = (r.stdout or "").strip()
    return val or None


def op_write_secret(item_title: str, field_id: str, value: str, timeout: int = 120) -> bool:
    """Replace a concealed field on a 1Password note. The value is piped in,
    never placed on a command line."""
    env = _op_env()
    try:
        r = subprocess.run([OP_EXE, "item", "get", item_title, "--vault", VAULT,
                            "--format", "json", "--reveal"],
                           env=env, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return False
        import json
        item = json.loads(r.stdout)
        touched = False
        for f in item.get("fields", []):
            if f.get("id") == field_id:
                f["value"] = value
                touched = True
        if not touched:
            return False
        payload = json.dumps(item)
        p = subprocess.run([OP_EXE, "item", "edit", item_title, "--vault", VAULT],
                           input=payload, env=env, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def cache_path(name: str) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    return VAULT_DIR / f"{name}.dpapi"


def resolve(name: str, op_ref: str, refresh: bool = True) -> str:
    """Resolve a secret: 1Password first, DPAPI cache as the fallback.

    Raises RuntimeError when neither source can produce a value - a service
    that needs a secret must fail loudly rather than start with a wrong one.
    """
    cp = cache_path(name)
    if refresh:
        val = op_read(op_ref)
        if val:
            try:
                cp.write_text(_dpapi(val, protect=True), encoding="utf-8")
            except Exception:
                pass
            return val
    if cp.exists():
        try:
            return _dpapi(cp.read_text(encoding="utf-8").strip(), protect=False)
        except Exception:
            pass
    raise RuntimeError(
        f"secret '{name}' unavailable: 1Password did not answer and no DPAPI cache exists at {cp}")
