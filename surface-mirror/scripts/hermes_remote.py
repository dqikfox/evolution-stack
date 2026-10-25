"""Operate and orchestrate a REMOTE Hermes agent from THRONE.

SHADOW (SHADOW-EOKGST4R) runs a full Hermes install: a gateway with its
own platform set (simplex connected, telegram revoked), an Electron
desktop app, and Ollama. It is a peer, not a child, so everything the
house does locally has to work across a transport.

The channels that actually exist, proven on the wire:

  ssh        shadow@<ip> with a key, batch mode, no prompts
  http       the remote's platform port is bound to 0.0.0.0, so the
             tailnet can reach it directly
  tunnel     `ssh -L` turns the remote's localhost-only surfaces into
             local ones - the way to drive a web UI that only binds
             to 127.0.0.1
  desktop    the Electron app needs an INTERACTIVE session; a process
             started from an SSH session lands in session 0 with no
             visible desktop, so it is started through a scheduled task
             with an interactive token instead

The rule this file follows everywhere: report what is true, never
assume. A remote that cannot be reached says so; a platform that is
fatal says fatal; a desktop app that is not running is reported as not
running rather than started behind the operator's back.

Usage:
    hermes_remote.py status    --host shadow
    hermes_remote.py platforms --host shadow
    hermes_remote.py exec      --host shadow -- "hostname"
    hermes_remote.py tunnel    --host shadow --remote-port 8644
    hermes_remote.py desktop   --host shadow [--start]
    hermes_remote.py watch     --host shadow --until-online
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERMES = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes"
SCRIPTS = HERMES / "scripts"
LOGS = HERMES / "logs"
INFRA = Path(os.environ.get("ULTRON_INFRA", "E:/ultron-memory/infra"))
REGISTRY = INFRA / "REMOTE_AGENTS.json"
TAILSCALE = Path(r"C:/Program Files/Tailscale/tailscale.exe")


# ----------------------------------------------------------------- registry

def load_registry() -> dict:
    if not REGISTRY.is_file():
        return {}
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_host(name: str) -> dict:
    """Look a host up. A name that is not registered is not guessed at."""
    reg = load_registry()
    entry = reg.get(name)
    if entry is None:
        for key, value in reg.items():
            if value.get("tailnet_name", "").lower() == name.lower():
                entry = value
                break
    if entry is None:
        raise SystemExit(f"unknown host: {name} (known: {', '.join(sorted(reg)) or 'none'})")
    return entry


# --------------------------------------------------------------------- ssh

def ssh_command(host: dict, remote_ps: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run a PowerShell script on the remote and return (rc, stdout, stderr).

    The script is sent as -EncodedCommand (base64, UTF-16LE). That is
    not decoration: a PowerShell script with quotes, dollars and
    semicolons passed through ssh's own quoting layer gets mangled in
    ways that look like a remote bug and are not one.
    """
    encoded = base64.b64encode(remote_ps.encode("utf-16-le")).decode()
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new",
           "-i", str(host["key"]), f"{host['user']}@{host['ip']}",
           "powershell", "-NoProfile", "-EncodedCommand", encoded]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, "", f"the remote command exceeded {timeout}s"
    except FileNotFoundError:
        return 127, "", "ssh is not installed on this host"
    stdout = _clean(proc.stdout)
    stderr = _clean(proc.stderr)
    return proc.returncode, stdout, stderr


# A script that travels on the command line hits the Windows limit: base64
# of UTF-16LE is 2.67x the script, and the command line caps at ~8191
# characters. So the script goes over the STDIN CHANNEL and a small decoder
# on the command line puts it on disk and runs it.
_DECODER = r"""
$ErrorActionPreference = 'Stop'
$text = [Console]::In.ReadToEnd()
$path = Join-Path $env:TEMP 'hermes_remote_task.ps1'
[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false))
& $path
if (-not $?) { exit 1 }
"""


