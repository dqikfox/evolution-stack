"""
nexus_core_sync.py - mirror new lessons from the MSI satellite into the
local Obsidian bridge log.

Why this is a script and not a prompt:
  This job runs every hour. When the work was done by a model reading the
  prompt, the model occasionally entered a repetition loop and the whole run
  was recorded as a failure - twice, while the underlying condition was
  "MSI is offline", which is not a defect at all. A deterministic script
  cannot loop, cannot forget the preflight, and produces the same answer
  every time.

Exit codes:
    0  sync ran (entries may or may not have been appended)
    3  deferred: the MSI satellite is offline (an expected external condition)
    1  a real failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

Tailscale = Path(r"C:\Program Files\Tailscale\tailscale.exe")
MSI_TAILSCALE_IP = "100.83.120.56"
MSI_PORTS = (445, 22)
SHARE = Path(r"\\Msi\e\ultron-memory\Lessons")
BRIDGE_LOG = Path(r"C:\Users\KING\Documents\2nd brain\AI\Knowledge\Capability Registry"
                   r"\ultron-bridge_log.md")
STATE = Path(r"C:\Users\KING\AppData\Local\hermes\state\nexus_core_sync.json")


# ----------------------------------------------------------------- preflight --
def tailscale_peer(name: str = "msi") -> dict:
    """Return {online, lastSeen, ip} for a Tailscale peer. Never raises."""
    if not Tailscale.exists():
        return {"online": None, "lastSeen": None, "ip": None, "error": "tailscale.exe not found"}
    try:
        r = subprocess.run([str(Tailscale), "status", "--json"],
                           capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout or "{}")
    except Exception as e:                                  # noqa: BLE001
        return {"online": None, "lastSeen": None, "ip": None, "error": str(e)[:120]}
    for peer in data.get("Peer", {}).values():
        host = (peer.get("HostName") or "").lower()
        dns = (peer.get("DNSName") or "").lower()
        if name.lower() in host or name.lower() in dns:
            ips = peer.get("TailscaleIPs") or []
            return {
                "online": bool(peer.get("Online")),
                "lastSeen": peer.get("LastSeen"),
                "ip": ips[0] if ips else None,
                "host": peer.get("HostName"),
            }
    return {"online": False, "lastSeen": None, "ip": None, "error": "peer not found"}


def tcp_probe(host: str, ports=MSI_PORTS, timeout: float = 2.0) -> dict:
    out = {}
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            out[port] = True
        except OSError:
            out[port] = False
        finally:
            s.close()
    return out


def relative_age(last_seen: str | None) -> str:
    if not last_seen:
        return "unknown"
    try:
        ts = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return str(last_seen)[:19]
    delta = time.time() - ts.timestamp()
    if delta < 0:
        return "just now"
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{int(delta // secs)}{unit} ago"
    return f"{int(delta)}s ago"


# -------------------------------------------------------------------- parsing --
def front_matter(text: str) -> dict:
    """Minimal YAML front-matter reader: scalars, inline lists, block lists."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    fm: dict = {}
    key = None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and key:          # block list item
            item = line.strip().lstrip("-").strip().strip("'\"")
            if item:
                fm.setdefault(key, [])
                if isinstance(fm[key], list):
                    fm[key].append(item)
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            key = k.strip()
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                fm[key] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            elif v in ("", "[]"):
                fm[key] = []
            else:
                fm[key] = v.strip("'\"")
    return fm


def summarise(path: Path) -> tuple[str, str, str]:
    """Return (title, impact, tags) for a lesson file."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return (path.stem, "", "")
    fm = front_matter(text)
    title = str(fm.get("title") or path.stem)
    impact = str(fm.get("impact") or "")
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
    return (title, impact, ", ".join(str(t) for t in tags))


# ---------------------------------------------------------------------- state --
def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# ----------------------------------------------------------------------- sync --
def append_entry(entry: str) -> None:
    BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    if BRIDGE_LOG.exists():
        text = BRIDGE_LOG.read_text(encoding="utf-8", errors="ignore")
        if "## Entries" not in text:
            text = text.rstrip() + "\n\n## Entries\n"
        head, _, tail = text.partition("## Entries")
        text = head + "## Entries\n" + tail.rstrip() + "\n\n" + entry.rstrip() + "\n"
    else:
        text = ("title: Ultron Bridge Log\nstatus: active\n"
                "description: Auto-synced log of remote lessons discovered on the MSI node.\n"
                "---\n# Ultron Bridge Log\n\n## Entries\n\n" + entry.rstrip() + "\n")
    BRIDGE_LOG.write_text(text, encoding="utf-8")
    # keep the updated stamp honest
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    updated = re.sub(r"^updated:.*$", f"updated: '{stamp}'", text, count=1, flags=re.M)
    BRIDGE_LOG.write_text(updated, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="print a one-line summary only")
    args = ap.parse_args()

    peer = tailscale_peer("msi")
    probes = tcp_probe(MSI_TAILSCALE_IP)
    reachable = peer.get("online") or any(probes.values())
    age = relative_age(peer.get("lastSeen"))

    if not reachable:
        msg = (f"Nexus_Core_Sync deferred: MSI offline (last seen {age}). "
               f"No new lessons imported.")
        # record the deferral so the state is observable even though the
        # run itself is silent - an hourly "MSI is offline" message is
        # noise, but a job that quietly stops checking is worse.
        state = load_state()
        state["_last_run"] = {
            "result": "deferred",
            "reason": "msi offline",
            "last_seen": peer.get("lastSeen"),
            "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        }
        save_state(state)
        print(msg)
        return 3

    try:
        files = sorted(p for p in SHARE.glob("*.md") if p.is_file())
    except OSError as e:
        print(f"Nexus_Core_Sync failed: cannot read {SHARE}: {e}", file=sys.stderr)
        return 1

    state = load_state()
    imported, skipped = [], []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        sig = f"{st.st_mtime:.0f}:{st.st_size}"
        if state.get(f.name, {}).get("sig") == sig:
            skipped.append(f.name)
            continue
        title, impact, tags = summarise(f)
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        entry = (f"### {stamp} - {title}\n"
                 f"- source: `//Msi/e/ultron-memory/Lessons/{f.name}`\n"
                 f"- impact: {impact or '(not stated)'}\n"
                 f"- tags: {tags or '(none)'}\n")
        append_entry(entry)
        state[f.name] = {"sig": sig, "imported_at": stamp}
        imported.append(f.name)
    state["_last_run"] = {
        "result": "imported" if imported else "no-change",
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "imported": imported,
    }
    save_state(state)

    if imported:
        print(f"Nexus_Core_Sync: imported {len(imported)} new lesson(s) into the bridge log: "
              + ", ".join(imported))
    else:
        print(f"Nexus_Core_Sync: MSI reachable, {len(files)} lesson file(s) checked, "
              f"nothing new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
