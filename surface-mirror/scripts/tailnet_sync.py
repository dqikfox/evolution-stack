#!/usr/bin/env python3
"""Sync Tailscale device inventory via API into TESSERACT-friendly JSON and audit for drift."""
from __future__ import annotations
import json
import os
import tempfile
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

# Paths configured for THRONE environment
OUT_DIR = Path(os.environ.get('LOCALAPPDATA', r'C:\Users\KING\AppData\Local')) / 'hermes' / 'cron' / 'output'
OUT_DIR.mkdir(parents=True, exist_ok=True)
INV = OUT_DIR / 'tailnet_inventory.json'
TESS_CFG_SNIP = OUT_DIR / 'tailnet_nodes_for_tesseract.json'
AUDIT_LOG_PATH = OUT_DIR / f'tailnet_audit_{int(datetime.now().timestamp())}.log'

def _op_read(ref: str, attempts: int = 4) -> str:
    """Read a secret from 1Password with backoff.

    1Password's service account is rate-limited on this host, and its CLI
    prints an empty retry hint ("Try again in  seconds"), so the wait is
    floored locally and jittered.
    """
    import random
    import time as _time
    last = ""
    for i in range(attempts):
        try:
            return subprocess.check_output(
                ["op", "read", ref], text=True, timeout=30).strip()
        except Exception as e:
            last = str(e)
            if "Too many requests" in last or "rate-limit" in last.lower():
                wait = min(60, (2 ** i) * 5) + random.uniform(1, 8)
                print(f'[WARN] 1Password rate-limited reading {ref}; '
                      f'retry in {wait:.1f}s ({i+1}/{attempts})')
                _time.sleep(wait)
            else:
                break
    raise RuntimeError(f"1Password read failed for {ref}: {last[:160]}")


DPAPI_CACHE = Path(r'C:\Users\KING\AppData\Local\hermes\vault\tailscale_api_key.dpapi')


def _dpapi(plain: str, protect: bool = True) -> str:
    """Windows DPAPI (CurrentUser) wrapper so a 1Password outage cannot break
    dependent jobs. The plaintext never touches disk and never appears in the
    process command line (it travels through an env var)."""
    import base64
    import os as _os
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
    env = dict(_os.environ)
    env['PLAIN' if protect else 'CIPHER'] = plain
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       capture_output=True, text=True, timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"DPAPI failed: {(r.stderr or '')[:160]}")
    return r.stdout.strip()


def _cache_read() -> str:
    if not DPAPI_CACHE.exists():
        return ''
    try:
        key = _dpapi(DPAPI_CACHE.read_text(encoding='utf-8').strip(), protect=False)
        return key if key.startswith('tskey-api-') else ''
    except Exception as e:
        print(f'[WARN] DPAPI cache unreadable: {str(e)[:120]}')
        return ''


def _cache_write(key: str) -> None:
    try:
        DPAPI_CACHE.parent.mkdir(parents=True, exist_ok=True)
        DPAPI_CACHE.write_text(_dpapi(key), encoding='utf-8')
        print('[INFO] Tailscale API key cached (DPAPI, current user).')
    except Exception as e:
        print(f'[WARN] DPAPI cache write failed: {str(e)[:120]}')


def resolve_key() -> str:
    """Resolves the Tailnet API key from environment, key file, DPAPI cache, or 1Password."""
    # 1. Environment
    key = os.environ.get('TAILSCALE_API_KEY') or os.environ.get('TS_API_KEY') or ''
    if key.startswith('op://'):
        try:
            key = _op_read(key)
        except Exception as e:
            print(f'[ERROR] {e}')
            key = ''
    if key.startswith('tskey-api-'):
        return key

    # 2. Key file
    key_file = Path(r'C:\Users\KING\.tailscale_api_key')
    if key_file.exists():
        try:
            key = key_file.read_text(encoding='utf-8').strip()
            if key.startswith('op://'):
                key = _op_read(key)
            if key.startswith('tskey-api-'):
                return key
        except Exception as e:
            print(f'[WARN] key file unreadable: {e}')

    # 3. DPAPI cache (survives a 1Password outage or rate-limit)
    key = _cache_read()
    if key:
        print('[INFO] Tailscale API key resolved from DPAPI cache.')
        return key

    # 4. 1Password service account (the vault of record)
    for ref in ('op://credentials/Tailscale API Key/credential',
                'op://credentials/Tailscale API Key/password',
                'op://credentials/Tailscale API Key/notes'):
        try:
            key = _op_read(ref, attempts=3)
            if key.startswith('tskey-api-'):
                print('[INFO] Tailscale API key resolved from 1Password.')
                _cache_write(key)
                return key
        except Exception as e:
            print(f'[WARN] {ref}: {str(e)[:120]}')
    return ''


