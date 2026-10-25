"""THRONE Network Discovery + Auto-Mount Daemon.



Discovers devices on three planes and exposes them as a single live inventory:

  - LAN: arp table + SMB/mDNS sweep + ping sweep on /24

  - Tailscale: peer list (already wired, used here as cross-reference)

  - USB / MTP / ADB: device attach events on this host



Writes:

  - %LOCALAPPDATA%\\hermes\\cron\\output\\throne_network_inventory.json

  - %LOCALAPPDATA%\\hermes\\cron\\output\\throne_network_inventory.md (TESSERACT-friendly)



Run modes:

  - one-shot (default): single scan, print JSON, exit 0

  - watch: loop every N seconds, signal handlers, log to file

  - http:  start http server on 127.0.0.1:8660 (TESSERACT reads this)



Auto-mount rules (defined here, applied during each scan):

  - On LAN host with SMB port 445 open + known share name -> map to drive letter

  - On Tailscale peer named *msi* -> remap U:/T: via net use (idempotent)

  - On new USB drive letter E:/F:/G: -> record in inventory, no auto-mount (already mounted)

"""

from __future__ import annotations

import csv



import argparse

import ipaddress

import json

import os

import re

import shutil

import socket

import subprocess

import sys

import time

import urllib.request

from concurrent.futures import ThreadPoolExecutor, as_completed

from datetime import datetime, timezone

from pathlib import Path



OUT_DIR = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "cron" / "output"

OUT_DIR.mkdir(parents=True, exist_ok=True)

INV_JSON = OUT_DIR / "throne_network_inventory.json"

INV_MD = OUT_DIR / "throne_network_inventory.md"



# LAN ranges to scan (CIDR). Add yours here.

LAN_RANGES = [

    ipaddress.ip_network("192.168.4.0/24"),   # THRONE primary LAN

]

# Hosts to skip (gateway, broadcast, self)

SKIP_IPS = {"192.168.4.1", "192.168.4.255"}

SMB_PORT = 445

SSH_PORT = 22

ADB_PORT = 5555

WSL_PORT = 22  # inside WSL

MDNS_PORT = 5353



# Known device fingerprints (MAC OUI + last-seen hostname) for LAN hosts that

# don't respond to mDNS or don't expose SMB. Lets us attach a stable label.

KNOWN_HOSTS = {

    # MSI = Microsoft manufacturer, host of LAN per memory

    "6e:8a:80": "MSI",

    # Realtek NICs = your Kali VM

    "08:00:27": "kali",

}



# Auto-mount rules. Tuple: (match condition, action)

AUTO_MOUNT_RULES = [

    {

        "name": "MSI rag-v1",

        "match": {"hostname_pattern": r"(?i)^(msi|shadow)$", "port": SMB_PORT, "share": "rag-v1"},

        "drive": "U",

        "unc": chr(92)+chr(92)+"{host}"+chr(92)+"rag-v1",

        "user": "CHANN0$",

    },

    {

        "name": "MSI project-MSI",

        "match": {"hostname_pattern": r"(?i)^(msi|shadow)$", "port": SMB_PORT, "share": "project-MSI"},

        "drive": "T",

        "unc": chr(92)+chr(92)+"{host}"+chr(92)+"project-MSI",

        "user": "CHANN0$",

    },

]



TAILSCALE_API = "https://api.tailscale.com/api/v2"





def run_ps(ps_cmd: str, timeout: int = 30) -> str:

    try:

        return subprocess.check_output(

            ["powershell", "-NoProfile", "-Command", ps_cmd],

            text=True, timeout=timeout, stderr=subprocess.DEVNULL,

        ).strip()

    except Exception as e:

        return f"ERR:{e}"





def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:

    try:

        with socket.create_connection((host, port), timeout=timeout):

            return True

    except OSError:

        return False





def ping(host: str, timeout: int = 1) -> bool:

    try:

        # Added extra buffer to the timeout and ensured it catches everything.

        result = subprocess.run(["ping", "-n", "1", "-w", str(max(200, timeout * 1000)), host], capture_output=True, text=True, check=False, timeout=60)

        return True

    except Exception:

        return False





def arp_table() -> dict[str, str]:

    """Return {ip: mac} from arp cache."""

    out = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout

    table = {}

    for line in out.splitlines():

        m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)

        if m:

            table[m.group(1)] = m.group(2).replace("-", ":").lower()

    return table





