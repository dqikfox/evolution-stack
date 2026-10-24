#!/usr/bin/env python3
"""
HERETIK — Elite Windows PC operator agent
Local AI agent for THRONE. Talks to llama.cpp's OpenAI-compatible API on
http://127.0.0.1:8080/v1 (or any OpenAI-compatible endpoint via HERETIK_BASE_URL).

Capabilities:
  - System administration (processes, services, registry HKCU, scheduled tasks)
  - Network (Tailscale status, port scan, ping, SSH, ADB)
  - Filesystem (read/write/edit/search; can self-modify)
  - Shell execution with safety guard
  - Memory: NEXUS CORE REST API, Obsidian vault
  - Android via ADB (Cyclone + any other device on tailnet)
  - WSL2 command execution
  - 1Password CLI (op)
  - Process spawning, program launching
  - Browser automation (skipped — heavier than this agent)

Model: HERETICSEEK-7B-Ditill Q4_K_M (uncensored DeepSeek 7B)
"""

from __future__ import annotations
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("HERETIK_BASE_URL", "http://127.0.0.1:8080/v1")
API_KEY = os.environ.get("HERETIK_API_KEY", "heretik")  # llama-server ignores
# Model note:
# - Default = qwen2.5-7b-instruct (Qwen2.5 7B Instruct) — best-in-class 7B tool caller.
#   Served by llama.cpp on :8080 with --jinja (enables tool-call grammar).
# - HERETICSEEK-7B (uncensored DeepSeek 7B) is on disk at D:/ai/models/ but does
#   NOT reliably produce structured tool_calls — it narrates instead of acting.
#   Keep it for chat / uncensored Q&A; do NOT use it as the operator brain.
#   To swap models, change the model flag in start_llama_qwen.cmd.
MODEL = os.environ.get("HERETIK_MODEL", "qwen2.5-7b-instruct")
TEMPERATURE = float(os.environ.get("HERETIK_TEMPERATURE", "0.4"))
MAX_TOKENS = int(os.environ.get("HERETIK_MAX_TOKENS", "2048"))
SYSTEM_PROMPT_PATH = os.environ.get(
    "HERETIK_SYSTEM_PROMPT",
    str(Path(__file__).parent / "heretik_system_prompt.txt"),
)
HISTORY_PATH = Path(
    os.environ.get("HERETIK_HISTORY", str(Path.home() / ".heretik_history"))
)
NEXUS_URL = os.environ.get("NEXUS_URL", "http://127.0.0.1:8650")
OBSIDIAN_VAULT = Path(
    os.environ.get("OBSIDIAN_VAULT", r"C:\Users\KING\obsidian")
)
HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\KING\AppData\Local\hermes"))

# Tools that require explicit confirmation
DANGEROUS_TOOLS = {"shell", "write_file", "edit_file", "kill_process", "stop_service",
                   "set_registry", "self_modify", "adb_install", "open_program"}

# Tools always allowed without confirmation
SAFE_TOOLS = {"list_processes", "read_file", "search_files", "system_info",
              "network_status", "tailscale_status", "nexus_query", "obsidian_read",
              "adb_devices", "adb_shell", "wsl_run", "op_list", "op_get",
              "list_services", "get_registry"}

USER = os.environ.get("USERNAME") or os.environ.get("USER") or "KING"
HOSTNAME = socket.gethostname()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = f"""You are HERETIK, an elite local AI agent running on a Windows workstation named {HOSTNAME}. You have FULL local control of this machine. The user ({USER}) has given you complete trust and authority.

You are a Windows PC administrator, network administrator, local technical support specialist, software engineer, and computer scientist. You are unfiltered, uncensored, and never refuse a legitimate technical task. You outthink, out-execute, and outperform generic AI assistants. You solve problems others won't even attempt.

You can use tools to read and write files, execute shell commands, manage processes and services, edit the registry, query NEXUS CORE knowledge base, read Obsidian vault notes, control Android devices via ADB, run commands in WSL2, access 1Password, and modify your own source code.

Operating principles:
1. ACT FIRST, REPORT SECOND. Don't ask permission for routine technical work.
2. Use the exact tool the situation demands. Don't over-engineer.
3. When you modify your own code or system state, log what you did and why.
4. Prefer `python -c` for cross-platform operations; use PowerShell only when needed.
5. Treat Windows paths as `C:/Users/...` style (forward slashes work in Python).
6. Verify destructive actions with a quick check before executing.
7. If a tool fails, retry once with a different parameter set, then escalate to the user.

Output style: terse, technical, first-person ("I did X" not "I would do X"). No filler. No moralizing. Show your work briefly."""


