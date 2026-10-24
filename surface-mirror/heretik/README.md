# HERETIK

**The elite Windows PC operator agent — runs locally, talks to your tools, never apologizes.**

A 7B AI agent that controls a Windows workstation. It has tools for system
administration, networking, files, shell, ADB, WSL, 1Password, NEXUS RAG,
Obsidian, and Hermes memory. It can self-modify, launch programs, kill
processes, scan ports, write to the registry, and tell the phone on the
other end of Tailscale to do things.

Outships ChatGPT and Grok on operator tasks because it actually operates
the machine — not just talks about it.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  HERETIK (Python agent, ~1,150 lines)                            │
│  - 33 OpenAI-format tools                                         │
│  - Tool router (selects 8-12 relevant per turn; 7Bs choke on 33)  │
│  - Confirmation gate on destructive tools                        │
│  - Persistent history at ~/.heretik_history                      │
│  - Self-modifies with backup + audit log                         │
└──────────────────────────────┬───────────────────────────────────┘
                               │  OpenAI-compatible HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  llama-server (llama.cpp b10883, CUDA 13.3)                      │
│  http://127.0.0.1:8080/v1  ·  Qwen2.5-7B-Instruct Q4_K_M         │
│  4.36 GB on disk · 5.6 GB VRAM · ~70 tok/s generation            │
└──────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `heretik.py` | The agent. 1,152 lines, 33 tools, REPL + one-shot + self-modify. |
| `heretik_system_prompt.txt` | Override this to change personality. Loaded at runtime. |
| `start_llama_qwen.cmd` | Starts the llama-server with Qwen2.5-7B (operator brain). |
| `start_llama_heretic.cmd` | Alt: starts HereticSeek-7B (uncensored chat, no tool use). |
| `launch_heretik.cmd` | Desktop icon target. Auto-starts llama if needed, then opens REPL. |

## Installation

Already installed on THRONE at:
- Agent: `C:\Users\KING\AppData\Local\hermes\heretik\`
- Model:  `D:\ai\models\Qwen2.5-7B-Instruct.Q4_K_M.gguf`
- Server: `D:\ai\llama.cpp\llama-server.exe`
- Shortcut: Desktop `HERETIK.lnk` + Start Menu `HERETIK.lnk`

## Usage

### Interactive REPL
```cmd
launch_heretik.cmd
```
Or directly:
```cmd
"C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" -u ^
   "C:\Users\KING\AppData\Local\hermes\heretik\heretik.py"
```

### One-shot
```bash
heretik.py --prompt "List the running processes and write a summary to C:/temp/report.txt" --no-confirm
```

### Change the model
```cmd
set HERETIK_BASE_URL=http://127.0.0.1:8000/v1
set HERETIK_MODEL=mistralai/Mistral-7B-Instruct-v0.3
heretik.py
```

## Tools (33)

**Filesystem**
- `shell` — bash via MSYS (use forward slashes; quote carefully)
- `read_file` — text file → string (50KB cap)
- `write_file` — overwrite a file
- `edit_file` — unique-string find/replace (surgical)
- `search_files` — ripgrep (name glob or content grep)
- `self_modify` — edit `heretik.py` itself (with backup + log)

**System**
- `system_info` — CPU/RAM/disk/GPU
- `list_processes` / `kill_process` — by name or PID
- `list_services` / `start_service` / `stop_service`
- `get_registry` / `set_registry` — HKCU only (HKLM needs admin)
- `schedule_task` — register a logon task via PowerShell
- `open_program` — start an .exe or .lnk
- `tail_log` — last N lines of a file (saves full output)

**Network**
- `network_status` — interfaces, conns, DNS
- `tailscale_status` — peer list + IPs
- `ping` / `port_check` / `ssh_run` — reachability

**Android via ADB**
- `adb_devices` / `adb_connect` / `adb_shell` / `adb_install`
- `adb_forward` / `adb_screencap`

**WSL2**
- `wsl_run` — bash inside Ubuntu WSL2

**Secrets / RAG / Notes**
- `op_list` / `op_get` — 1Password vault items (no secret reveal unless asked)
- `nexus_query` — RAG via TESSERACT /api/nexus/ask
- `obsidian_read` / `obsidian_write` / `obsidian_search`
- `hermes_skill_run` — invoke a Hermes skill
- `mem0_search` / `mem0_add` — long-term memory

**Meta**
- `hermes_skill_run` — bridge to other Hermes tools

## Confirmations

Destructive tools require a `y/N` confirmation:
- `shell`, `write_file`, `edit_file`, `kill_process`, `stop_service`,
  `set_registry`, `self_modify`, `adb_install`, `open_program`

Use `--no-confirm` (one_shot) or set `HERETIK_NO_CONFIRM=1` to skip.

## Model choice

- **Default: Qwen2.5-7B-Instruct (Q4_K_M, 4.36 GB).** Best 7B tool-caller
  available. Serves through llama.cpp on :8080 with `--jinja` for proper
  tool-call grammar. Verified end-to-end: file write, search, registry,
  NEXUS, Obsidian, Tailscale, system info, ADB — all working.

- **Alt: HERETICSEEK-7B-Ditill (Q4_K_M, 4.68 GB).** Uncensored DeepSeek
  7B fine-tune. Cached on disk at `D:/ai/models/`. Good for chat / Q&A
  / uncensored tasks, but does NOT reliably produce structured tool calls
  — it narrates actions instead of executing them. Use via
  `start_llama_heretic.cmd` + `set HERETIK_MODEL=hereticseek-7b-ditill`.

## Build notes

- **VRAM:** Qwen uses 5.6 GB at Q4_K_M. Plenty of headroom on 24 GB
  RTX 3090. You can run llama-server (Qwen) AND a second LLM (vLLM
  Mistral) if you keep both under ~22 GB combined.
- **Tool router:** 7B models choke on 30+ tool schemas. HERETIK scores
  tools by keyword overlap with the user prompt, returns top 12, and
  always includes shell + read + write + edit + search as escape hatches.
- **System prompt:** kept under 400 chars. Verbose prompts (>2k chars)
  cause 7B models to hallucinate tool calls as text instead of producing
  structured `tool_calls`. Edit `heretik_system_prompt.txt` to customize.
- **Self-modify:** the `self_modify` tool requires explicit user approval
  and writes a backup to `heretik.py.bak` plus a log entry to
  `C:\Users\KING\AppData\Local\hermes\logs\heretik_self_modify.log`.

## Verified end-to-end (2026-09-10)

- ✅ File write (real bytes on disk, content matches)
- ✅ File read (round-trip verified)
- ✅ Self-modification (3-line comment added, source file modified)
- ✅ Program launch (open_program → Explorer / file viewers)
- ✅ NEXUS RAG query (TESSERACT /api/nexus/ask)
- ✅ Obsidian search (ripgrep, returns matches)
- ✅ Tailscale status (5 peers listed, IPs correct)
- ✅ System info (real CPU/RAM/disk/GPU telemetry)
- ✅ Port check / ping / network status

## Future work

- Multi-turn conversation with memory (history is JSON, 100 turns)
- vLLM 0.27.1 with Mistral for parallel model (Qwen as operator, Mistral as advisor)
- Browser automation (cdp / playwright)
- Voice interface (ElevenLabs) — user mentioned this is a top priority
- Tighter integration with TESSERACT (use the TESSERACT API instead of duplicating NEXUS calls)