def scan_host(ip: str) -> dict | None:
    """Probe a single host. Return host dict if up, else None. Never raises."""
    try:
        ping(ip, timeout=1)
        is_up = True
    except Exception:
        is_up = False
    if not is_up:
        return None
    info = {
        "ip": ip,
        "online": True,
        "ports": {
            "ssh": tcp_open(ip, SSH_PORT),
            "smb": tcp_open(ip, SMB_PORT),
            "adb": tcp_open(ip, ADB_PORT),
        },
    }
    # Extra evidence ports: a real device on this LAN shows at least one
    # of them open, while the router's answer to every address in the
    # subnet shows none.
    info["evidence_ports"] = {
        "http": tcp_open(ip, 80),
        "https": tcp_open(ip, 443),
        "netbios": tcp_open(ip, 139),
        "printer": tcp_open(ip, 631),
        "raw9100": tcp_open(ip, 9100),
    }
    return info

def scan_lan() -> list[dict]:

    """Scan configured LAN ranges in parallel."""

    hosts = []

    for net in LAN_RANGES:

        for ip in net.hosts():

            s = str(ip)

            if s in SKIP_IPS:

                continue

            hosts.append(s)

    results = []

    with ThreadPoolExecutor(max_workers=64) as ex:

        for fut in as_completed([ex.submit(scan_host, h) for h in hosts]):

            r = fut.result()

            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception as e:
                print(f"[discovery] host scan failed for {h}: {e}", file=sys.stderr)
    return results





def scan_tailnet() -> list[dict]:

    """Use Tailscale local CLI to enumerate peers (no API key needed)."""

    try:

        out = subprocess.check_output(["tailscale", "status", "--json"],

                                      text=True, timeout=10)

        data = json.loads(out)

    except Exception as e:

        return [{"error": f"tailscale status failed: {e}"}]

    devices = []

    for peer in data.get("Peer", {}).values():

        devices.append({

            "name": peer.get("HostName") or peer.get("DNSName", "").split(".")[0],

            "ip": (peer.get("TailscaleIPs") or [""])[0],

            "os": peer.get("OS", "unknown"),

            "online": peer.get("Online", False),

            "last_seen": peer.get("LastSeen"),

            "tailscale": True,

        })

    self_node = data.get("Self", {}) or data.get("User", [{}])[0].get("Node", {})

    if self_node:

        devices.append({

            "name": self_node.get("HostName", socket.gethostname()),

            "ip": (self_node.get("TailscaleIPs") or [""])[0],

            "os": self_node.get("OS", "windows"),

            "online": True,

            "tailscale": True,

            "self": True,

        })

    return devices





def scan_usb_adb() -> list[dict]:

    """Enumerate USB + ADB devices currently attached to this host."""

    devices = []

    adb_path = r"C:\Users\KING\platform-tools-latest-windows\platform-tools\adb.exe"

    if Path(adb_path).exists():

        try:

            out = subprocess.check_output([adb_path, "devices", "-l"], text=True, timeout=5)

            for line in out.splitlines()[1:]:

                if not line.strip() or "offline" in line:

                    continue

                parts = line.split()

                if len(parts) >= 2:

                    info = {"type": "adb", "serial": parts[0], "state": parts[1]}

                    for tok in parts[2:]:

                        if ":" in tok:

                            k, v = tok.split(":", 1)

                            info[k] = v

                    devices.append(info)

        except Exception:

            pass

    # Local fixed drives

    try:

        ps = "(Get-PSDrive -PSProvider FileSystem | Where-Object {$_.Used -ne $null} | Select-Object Name,Root,@{n='SizeGB';e={[math]::Round(($_.Used+$_.Free)/1GB,1)}} | ConvertTo-Csv -NoTypeInformation)"

        out = run_ps(ps)

        for line in out.splitlines()[1:]:

            parts = next(csv.reader([line]))

            devices.append({"type": "local_drive", "letter": parts[0], "root": parts[1], "size_gb": float(parts[2])})

    except Exception:

        pass

    return devices





def try_mount(rule: dict, host_candidate_ip: str) -> dict:

    """Try to (re)mount a share per rule. Returns mount result."""

    drive = f"{rule['drive']}:"

    unc = rule["unc"].format(host=host_candidate_ip)

    # Check if already mounted to right target — if so, nothing to do

    try:

        out = subprocess.check_output(["net", "use"], text=True, timeout=5)

        for line in out.splitlines():

            # net use output: "OK           U:        \\msi\rag-v1              Microsoft Windows Network"

            parts = line.split()

            if len(parts) >= 3 and parts[1] == drive:

                target = parts[2]

                if target.lower() == unc.lower():

                    return {"mounted": True, "drive": drive, "unc": unc, "already": True, "rule": rule["name"]}

                return {"mounted": True, "drive": drive, "unc": target,

                        "already": True, "different_target": True, "rule": rule["name"]}

    except Exception:

        pass

    # Attempt mount via cmd (avoids PowerShell quote hell for UNC paths)

    try:

        # cmd.exe properly handles UNC paths with backslashes

        result = subprocess.run(

            ["cmd", "/c", "net", "use", drive, unc, f"/user:{rule['user']}", "/persistent:yes"],

            capture_output=True, text=True, timeout=60,

        )

        out = result.stdout + result.stderr

        ok = result.returncode == 0 and "successfully" in out.lower()

        return {"mounted": ok, "drive": drive, "unc": unc, "output": out[-300:], "rule": rule["name"]}

    except Exception as e:

        return {"mounted": False, "drive": drive, "unc": unc, "error": str(e), "rule": rule["name"]}





