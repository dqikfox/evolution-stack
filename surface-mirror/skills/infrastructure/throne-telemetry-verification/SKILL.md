---
name: throne-telemetry-verification
description: Verify THRONE metrics (CPU/RAM/GPU/Disk) and drive re-maps.
---

# THRONE Telemetry Verification

Procedure and pitfalls for proving "is this metric real?" on THRONE and for
remapping Q:→E: without breaking launchers. TESSERACT metrics are real,
live, and unit-coherent — but three separate unit-convention mismatches make
them *look* wrong against Task Manager / nvidia-smi.

## Step 1: Verify the live sources independently

Do not trust the API alone. Cross-check with three providers before concluding
a dashboard number is wrong:

```
# CPU + per-core + RAM + disk (Task Manager's own source)
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Processor; Get-CimInstance Win32_OperatingSystem; Get-CimInstance Win32_LogicalDisk -Filter DriveType=3"

# GPU truth (bypasses NVML's process-ownership quirks)
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits

# TESSERACT API (the number the dashboard shows)
curl -s http://127.0.0.1:8705/api/stats
```

## Step 2: Apply the unit-convention table

Most "wrong-looking" numbers on THRONE are psutil GB vs WMI/TaskManager GiB:

| Field | psutil output | Task Manager / hardware | Mismatch source |
|---|---|---|---|
| RAM total | 68.39 GB | 63.7 GiB | GB (10⁹) vs GiB (2³⁰) — both correct, one label |
| Disk C: | 2000.3 GB | 1862.9 GiB | GB vs GiB — same drive |
| Disk D: | 1024.2 GB | 953.9 GiB | GB vs GiB |
| Disk E: | 5001 GB | 4657.5 GiB | GB vs GiB (Seagate One Touch 5TB) |
| GPU total | 25.77 GB | 24 GiB | NVML-reported usable vs card label |

**Rule:** when `psutil total_gb` = 1.073 × `TaskManager GiB`, the number is
real — it's a unit convention, not a data bug. Use `ram.total_gib` for the
"64 GB installed" parity display.

## Step 3: Interpret GPU memory vs utilization

On a host where Ollama + llama-server.exe are always resident:

- `gpu.percent` (compute util) ≈ 2–8 % is **real** — the models are
  memory-resident but compute-idle.
- `gpu.mem_used_gb` ≈ 23–25 GB is **real** — those are the loaded models
  holding VRAM so they don't rehydrate per request.
- The 3090 running `mem_used ≈ mem_total` at `util = 0` is **by design**,
  not a leak. Do not "fix" it by unloading models.

## Step 4: Diagnose the :8650 port before trusting NEXUS health

Two different services can occupy :8650 — verify via `curl /health` and
inspect the `service` + `components.database.notes_count` fields together:

| Service | `/health` shape | Meaning |
|---|---|---|
| nexus-core 3.3.0 | `"service":"nexus-core"`, `notes_count: 2000+` | Real brain on E:\ultron-memory\nexus-core |
| TESSERACT migration stub | `"service":"tesseract"`, `notes_count: 0` | Old stub on C: — port-squatter, kill and relaunch nexus |

A 200 OK alone is not a health signal. When in doubt, `taskkill /PID <pid> /F`
the squatter and launch `C:/Users/KING/.cache/nexus-venv/Scripts/python.exe E:/ultron-memory/nexus-core/start.py`. Launch it via `terminal(background=true, notify=['Uvicorn running'])` — the command's own `&` backgrounding is rejected by the terminal tool, and a foreground run hangs the shell.

Before reporting NEXUS "running" as healthy, also `curl /openapi.json` and check the path surface: the real nexus-core exposes `/api/elite/*`, `/api/hive/*`, `/v1/chat/completions`; the stub exposes `/api/nexus/*` only. Path shape is the identity, not the port.

## Step 6: Dual drive letters (Q: alongside E:)

When the user wants an old drive letter to keep resolving after migrating to a new one, do not reach for `mountvol` — it returns `The parameter is incorrect.` for a second native letter on the same volume, and `Add-PartitionAccessPath` needs elevation the Hermes terminal doesn't have.

Working pattern — `subst` + logon task:

```
subst Q: "E:\\"   # quoting: bash strips backslashes; this reaches cmd as subst Q: E:\
```

Then persist across reboots with a Scheduled Task at user logon running a .cmd wrapper (subst is per-user and non-persistent):

```
# C:\Users\KING\AppData\Local\hermes\scripts\persist_dual_letter_q_to_e.cmd:
subst Q: E:\ 2>nul
# Registered as:\npowershell -Command "Register-ScheduledTask -TaskName 'SubstQ2E' -Action (New-ScheduledTaskAction -Execute <cmd>) -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)"
```

Verify with a cross-letter write: `echo test > Q:/x.txt && cat E:/x.txt && rm Q:/x.txt`. Canonical path stays E:; Q: is the alias layer for legacy hardcoded references.

## Step 5: Drive-letter migration (Q: → E:) without broken launchers

When a physical drive arrives as a new letter, the data migration is easy —
the **ghosts in `.lnk` files** are what break first. Procedure:

1. `df -h` + `Get-Volume` to confirm the new letter maps to the same physical
   device (match Size against the old letter's recorded size).
2. `rg '\bQ:' --glob '!nul' <project-root>` for hardcoded letters. Patch configs
   (TESSERACT `core/config.py` `launch_dir`, `seed.py`, `docs/ARCHITECTURE.md`,
   live `templates/import.html` defaults).
3. Scan and rewrite .lnk files on Desktop + Start Menu (both `WorkingDirectory`
   AND `Arguments`/`TargetPath`):
   ```
   powershell.exe -NoProfile -Command "
     $sh = New-Object -ComObject WScript.Shell
     Get-ChildItem $env:USERPROFILE\Desktop, \"$env:APPDATA\Microsoft\Windows\Start Menu\" -Recurse -Filter *.lnk |
     ForEach-Object { $l = $sh.CreateShortcut($_.FullName); if ($l.WorkingDirectory -match '^Q:' -or $l.Arguments -match 'Q:') { $l.WorkingDirectory = $l.WorkingDirectory -replace '^Q:', 'E:'; $l.Arguments = $l.Arguments -replace 'Q:', 'E:'; $l.Save() } }"
   ```
4. `.vbs` / `.bat` launchers hardcode `nexusRoot` and `LOG_FILE` — patch in
   place; scripts that resolve `Path(__file__).parent` survive untouched.
5. `notes/**` and `README/CHANGELOG` historical mentions are **content**, not
   paths — leave them.

## Reference: THRONE live stats shape (TESSERACT :8705)

`curl http://127.0.0.1:8705/api/stats` returns

- `cpu.percent / per_core / freq_mhz / cores / threads` (psutil, live)
- `ram.percent / used_gb / total_gb / total_gib / available_gb`
- `swap.percent / used_gb / total_gb`
- `disk[] = { mountpoint, total_gb, used_gb, free_gb, percent }` (C: D: E:)
- `gpu.name / percent / mem_used_gb / mem_total_gb / mem_total_phys_gb / mem_pct / temp_c / fan_pct / power_w` (pynvml)
- `network.bytes_dl_s / bytes_ul_s` (psutil delta)
- `process_count / uptime_s / ts`