def ssh_script(host: dict, script: str, timeout: int = 180) -> tuple[int, str, str]:
    """Run a PowerShell script on the remote, whatever its length.

    The script is piped to the far side and written to a file there, so
    the size of the script is bounded by the SSH channel and not by the
    command line. This is the channel real work needs: a one-liner
    pasted through two shells - bash here, cmd over ssh, PowerShell on the
    far side - has three layers of quoting between it and the code, and
    every one of them eats something. A script file has none.
    """
    encoded = base64.b64encode(_DECODER.strip().encode("utf-16-le")).decode()
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new",
           "-i", str(host["key"]), f"{host['user']}@{host['ip']}",
           "powershell", "-NoProfile", "-EncodedCommand", encoded]
    try:
        proc = subprocess.run(cmd, input=script, capture_output=True, text=True,
                               timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, "", f"the remote script exceeded {timeout}s"
    except FileNotFoundError:
        return 127, "", "ssh is not installed on this host"
    return proc.returncode, _clean(proc.stdout), _clean(proc.stderr)

def _clean(text: str) -> str:
    """Drop the CLIXML progress noise PowerShell emits over ssh, and the
    client's own post-quantum warning.

    The warning is noise from THIS machine's ssh client, not from the
    remote, and it lands on stdout where it hides the answer. A tool
    whose output starts with three lines of somebody else's warning
    gets skimmed, and the skimming is how a real result gets missed.
    """
    if not text:
        return ""
    # PowerShell emits a progress record that starts with the CLIXML
    # marker line; cut at whichever marker appears first.
    for marker in ("#< CLIXML", "<Objs"):
        if marker in text:
            text = text.split(marker)[0]
    kept = []
    for line in text.splitlines():
        if "not using a post-quantum key exchange" in line:
            continue
        if line.startswith("** WARNING:") or line.startswith("**"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


# ------------------------------------------------------------------ probes

def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def http_get(url: str, timeout: float = 8.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(400).decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def tailscale_state(host: dict) -> str:
    """The tailnet's own view of a peer.

    The online flag is not the authority - a host that has re-registered
    leaves a second record behind, and one of the two can claim to be
    online while the host is dark. The network is the authority.

    Peers are matched by IP, not by name: the tailnet records the name
    a node REGISTERED under, which is not the same as the hostname the
    node reports. This host is registered as `ultron-brain` and calls
    itself `shadow`, and only the IP tells you which record is the
    machine you are actually talking to.
    """
    if not TAILSCALE.is_file():
        return "tailscale cli not found"
    try:
        proc = subprocess.run([str(TAILSCALE), "status", "--json"], capture_output=True,
                              text=True, timeout=30, encoding="utf-8", errors="replace")
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:
        return f"tailscale status failed: {exc}"
    ip = host.get("ip")
    for peer in (data.get("Peer") or {}).values():
        ips = peer.get("TailscaleIPs") or []
        names = peer.get("HostName") or ""
        if ip and ip in ips:
            return (f"registered as '{names}' online={peer.get('Online')} "
                    f"lastSeen={peer.get('LastSeen')} os={peer.get('OS')} ip={ip}")
        if names.lower() == str(host.get("tailnet_name", "")).lower():
            return (f"registered as '{names}' online={peer.get('Online')} "
                    f"lastSeen={peer.get('LastSeen')} os={peer.get('OS')}")
    return "not in the tailnet"


# ---------------------------------------------------------------- commands

def cmd_status(host: dict) -> int:
    name = host.get("tailnet_name", host["name"])
    print(f"== {host['name']} ({name}) ==")
    print(f"  tailnet : {tailscale_state(host)}")
    reachable = tcp_open(host["ip"], 22)
    print(f"  ssh     : {'open' if reachable else 'UNREACHABLE'} on {host['ip']}:22")
    if not reachable:
        print("  -> the host is not reachable; every other check needs it up")
        return 1
    rc, out, err = ssh_command(host, _remote_identity_ps(), timeout=90)
    if rc != 0:
        print(f"  ssh exec failed (rc={rc}): {err[:200]}")
        return 1
    for line in out.splitlines():
        if line.strip():
            print("  " + line)
    for port_name, port in (("platform", host.get("platform_port")),
                             ("gateway", host.get("gateway_port"))):
        if not port:
            continue
        status, body = http_get(f"http://{host['ip']}:{port}/health")
        print(f"  {port_name:<8}: :{port} -> HTTP {status}  {body[:120]}")
    return 0


def _remote_identity_ps() -> str:
    return r'''
$ErrorActionPreference = 'SilentlyContinue'
try { "host   : " + (hostname) + "   user: " + (whoami) } catch { "host   : unknown" }
try { "os     : " + (Get-CimInstance Win32_OperatingSystem).Caption } catch {}
try { "gateway: " + ((Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'hermes_cli' } | Measure-Object).Count) + " hermes process(es)" } catch {}
'''


def cmd_platforms(host: dict) -> int:
    """The remote gateway's own view of its platforms.

    Read, not guessed: a platform in a fatal state is reported as fatal
    with its reason, because that is the difference between "the remote
    is broken" and "one channel of the remote is broken".
    """
    rc, out, err = ssh_command(host, r'''
$h = Join-Path $env:LOCALAPPDATA "hermes"
if (Test-Path "$h\gateway_state.json") {
  $s = Get-Content "$h\gateway_state.json" -Raw | ConvertFrom-Json
  "gateway_state: " + $s.gateway_state + "   pid: " + $s.pid
  foreach ($p in $s.platforms.PSObject.Properties) {
    $v = $p.Value
    $line = "  " + $p.Name.PadRight(12) + " state=" + $v.state
    if ($v.error_code) { $line += "  code=" + $v.error_code }
    if ($v.error_message) { $line += "  reason=" + ($v.error_message -replace '\s+',' ').Substring(0,[Math]::Min(120,$v.error_message.Length)) }
    $line
  }
} else { "no gateway_state.json" }
''', timeout=90)
    if rc != 0:
        print(f"  failed (rc={rc}): {err[:200]}")
        return 1
    print(out)
    return 0


def cmd_exec(host: dict, command: str, timeout: int) -> int:
    """Run a command on the remote. The command runs in the remote's
    default shell, exactly as typed - no clever wrapping."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new",
           "-i", str(host["key"]), f"{host['user']}@{host['ip']}", command]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(f"  the command exceeded {timeout}s", file=sys.stderr)
        return 124
    out = _clean(proc.stdout)
    err = _clean(proc.stderr)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return proc.returncode


def cmd_tunnel(host: dict, remote_port: int, local_port: int, detach: bool) -> int:
    """Make a remote localhost-only surface reachable from here.

    The remote's web UI and its API bind to 127.0.0.1, which the
    tailnet cannot reach. A local forward is the way in.
    """
    if not detach:
        print(f"  forwarding http://127.0.0.1:{local_port} -> "
              f"{host['ip']}:{remote_port}  (ctrl-c to stop)")
        cmd = ["ssh", "-N", "-L", f"{local_port}:127.0.0.1:{remote_port}",
               "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
               "-o", "ServerAliveInterval=30",
               "-i", str(host["key"]), f"{host['user']}@{host['ip']}"]
        return subprocess.call(cmd)
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"tunnel_{host['name']}_{remote_port}.log"
    cmd = ["ssh", "-N", "-L", f"{local_port}:127.0.0.1:{remote_port}",
           "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
           "-o", "ServerAliveInterval=30",
           "-i", str(host["key"]), f"{host['user']}@{host['ip']}"]
    with open(log, "wb") as handle:
        proc = subprocess.Popen(cmd, stdout=handle, stderr=handle,
                                stdin=subprocess.DEVNULL, close_fds=True)
    time.sleep(3)
    if proc.poll() is not None:
        print(f"  the tunnel refused to start; see {log}")
        return 1
    ok = tcp_open("127.0.0.1", local_port, timeout=4)
    print(f"  tunnel pid={proc.pid}  http://127.0.0.1:{local_port} -> "
          f"{host['ip']}:{remote_port}  {'OPEN' if ok else 'not answering'}  log={log}")
    return 0 if ok else 1


def cmd_desktop(host: dict, start: bool) -> int:
    """Report (and optionally start) the remote's Electron desktop app.

    A GUI started from an SSH session lands in session 0 with no visible
    desktop, so it is started through a scheduled task that runs in the
    interactive session instead.
    """
    script = r'''
$h = Join-Path $env:LOCALAPPDATA "hermes"
$exe = "$h\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe"
"exe      : " + $exe + "  exists=" + (Test-Path $exe)
$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'Hermes.exe' }
"running  : " + (@($running).Count) + " process(es)"
foreach ($p in @($running)) { "  pid=" + $p.ProcessId + " session=" + $p.SessionId }
foreach ($f in @("desktop.log","gui.log")) {
  $p = Join-Path $h "logs\$f"
  if (Test-Path $p) { $i = Get-Item $p; "  $f last write: " + $i.LastWriteTime + "  (" + [math]::Round($i.Length/1KB) + "KB)" }
}
'''
    rc, out, err = ssh_command(host, script, timeout=90)
    if rc != 0:
        print(f"  failed (rc={rc}): {err[:200]}")
        return 1
    print(out)
    if not start:
        return 0
    start_ps = r'''
$h = Join-Path $env:LOCALAPPDATA "hermes"
$exe = "$h\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe"
if (-not (Test-Path $exe)) { "the desktop executable is missing"; exit 2 }
$task = "HermesDesktopInteractive"
$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory (Split-Path $exe)
$princ = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $task -Action $action -Principal $princ -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $task
Start-Sleep -Seconds 6
$info = Get-ScheduledTask -TaskName $task
"task state: " + $info.State + "  last result: " + (Get-ScheduledTaskInfo -TaskName $task).LastTaskResult
$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'Hermes.exe' }
"Hermes.exe processes: " + (@($running).Count)
foreach ($p in @($running)) { "  pid=" + $p.ProcessId + " session=" + $p.SessionId }
'''
    print("  -- starting the desktop app in the interactive session --")
    rc, out, err = ssh_command(host, start_ps, timeout=120)
    print(out or err[:400])
    return rc


def cmd_script(host: dict, path: Path, timeout: int) -> int:
    """Run a local PowerShell script on the remote.

    The script travels over the SSH channel, so its length is not a
    limit: a script pasted through two shells - bash here, cmd over ssh,
    PowerShell on the far side - has three layers of quoting between it
    and the code, and every one of them eats something. A script file has
    none.
    """
    if not path.is_file():
        raise SystemExit(f"no such script: {path}")
    rc, out, err = ssh_script(host, path.read_text(encoding="utf-8", errors="replace"),
                               timeout=timeout)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return rc


def cmd_watch(host: dict, interval: int, until_online: bool, once: bool) -> int:
    """Poll a host and log when it changes state.

    The point is the CHANGE: a peer that was dark and is now up is worth
    knowing about, and a peer that keeps being dark is worth knowing
    that too.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"watch_{host['name']}.log"
    last = None
    while True:
        up = tcp_open(host["ip"], 22, timeout=3)
        state = "up" if up else "down"
        if state != last:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{stamp}] {host['name']} ({host['ip']}) is {state}"
            print("  " + line)
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            last = state
            if up and until_online:
                return 0
        if once:
            return 0 if up else 1
        time.sleep(interval)


# -------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command",
                        choices=["status", "platforms", "exec", "script", "tunnel", "desktop", "watch"])
    parser.add_argument("--host", required=True, help="a name from the remote agent registry")
    parser.add_argument("--script", type=Path, help="a local PowerShell script to run on the remote")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--remote-port", type=int, default=0)
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--until-online", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--run", help="the command to run on the remote (for exec)")
    parser.add_argument("rest", nargs="*", help="the command, for exec")
    args = parser.parse_args()

    host = resolve_host(args.host)
    if args.command == "status":
        return cmd_status(host)
    if args.command == "platforms":
        return cmd_platforms(host)
    if args.command == "exec":
        # argparse eats a bare "--" separator, so the command arrives as
        # --run "..." or as trailing words.
        command = args.run or " ".join(args.rest)
        if not command:
            raise SystemExit('exec needs a command: --run "..."')
        return cmd_exec(host, command, args.timeout)
    if args.command == "script":
        if not args.script:
            raise SystemExit("script needs --script <path>")
        return cmd_script(host, args.script, args.timeout)
    if args.command == "tunnel":
        if not args.remote_port:
            raise SystemExit("--remote-port is required")
        return cmd_tunnel(host, args.remote_port, args.local_port or args.remote_port, args.detach)
    if args.command == "desktop":
        return cmd_desktop(host, args.start)
    if args.command == "watch":
        return cmd_watch(host, args.interval, args.until_online, args.once)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