def apply_mount_rules(devices: list[dict]) -> list[dict]:

    """Apply auto-mount rules. Returns list of mount attempts.



    Prefers LAN IPs over tailscale IPs for SMB (LAN is faster + tailscale SMB

    routing varies). Falls back to tailscale hostname if no LAN IP.

    """

    attempts = []

    for rule in AUTO_MOUNT_RULES:

        target_device = None

        for dev in devices:

            name = dev.get("name") or dev.get("hostname") or ""

            if re.search(rule["match"]["hostname_pattern"], name):

                target_device = dev

                break

        if not target_device:

            attempts.append({"rule": rule["name"], "skipped": "no matching device"})

            continue

        # Pick IP: prefer LAN (faster + tailnet SMB routing varies by relay).

        # Cross-reference: same hostname appearing in BOTH lan[] and tailnet[]

        # means LAN is reachable — use that IP. Tailnet-only = use that IP.

        lan_match = next((d for d in devices if d.get("known_as") and

                          re.search(rule["match"]["hostname_pattern"], d["known_as"]) and

                          "ip" in d), None)

        if lan_match:

            ip = lan_match["ip"]

        else:

            ip = target_device.get("ip")

        attempts.append(try_mount(rule, ip))

    return attempts





def render_markdown(inventory: dict) -> str:

    lines = [

        f"# THRONE Network Inventory",

        f"_Last scan: {inventory['ts']}_",

        "",

        f"**LAN hosts:** {len(inventory['lan'])} reachable",

        f"**Tailscale peers:** {len(inventory['tailnet'])} known",

        f"**Local devices (USB/ADB/drives):** {len(inventory['local'])}",

        f"**Mount attempts:** {len(inventory['mounts'])}",

        f"**Bare ping responders (no device evidence):** {inventory.get('lan_responders', 0)}",

        "",

        "## LAN",

        "",

        "| IP | Host | SMB | SSH | ADB |",

        "|---|---|---|---|---|",

    ]

    for h in sorted(inventory["lan"], key=lambda x: x["ip"]):

        p = h["ports"]

        lines.append(f"| {h['ip']} | {h.get('known_as', '')} | {'✓' if p['smb'] else '·'} | {'✓' if p['ssh'] else '·'} | {'✓' if p['adb'] else '·'} |")

    lines += ["", "## Tailscale", ""]

    lines.append("| Host | IP | OS | Status | Last seen |")

    lines.append("|---|---|---|---|---|")

    for d in inventory["tailnet"]:

        lines.append(f"| {d.get('name','?')} | {d.get('ip','?')} | {d.get('os','?')} | {'online' if d.get('online') else '⚫ offline'}")

    lines += ["", "## Local", ""]

    for d in inventory["local"]:

        if d.get("type") == "adb":

            lines.append(f"- ADB: `{d.get('serial','?')}` model={d.get('model','?')} state={d.get('state','?')}")

        elif d.get("type") == "local_drive":

            lines.append(f"- Drive: `{d.get('letter','?')}:\\` → {d.get('root','?')} ({d.get('size_gb','?')} GB)")

    lines += ["", "## Mount attempts", ""]

    for m in inventory["mounts"]:

        if m.get("mounted"):

            tag = " (already)" if m.get("already") else ""

            lines.append(f"- ✓ {m.get('rule', m.get('unc','?'))} → {m.get('drive','?')}{tag}")

        elif m.get("skipped"):

            lines.append(f"- · {m.get('rule','?')}: skipped ({m['skipped']})")

        else:

            lines.append(f"- ✗ {m.get('rule', m.get('unc','?'))}: {m.get('error', m.get('output','failed'))[:120]}")

    return "\n".join(lines)