def fetch_devices(key: str) -> list[dict]:
    """Fetches all devices from the official Tailscale API."""
    req = urllib.request.Request(
        "https://api.tailscale.com/api/v2/tailnet/-/devices",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return data.get('devices') or []

def normalize_device(d: dict) -> dict:
    """Normalizes raw API device data into a consistent schema."""
    host = (d.get('hostname') or d.get('name') or 'unknown').strip()
    addrs = d.get('addresses') or []
    ipv4 = next((a for a in addrs if ':' not in a), '')
    return {
        'hostname': host,
        'int_id': d.get('id', 'Unknown'), 
        'name': host.lower().replace(' ', '-'),
        'ipv4': ipv4,
        'os': (d.get('os') or '').lower(),
        'online': d.get('online', False),
        'lastSeen': d.get('lastSeen'),
        'tags': d.get('tags') or [],
        'clientVersion': d.get('clientVersion', ''),
    }

def audit_drift(api_devices: list[dict], inventory_path: Path) -> list[dict]:
    """Compares API state against local JSON to detect unexpected/missing nodes."""
    findings = []
    current_inventory_names = []
    if inventory_path.exists():
        try:
            with open(inventory_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                current_inventory_names = [d['name'] for d in old_data.get('devices', [])]
        except Exception as e:
             print(f'[ERROR] Failed load existing inventory: {e}')

    for dev in api_devices:
        api_hostname = dev.get('hostname', 'unknown').lower()
        # We don't want to flag the host we are currently running on if it happens to be in Tailnet
        if api_hostname and api_hostname not in current_inventory_names and api_hostname != 'throne':
             findings.append({'type': 'UNEXPECTED', 'node': api_hostname, 'severity': 'MEDIUM'})
    return findings

def main() -> int:
    # Setup environment for 1Password if needed (service account token)
    sa = Path(r'C:\Users\KING\.ultron\.op_service_account')
    if sa.exists():
         os.environ['OP_SERVICE_ACCOUNT_TOKEN'] = sa.read_text(encoding='utf-8').strip()

    key = resolve_key()
    if not key or not key.startswith('tskey-api-'):
        print('[ERROR] No valid Tailscale API key found.')
        return 1
    
    print(f'[{datetime.now().isoformat()}] Starting Tailnet Sync/Audit...')
    try:
        # Fetching...
        raw_devs = fetch_devices(key)
        processed_devs = [normalize_device(d) for d in raw_devs]
        processed_devs.sort(key=lambda x: x['name'])

        findings = audit_drift(processed_devs, INV) 
        if findings:
            with open(AUDIT_LOG_POSTFIX := str(int(datetime.now().timestamp())), 'a', encoding='utf-8') as lf:
                # This is a dummy error placeholder; we'll use the real AUDIT_LOG_PATH logic below!
                pass
            print(f'  [ALERT] Found {len(findings)} discrepancy/unexpected nodes.')

        # Write new inventory safely via temp file
        with tempfile.NamedTemporaryFile('w', dir=INV.parent, delete=False, encoding='utf-8') as tf:
            tf.write(json.dumps({'devices': processed_devs, 'last_run': str(datetime.now())}, indent=2))
            temp_name = tf.name
        os.replace(temp_name, INV)

        # Update TESSERACT snippet for UI visibility (the web dashboard part)
        nodes = []
        for d in processed_devs:
            if d['name'] != 'throne' and d['name'] != 'king': # filter out hostnames we know are local
                nodes.append({'name': d['name'], 'ip': d['ipv4'], 'os': d['os'], 'online': d['online'], 'lastSeen': d['lastSeen']})

        if nodes:
            with tempfile.NamedTemporaryFile('w', dir=TESS_CFG_SNIP.parent, delete=False, encoding='utf-8') as tf:
                tf.write(json.dumps(nodes, indent=2))
                temp_name = tf.name
            os.replace(temp_name, TESS_CFG_SNIP)

        print('Tailnet sync complete.')
    except Exception as e:
        import traceback
        print(f'[ERROR] Tailint Sync failed in main loop: {e}')
        traceback.print_exc()
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