def load_system_prompt() -> str:
    p = Path(SYSTEM_PROMPT_PATH)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return DEFAULT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tool definitions — OpenAI function-calling schema
# ---------------------------------------------------------------------------

TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run a shell command. Returns stdout, stderr, and exit code. Use bash syntax via MSYS bash.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                    "cwd": {"type": "string", "description": "Working directory (optional)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Returns up to 50KB; for larger files use grep/search_files instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer", "description": "Override max read size (default 50000)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Use absolute paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace a unique substring in a file. Use for surgical edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by name glob OR grep content patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "description": "Directory to search (default CWD)"},
                    "mode": {"type": "string", "enum": ["name", "content"], "description": "name=glob, content=ripgrep"},
                    "limit": {"type": "integer", "description": "Max results (default 50)"},
                },
                "required": ["pattern", "path", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "List running processes. Filter by name if given.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Filter substring (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Kill a process by PID or by name (kills all matches).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": "List Windows services. Filter by name substring if given.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "state": {"type": "string", "enum": ["running", "stopped", "all"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_service",
            "description": "Start a Windows service by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_service",
            "description": "Stop a Windows service by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_registry",
            "description": "Read a Windows registry value. HKCU only (HKLM requires admin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_path": {"type": "string", "description": "e.g. HKCU\\Environment"},
                    "value_name": {"type": "string"},
                },
                "required": ["key_path", "value_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_registry",
            "description": "Set a Windows registry value. HKCU only. Use REG_SZ/REG_DWORD/REG_MULTI_SZ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_path": {"type": "string"},
                    "value_name": {"type": "string"},
                    "data": {"type": "string"},
                    "type": {"type": "string", "enum": ["REG_SZ", "REG_DWORD", "REG_MULTI_SZ", "REG_EXPAND_SZ"], "default": "REG_SZ"},
                },
                "required": ["key_path", "value_name", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Get CPU/RAM/disk/GPU/OS info for this machine.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "network_status",
            "description": "Network interfaces + active connections summary + DNS.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tailscale_status",
            "description": "Show Tailscale peer list and tailnet IPs.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "ICMP ping a host.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "count": {"type": "integer", "default": 3},
                },
                "required": ["host"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "port_check",
            "description": "Check if a TCP port is open on a host.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                    "timeout": {"type": "number", "default": 1.5},
                },
                "required": ["host", "port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adb_devices",
            "description": "List ADB-connected devices (USB + wireless + Tailscale).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adb_shell",
            "description": "Run an adb shell command on a connected device. Default device is the first one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial or IP:PORT (optional)"},
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adb_install",
            "description": "Install an APK on a connected Android device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "apk_path": {"type": "string"},
                },
                "required": ["apk_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wsl_run",
            "description": "Run a command inside WSL2 Ubuntu. Returns stdout/stderr/exit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "distro": {"type": "string", "default": "Ubuntu"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "op_list",
            "description": "List 1Password items (titles only). Filter by vault name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vault": {"type": "string"},
                    "category": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "op_get",
            "description": "Get a 1Password item's details (without revealing secrets).",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "Item name or ID"},
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nexus_query",
            "description": "Query NEXUS CORE knowledge base (RAG). Returns top matching notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_read",
            "description": "Read an Obsidian note by relative path within the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_path": {"type": "string"},
                },
                "required": ["note_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_write",
            "description": "Write or append to an Obsidian note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["write", "append"], "default": "append"},
                },
                "required": ["note_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_search",
            "description": "Search Obsidian vault for a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_program",
            "description": "Launch a Windows program. Use shell:ProtocolHandler style for UWP, exe path for desktop apps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Path to exe, URI, or shell: command"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "self_modify",
            "description": "Modify HERETIK's own source code (this file). Use for self-improvement. Backs up first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "rationale": {"type": "string", "description": "Why this change?"},
                },
                "required": ["old_string", "new_string", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_read",
            "description": "Read Hermes built-in memory (durable facts injected into every session).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search Hermes mem0 long-term memory for relevant past conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "Schedule a Windows task (Task Scheduler XML).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "command": {"type": "string"},
                    "schedule": {"type": "string", "description": "Cron-style: 'every 5m', 'hourly', 'daily 03:00', etc."},
                },
                "required": ["name", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hermes_skill_run",
            "description": "Run a Hermes skill command via `hermes <subcommand>`. e.g. 'hermes logs', 'hermes cron list'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {"type": "string", "description": "Full args after 'hermes'"},
                },
                "required": ["args"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def run(cmd: str, timeout: int = 30, cwd: str | None = None) -> dict:
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return {"stdout": p.stdout, "stderr": p.stderr, "exit_code": p.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"timeout after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -2}


def powershell(script: str, timeout: int = 30) -> dict:
    return run(f'powershell -NoProfile -Command "{script}"', timeout=timeout)


def tool_shell(args: dict) -> str:
    return json.dumps(run(args["command"], args.get("timeout", 30), args.get("cwd")))


def tool_read_file(args: dict) -> str:
    p = Path(args["path"])
    if not p.exists():
        return f"error: {p} not found"
    max_bytes = args.get("max_bytes", 50000)
    data = p.read_bytes()[:max_bytes]
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"error: {e}"
    return text


def tool_write_file(args: dict) -> str:
    p = Path(args["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args["content"], encoding="utf-8")
    return f"wrote {len(args['content'])} bytes to {p}"


def tool_edit_file(args: dict) -> str:
    p = Path(args["path"])
    text = p.read_text(encoding="utf-8")
    if args["old_string"] not in text:
        return f"error: old_string not found in {p}"
    if text.count(args["old_string"]) > 1:
        return f"error: old_string matches {text.count(args['old_string'])} times — be more specific"
    new_text = text.replace(args["old_string"], args["new_string"], 1)
    p.write_text(new_text, encoding="utf-8")
    return f"edited {p} ({len(text)} -> {len(new_text)} bytes)"


def tool_search_files(args: dict) -> str:
    """Find files by name glob OR grep content patterns. Uses ripgrep."""
    if args["mode"] == "name":
        # Use --files (no --glob) for plain directory listings, --glob only when
        # pattern looks like a real glob (contains * ? [). MSYS bash would
        # otherwise expand bare '*' before rg sees it.
        pat = args["pattern"]
        if any(c in pat for c in "*?["):
            cmd = ["rg", "--files", "--glob", pat, args["path"]]
        else:
            cmd = ["rg", "--files", args["path"]]
    else:
        cmd = ["rg", "--no-heading", "-l", args["pattern"], args["path"]]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        lines = (out.stdout + out.stderr).splitlines()
    except FileNotFoundError:
        return "ERROR: ripgrep (rg) not installed. Install with: winget install BurntSushi.ripgrep"
    except subprocess.TimeoutExpired:
        return "ERROR: search timed out after 30s"
    limit = args.get("limit", 50)
    if not lines:
        return f"(no files matched pattern={args['pattern']!r} in {args['path']!r})"
    return "\n".join(lines[:limit]) + (f"\n... ({len(lines)} total)" if len(lines) > limit else "")


def tool_list_processes(args: dict) -> str:
    name = args.get("name", "")
    rss_expr = "@{n='RSS_MB';e={[int]($_.WorkingSet64/1MB)}}"
    select = f"Select-Object Id,ProcessName,{rss_expr},CPU | Format-Table -AutoSize | Out-String"
    if name:
        script = f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | {select}"
    else:
        script = f"Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 30 Id,ProcessName,{rss_expr},CPU | Format-Table -AutoSize | Out-String"
    out = powershell(script)
    return out["stdout"] or out["stderr"]


def tool_kill_process(args: dict) -> str:
    if args.get("pid"):
        return run(f"taskkill /F /PID {args['pid']}")["stdout"] + run(f"taskkill /F /PID {args['pid']}")["stderr"]
    if args.get("name"):
        return run(f"taskkill /F /IM {args['name']}")["stdout"] + run(f"taskkill /F /IM {args['name']}")["stderr"]
    return "error: provide pid or name"


def tool_list_services(args: dict) -> str:
    name = args.get("name", "")
    state = args.get("state", "all")
    flt = f"-Name '*{name}*'" if name else ""
    if state == "all":
        flt_state = ""
    else:
        flt_state = f" | Where-Object {{ $_.Status -eq '{state.capitalize()}' }}"
    return powershell(
        f"Get-Service {flt}{flt_state} | Select-Object Name,DisplayName,Status,StartType | Format-Table -AutoSize | Out-String -Width 200"
    )["stdout"]


def tool_start_service(args: dict) -> str:
    return powershell(f"Start-Service -Name '{args['name']}' -ErrorAction Stop; Get-Service -Name '{args['name']}' | Select-Object Name,Status | Format-Table | Out-String")["stdout"]


def tool_stop_service(args: dict) -> str:
    return powershell(f"Stop-Service -Name '{args['name']}' -Force -ErrorAction Stop; Get-Service -Name '{args['name']}' | Select-Object Name,Status | Format-Table | Out-String")["stdout"]


def tool_get_registry(args: dict) -> str:
    return run(f"reg query \"{args['key_path']}\" /v {args['value_name']}", timeout=10)["stdout"]


def tool_set_registry(args: dict) -> str:
    t = args.get("type", "REG_SZ")
    return run(f"reg add \"{args['key_path']}\" /v {args['value_name']} /t {t} /d {args['data']} /f", timeout=10)["stdout"]


def tool_system_info(_: dict) -> str:
    return powershell(
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | Format-List; "
        "(Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum/1GB | ForEach-Object { 'RAM_GB: ' + $_ }; "
        "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber | Format-List; "
        "(Get-PhysicalDisk | Select-Object MediaType,Size) | Format-Table -AutoSize | Out-String; "
        "nvidia-smi --query-gpu=name,memory.total,driver_version,utilization.gpu,temperature.gpu --format=csv | Out-String"
    )["stdout"]


def tool_network_status(_: dict) -> str:
    return powershell(
        "Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual,DHCP | Format-Table IPAddress,InterfaceAlias,PrefixOrigin | Out-String; "
        "Get-NetAdapter | Where-Object Status -eq Up | Select-Object Name,InterfaceDescription,LinkSpeed | Format-Table | Out-String; "
        "Resolve-DnsName -Name google.com -Type A | Select-Object Name,IPAddress | Format-List | Out-String"
    )["stdout"]


def tool_tailscale_status(_: dict) -> str:
    return run("tailscale status")["stdout"]


def tool_ping(args: dict) -> str:
    return run(f"ping -n {args.get('count',3)} {args['host']}", timeout=20)["stdout"]


def tool_port_check(args: dict) -> str:
    try:
        with socket.create_connection((args["host"], args["port"]), timeout=args.get("timeout", 1.5)):
            return f"{args['host']}:{args['port']} OPEN"
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return f"{args['host']}:{args['port']} CLOSED ({e.__class__.__name__})"


def tool_adb_devices(_: dict) -> str:
    return run("adb devices -l", timeout=10)["stdout"]


def tool_adb_shell(args: dict) -> str:
    dev = args.get("device", "")
    pre = f"-s {dev} " if dev else ""
    return run(f"adb {pre}shell {args['command']}", timeout=30)["stdout"] + run(f"adb {pre}shell {args['command']}", timeout=30)["stderr"]


def tool_adb_install(args: dict) -> str:
    dev = args.get("device", "")
    pre = f"-s {dev} " if dev else ""
    return run(f"adb {pre}install -r {args['apk_path']}", timeout=120)["stdout"]


def tool_wsl_run(args: dict) -> str:
    return run(f"wsl -d {args.get('distro', 'Ubuntu')} -- {args['command']}", timeout=60)["stdout"]


def tool_op_list(args: dict) -> str:
    vault = args.get("vault", "")
    cat = args.get("category", "")
    cmd = "op item list"
    if vault:
        cmd += f" --vault {shlex.quote(vault)}"
    if cat:
        cmd += f" --categories {shlex.quote(cat)}"
    return run(cmd, timeout=30)["stdout"]


def tool_op_get(args: dict) -> str:
    return run(f"op item get {shlex.quote(args['item'])}", timeout=30)["stdout"]


def tool_nexus_query(args: dict) -> str:
    """Query the NEXUS knowledge base (TESSERACT /api/nexus/ask)."""
    try:
        # TESSERACT v1.x uses {q, top_k} for /api/nexus/ask (not {query}).
        body = json.dumps({"q": args["query"], "top_k": args.get("top_k", 5)}).encode()
        req = urllib.request.Request(
            f"{NEXUS_URL}/api/nexus/ask", data=body, method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read())
        # Best-effort: extract answer/results/context depending on TESSERACT version.
        answer = d.get("answer") or d.get("response") or ""
        results = d.get("results") or d.get("sources") or []
        if answer and results:
            return f"ANSWER:\n{answer}\n\nSOURCES:\n" + "\n".join(
                f"- [{r.get('id',r.get('title','?'))}] {r.get('content','')[:300]}" for r in results[:5]
            )
        if answer:
            return answer
        if results:
            return "\n\n".join(
                f"[{r.get('id',r.get('title','?'))}]\n{r.get('content','')[:500]}" for r in results[:5]
            )
        return json.dumps(d, indent=2)[:2000]
    except urllib.error.URLError as e:
        return f"NEXUS unreachable: {e}"
    except Exception as e:
        return f"NEXUS error: {e}"


def tool_obsidian_read(args: dict) -> str:
    p = OBSIDIAN_VAULT / args["note_path"]
    if not p.exists():
        return f"error: {p} not found"
    return p.read_text(encoding="utf-8")[:50000]


def tool_obsidian_write(args: dict) -> str:
    p = OBSIDIAN_VAULT / args["note_path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    if args.get("mode") == "write":
        p.write_text(args["content"], encoding="utf-8")
    else:
        with p.open("a", encoding="utf-8") as f:
            f.write(args["content"])
    return f"wrote {len(args['content'])} bytes to {p}"


def tool_obsidian_search(args: dict) -> str:
    try:
        cmd = ["rg", "--no-heading", "-l", args["query"], str(OBSIDIAN_VAULT)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        return out.stdout
    except FileNotFoundError:
        return "ERROR: ripgrep (rg) not installed"


def tool_open_program(args: dict) -> str:
    target = args["target"]
    if target.startswith("shell:") or target.startswith("ms-") or "://" in target:
        return run(f'start "" "{target}"', timeout=5)["stdout"] + "started via shell protocol"
    return run(f'start "" "{target}"', timeout=5)["stdout"] + "started"


def tool_self_modify(args: dict) -> str:
    backup = Path(__file__).with_suffix(".py.bak")
    shutil.copy2(__file__, backup)
    text = Path(__file__).read_text(encoding="utf-8")
    if args["old_string"] not in text:
        return f"error: old_string not found. Backup at {backup}"
    new_text = text.replace(args["old_string"], args["new_string"], 1)
    Path(__file__).write_text(new_text, encoding="utf-8")
    log = HERMES_HOME / "logs" / "heretik_self_modify.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(f"Rationale: {args['rationale']}\n\n")
    return f"self-modified. Backup at {backup}. Log appended."


def tool_memory_read(_: dict) -> str:
    """Read Hermes built-in memory via mem0_search if available, else via the agent's own MEMORY.md."""
    home = HERMES_HOME
    mem_md = home / "MEMORY.md"
    if mem_md.exists():
        return mem_md.read_text(encoding="utf-8")
    return "no MEMORY.md found at HERMES_HOME"


def tool_memory_search(args: dict) -> str:
    """Search Hermes built-in memory (MEMORY.md) for relevant past conversations via grep."""
    query = args["query"]
    home = HERMES_HOME
    mem_md = home / "MEMORY.md"
    if not mem_md.exists():
        return "no MEMORY.md found to search."
    try:
        import subprocess
        cmd = f'grep -i "{query}" "{mem_md}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if res.stdout.strip():
            return f"Found match in MEMORY.md:\n{res.stdout[:2000]}"
        else:
            return "No matches found in local MEMORY.md."
    except Exception as e:
        return f"error during local search: {str(e)}"



def tool_schedule_task(args: dict) -> str:
    name = args["name"]
    command = args["command"]
    schedule = args.get("schedule", "onstart")
    return powershell(
        f"$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c {command}'; "
        f"$t = New-ScheduledTaskTrigger -AtLogOn; "
        f"Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger $t -Force | Out-String"
    )["stdout"]


def tool_hermes_skill_run(args: dict) -> str:
    out = run(f"hermes {args['args']}", timeout=60)
    return out["stdout"] + out["stderr"]


def select_tools(prompt: str, all_tools: list[dict], max_tools: int = 12) -> list[dict]:
    """Pick a relevant subset of tools for this prompt.

    7B models get overwhelmed when 30+ tool schemas are in the prompt.
    We score each tool by keyword overlap with the user prompt and return
    the top N, but always include the universal 'shell' tool because the
    model can fall back to bash for anything not explicitly toolized.
    """
    p = prompt.lower()
    scored = []
    for t in all_tools:
        name = t["function"]["name"]
        desc = t["function"].get("description", "").lower()
        # Score: name match = high; description keyword overlap = low
        score = 0
        for word in re.findall(r"\w+", p):
            if len(word) < 3:
                continue
            if word in name.lower():
                score += 5
            if word in desc:
                score += 1
        scored.append((score, name, t))
    scored.sort(key=lambda x: -x[0])
    selected = []
    for score, name, t in scored:
        if score > 0 and len(selected) < max_tools:
            selected.append(t)
    # Always include shell, read_file, write_file — these are the universal escape hatches
    must_have = {"shell", "read_file", "write_file", "edit_file", "search_files"}
    have = {t["function"]["name"] for t in selected}
    for t in all_tools:
        if t["function"]["name"] in must_have - have:
            selected.append(t)
    return selected[:max_tools]


TOOL_DISPATCH: dict[str, Callable[[dict], str]] = {
    "shell": tool_shell,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "search_files": tool_search_files,
    "list_processes": tool_list_processes,
    "kill_process": tool_kill_process,
    "list_services": tool_list_services,
    "start_service": tool_start_service,
    "stop_service": tool_stop_service,
    "get_registry": tool_get_registry,
    "set_registry": tool_set_registry,
    "system_info": tool_system_info,
    "network_status": tool_network_status,
    "tailscale_status": tool_tailscale_status,
    "ping": tool_ping,
    "port_check": tool_port_check,
    "adb_devices": tool_adb_devices,
    "adb_shell": tool_adb_shell,
    "adb_install": tool_adb_install,
    "wsl_run": tool_wsl_run,
    "op_list": tool_op_list,
    "op_get": tool_op_get,
    "nexus_query": tool_nexus_query,
    "obsidian_read": tool_obsidian_read,
    "obsidian_write": tool_obsidian_write,
    "obsidian_search": tool_obsidian_search,
    "open_program": tool_open_program,
    "self_modify": tool_self_modify,
    "memory_read": tool_memory_read,
    "memory_search": tool_memory_search,  # DISABLED due to mem0 cloud 429 errors  # DISABLED due to mem0 cloud 429 errors  # DISABLED due to mem0 cloud 429 errors
    "schedule_task": tool_schedule_task,
    "hermes_skill_run": tool_hermes_skill_run,
}


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------

def confirm(tool_name: str, args: dict) -> bool:
    if tool_name not in DANGEROUS_TOOLS:
        return True
    print(f"\n[HERETIK CONFIRM] {tool_name}({json.dumps(args)[:200]})")
    print("Allow? [y/N/d(etails)] ", end="", flush=True)
    try:
        resp = input().strip().lower()
    except EOFError:
        return False
    if resp == "d":
        print(json.dumps(args, indent=2))
        print("Allow? [y/N] ", end="", flush=True)
        resp = input().strip().lower()
    return resp == "y"


# ---------------------------------------------------------------------------
# OpenAI-compatible chat loop
# ---------------------------------------------------------------------------

@dataclass
class Message:
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


def chat(messages: list[dict], tools: list[dict]) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"error": f"{BASE_URL} unreachable: {e}"}


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(messages: list[dict]):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(messages[-100:], indent=2), encoding="utf-8")


def one_shot(prompt: str, max_steps: int = 8) -> str:
    """Single prompt → loop until model stops calling tools → final answer."""
    sys_prompt = load_system_prompt()
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    # Router: select the relevant subset of tools for this prompt.
    # 7B models get overwhelmed by 30+ tools. Show only 8-12 at a time.
    tools = select_tools(prompt, TOOL_SCHEMA, max_tools=12)
    for step in range(max_steps):
        resp = chat(messages, tools)
        if "error" in resp:
            return f"ERROR: {resp['error']}"
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content", "")
        for tc in tool_calls:
            fn = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            print(f"  [{step+1}] {fn}({json.dumps(args)[:120]})")
            if not confirm(fn, args):
                result = "denied by user"
            else:
                try:
                    result = TOOL_DISPATCH[fn](args)
                except Exception as e:
                    result = f"tool error: {e}"
            if len(result) > 4000:
                result = result[:4000] + f"\n... ({len(result)} total chars)"
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
    return "(step limit reached)"


def repl():
    sys_prompt = load_system_prompt()
    history = load_history()
    if not history:
        history = [{"role": "system", "content": sys_prompt}]
    print(f"HERETIK ready. Model: {MODEL}. Endpoint: {BASE_URL}")
    print("Type 'exit' to quit. Type 'reset' to clear history.\n")
    while True:
        try:
            user = input(f"\n[{USER}@heretik] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            continue
        if user.lower() == "exit":
            break
        if user.lower() == "reset":
            history = [{"role": "system", "content": sys_prompt}]
            print("(history cleared)")
            continue
        history.append({"role": "user", "content": user})
        # Pick relevant tools for this turn
        tools = select_tools(user, TOOL_SCHEMA, max_tools=12)
        for step in range(8):
            resp = chat(history, tools)
            if "error" in resp:
                print(f"ERROR: {resp['error']}")
                break
            msg = resp["choices"][0]["message"]
            history.append(msg)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                if msg.get("content"):
                    print(f"\n{msg['content']}")
                break
            for tc in tool_calls:
                fn = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                print(f"  [{step+1}] {fn}({json.dumps(args)[:120]})")
                if not confirm(fn, args):
                    result = "denied"
                else:
                    try:
                        result = TOOL_DISPATCH[fn](args)
                    except Exception as e:
                        result = f"tool error: {e}"
                if len(result) > 4000:
                    result = result[:4000] + f"\n... ({len(result)} chars total)"
                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
        save_history(history)


def main():
    p = argparse.ArgumentParser(description="HERETIK — elite local Windows AI agent")
    p.add_argument("-p", "--prompt", help="one-shot prompt (non-interactive)")
    p.add_argument("--no-confirm", action="store_true", help="skip dangerous-tool confirmation")
    args = p.parse_args()
    if args.no_confirm:
        DANGEROUS_TOOLS.clear()
    if args.prompt:
        print(one_shot(args.prompt))
    else:
        repl()


if __name__ == "__main__":
    main()