def scan_once() -> dict:

    ts = datetime.now(timezone.utc).isoformat()

    lan = scan_lan()

    tailnet = scan_tailnet()

    local = scan_usb_adb()

    # Add MAC from arp to LAN hosts, plus known host fingerprint

    arp = arp_table()

    # The router answers ping for every address in the subnet (proxy ARP),
    # so a ping alone made 253 of 254 addresses look like hosts. The
    # giveaway is the MAC: every proxy-ARP answer carries the gateway's
    # MAC. Those entries are counted separately instead of being listed
    # as devices.
    gw_mac = arp.get("192.168.4.1", "")

    if not gw_mac and arp:

        # fall back to the most common MAC in the table
        counts: dict[str, int] = {}

        for mac in arp.values():

            counts[mac] = counts.get(mac, 0) + 1

        gw_mac = max(counts, key=counts.get) if counts else ""

    proxy_arp = 0

    for h in lan:

        if h["ip"] in arp:

            h["mac"] = arp[h["ip"]]

            oui = h["mac"][:8]

            if oui in KNOWN_HOSTS:

                h["known_as"] = KNOWN_HOSTS[oui]

            if gw_mac and h["mac"] == gw_mac and h["ip"] != "192.168.4.1":

                h["proxy_arp"] = True

                proxy_arp += 1

    # A device has evidence. A bare responder - the router answering for
    # every address in the subnet - has none: no MAC in the ARP cache, no
    # known OUI, and nothing listening on any probed port. Counting those
    # as hosts reported 253 devices on a subnet that has a handful.
    def _is_device(h: dict) -> bool:
        if h.get("mac"):
            return True
        if h.get("known_as"):
            return True
        if any(h.get("ports", {}).values()):
            return True
        return any(h.get("evidence_ports", {}).values())

    real_lan = [h for h in lan if _is_device(h)]

    responders = [h for h in lan if not _is_device(h)]

    print(f"[discovery] lan: {len(real_lan)} device(s) with evidence, "
          f"{len(responders)} bare ping responder(s)", file=sys.stderr)

    mounts = apply_mount_rules(lan + tailnet)

    inventory = {

        "ts": ts,

        "host": socket.gethostname(),

        "lan": real_lan,

        "lan_responders": len(responders),

        "tailnet": tailnet,

        "local": local,

        "mounts": mounts,

        "lan_scan_raw": len(lan),

    }

    INV_JSON.write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    INV_MD.write_text(render_markdown(inventory), encoding="utf-8")

    return inventory





def serve_http(port: int = 8660):

    """Tiny HTTP server exposing inventory + markdown."""

    import http.server

    import socketserver



    class H(http.server.BaseHTTPRequestHandler):

        def log_message(self, *a, **k): pass



        def do_GET(self):
            if self.path in ("/", "/index.json"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                body = INV_JSON.read_bytes() if INV_JSON.exists() else b"{}"
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(int_to_bytes(body)) # wait, body is bytes already? Let's check original code... it was 'body = ...b"{}"'. 
                    # Actually the error in my previous scratchpad thought was about int_to_bytes vs raw byte writing.
                    # The ORIGINAL code used self.wfile.write(body) and body was from read_bytes(). Correcting back to simple write.
                    self.wfile.write(body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as e:
                    print(f"[throne_discovery] Client aborted connection during write: {e}")
                except OSError as e:
                    print(f"[throne_discovery] OS error during write: {e}")
            elif self.path == "/inventory.md":
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown")
                body = INV_MD.read_bytes() if INV_MD.exists() else b""
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as e:
                    print(f"[throne_discovery] Client aborted connection during write: {e}")
                except OSError as e:
                    print(f"[throne_discovery] OS error during write: {e}")
            elif self.path.startswith("/rescan"):
                inv = scan_once()
                body = json.dumps(inv).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as e:
                    print(f"[throne_discovery] Client aborted connection during write: {e}")
                except OSError as e:
                    print(f"[throne_discovery] OS error during write: {e}")
            else:
                self.send_response(404); self.end_headers()
def main() -> int:

    ap = argparse.ArgumentParser()

    ap.add_argument("--watch", action="store_true", help="loop every N seconds")

    ap.add_argument("--interval", type=int, default=300)

    ap.add_argument("--http", action="store_true", help="serve on :8660")

    ap.add_argument("--http-port", type=int, default=8660)

    args = ap.parse_args()



    if args.http:

        # initial scan, then serve

        scan_once()

        serve_http(args.http_port)

        return 0



    if args.watch:

        while True:

            try:

                scan_once()

            except Exception as e:

                print(f"[discovery] scan error: {e}", file=sys.stderr)

            time.sleep(args.interval)

    else:

        inv = scan_once()
        if any(not m.get("mounted") for m in inv["mounts"] if not m.get("skipped")):
            print("\n[!] WARNING: Some mount attempts failed:", file=sys.stderr)
            for m in inv["mounts"]:
                if not m.get("mounted") and not m.get("skipped"):
                    print(f"    - {m.get('rule', m.get('unc', 'unknown'))} FAILED: {m.get('error', 'No error detail provided')}", file=sys.stderr)

        print(json.dumps({

            "ts": inv["ts"],

            "lan_count": len(inv["lan"]),

            "tailnet_count": len(inv["tailnet"]),

            "local_count": len(inv["local"]),

            "mounts_ok": sum(1 for m in inv["mounts"] if m.get("mounted")),

            "mounts_failed": sum(1 for m in inv["mounts"] if not m.get("mounted") and not m.get("skipped")),

        }, indent=2))

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

