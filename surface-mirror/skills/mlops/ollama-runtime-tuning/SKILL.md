---
name: ollama-runtime-tuning
description: Tune user-mode Ollama on Windows for VRAM and throughput.
---

# Ollama runtime tuning (Windows, user-mode)

`ollama serve` on a default Windows install leaves throughput on the table and lets the GPU thrash. Five environment variables cover most of it. This skill is the recipe.

## When to use

- Ollama is serving a single chat agent / model and VRAM swaps out mid-session
- Multiple requests queue up against one model and VRAM contention causes OOM
- First-token latency is high because the model unloads after the default 5-minute idle
- LLM throughput feels low on a GPU that should be saturated

Don't use for: authoring a new Modelfile or chat template (see `ollama-modelfile-authoring`), switching inference backends (see `llama-cpp`), or tuning a remote Ollama server.

## Detect the install mode first

`ollama` on Windows can run as either a Windows Service or a user-mode process under the logged-in user. The two paths have different env-var loading:

```bash
powershell -NoProfile -Command "Get-WmiObject Win32_Process -Filter \"name='ollama.exe'\" | Select-Object ProcessId,CommandLine,@{n='Owner';e={$_.GetOwner().User}}"
```

- **Service mode** (owner `SYSTEM` or similar): env vars live in `HKLM\SYSTEM\CurrentControlSet\Services\Ollama` value `Environment`, OR written via the GUI installer. Service restart required.
- **User mode** (owner `KING` or your user): env vars live in `HKCU\Environment`. New shell picks them up immediately, but the running `ollama.exe` needs a restart to see them.

On THRONE the install is user-mode under `KING@THRONE` — env vars go in HKCU and the `ollama.exe` restart is a manual `Stop-Process ollama` + relaunch `ollama serve`.

## The five knobs

| Env var | Recommended | Why |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | `1` | One request at a time. With multi-slot, parallel KV-cache builds compete for VRAM and the tail latency explodes. Bump to 2 only if you're sure VRAM headroom is ≥4 GB after model load. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Keeps the heaviest model pinned. Loading and unloading a 25.8B Q4_K_M takes ~8s and ~18 GB of disk read — you don't want that between every other message. |
| `OLLAMA_FLASH_ATTENTION` | `1` | Halves KV-cache memory and speeds up long-context inference. Requires GPU. If the model isn't GPU-resident this is a no-op. |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Quantises the KV cache to 8-bit. Quality loss is negligible for most workloads; memory savings are ~50% vs f16. Don't set to `q4_0` unless you're tight on VRAM — quality hits are visible. |
| `OLLAMA_KEEP_ALIVE` | `24h` | The model stays resident for 24 h instead of the default 5 min. Adjust down if you want explicit memory release; adjust up only if you have ≥ 8 GB headroom after model load. |

These compose with the existing `OLLAMA_CONTEXT_LENGTH` (set per-model) and `OLLAMA_HOST` (set to bind to a Tailscale interface if needed). Do NOT touch `OLLAMA_LLM_LIBRARY` — see pitfall.

## Procedure

### 1. Write the env vars

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_NUM_PARALLEL','1','User')
[Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS','1','User')
[Environment]::SetEnvironmentVariable('OLLAMA_FLASH_ATTENTION','1','User')
[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE','q8_0','User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE','24h','User')
```

Verify with `reg query HKCU\Environment`. The `Get-ChildItem HKCU:\Environment` PowerShell path is empty for user env vars on Windows 10+ — use `reg query` instead.

### 2. Restart Ollama

```bash
powershell -NoProfile -Command "Stop-Process -Name ollama -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-Process 'C:\Users\KING\AppData\Local\Programs\Ollama\ollama.exe' -ArgumentList 'serve'"
```

`llama-server.exe` is a child of `ollama.exe`; killing the parent takes the children with it. New `ollama serve` re-reads HKCU env on launch.

### 3. Verify env propagated

```bash
powershell -NoProfile -Command "Get-WmiObject Win32_Process -Filter \"name='ollama.exe'\" | ForEach-Object { $env = (Get-CimInstance Win32_ProcessEnvironment -Filter \"ProcessId=$($_.ProcessId)\").Environment; $env | Where-Object { $_ -match 'OLLAMA_' } }"
```

Or check `curl http://localhost:11434/api/ps` — the running model should now show the new context size and remain resident between requests.

### 4. Watch VRAM

```bash
"C:/Windows/System32/nvidia-smi.exe" --query-gpu=memory.used,memory.free --format=csv -l 5
```

A 25.8B Q4_K_M with `--ctx 65536` and q8_0 KV cache lands around **20–22 GB** on a 24 GB RTX 3090 (verified on THRONE: starscream-64k loaded = 21.7 GB VRAM). Leave the Modelfile default `num_ctx` alone — Ollama ships multi-hundred-K defaults (262144 for starscream-64k) that force CPU offload on 24 GB GPUs. Always set `num_ctx ≤ 65536` in the Modelfile or override at request time. If you see `memory.used` jump above ~22 GB during a parallel request, drop `OLLAMA_NUM_PARALLEL` to 1.

## Pitfalls

- **NEVER set `OLLAMA_LLM_LIBRARY=cpu_avx2`**. It forces the CPU-only backend, ignoring the GPU. Throughput drops ~20× and you only notice when you `nvidia-smi` and see 0% util. If you see that env var set anywhere, delete it (`reg delete HKCU\Environment /v OLLAMA_LLM_LIBRARY /f`). Set only as a deliberate debug tool when diagnosing GPU library issues.
- **Env vars in HKCU don't propagate to a running `ollama.exe`** — the parent process reads env at launch. New requests via the API pick up new model-load defaults; the running model keeps its old tuning. Restart to make the change effective.
- **`Get-CimInstance Win32_ProcessEnvironment` returns a flat string array, not a hashtable.** Filter with `Where-Object { $_ -match 'OLLAMA_' }`. Trying to index by name (`$env['OLLAMA_NUM_PARALLEL']`) returns nothing.
- **`[Environment]::SetEnvironmentVariable` returns nothing on success.** Don't check the return value — verify with `reg query HKCU\Environment` afterward.
- **`OLLAMA_MAX_LOADED_MODELS=0` is interpreted as "unlimited"**, not "zero". Set to a positive integer.
- **Setting `OLLAMA_KEEP_ALIVE=-1` (unload immediately)** is rarely what you want; the model unloads after every single request. If you actually want to free VRAM, stop `ollama serve` instead.
- **Service-mode installs ignore HKCU env entirely.** If `Get-WmiObject` shows owner `SYSTEM` or `LOCAL SERVICE`, you need to write to the service's `Environment` registry value (`HKLM\SYSTEM\CurrentControlSet\Services\Ollama`) and restart the service. That HKLM write needs elevation — see `infrastructure/windows-shell-automation` § "Hermes `terminal()` shell is not elevated".

## When the local GPU is the ceiling

Measure before you spend. Two numbers decide whether more money or better
scheduling is the answer:

```bash
nvidia-smi --query-gpu=memory.total,memory.used,utilization.gpu --format=csv
```

- **High committed VRAM, low utilisation** — capacity is committed but idle (a
  long-context model parked in VRAM between requests). The lever is scheduling
  and quantisation, not another card: unload models you are not using, drop
  `num_ctx` for interactive work, keep exactly one model resident.
- **VRAM is at the card's limit and the model class you need does not fit** —
  now money is the lever. A 70B-class model at a 64K context needs 40-80 GB,
  which no 24 GB card holds. Rent that capacity for the burst and stop it when
  the work is done: a node that is switched off when idle is a PEER, not a
  fleet. See `infrastructure/throne-sysadmin-network` § "Service and Peer
  Contracts" for the peer model and the wake command that starts a rented node
  only when the work needs it.
- **A fleet of hosted notebooks is not capacity you can use.** Notebook runtimes
  are ephemeral, hold no state, carry no secrets, and end on their own, so they
  cannot be a service, a cron target, or a dependency. They earn their keep in
  exactly two places: a sandbox for code you do not trust to run on your own
  machine, and shareable reproducible demos.

## Reference

- Ollama env-var documentation: https://github.com/ollama/ollama/blob/main/docs/faq.md
- `OLLAMA_KV_CACHE_TYPE` valid values: `f16` (default), `q8_0`, `q4_0` (quality-loss territory)

## Related

- `ollama-modelfile-authoring` — for Modelfile creation, system prompts, templates
- `llama-cpp` — for direct llama.cpp server config (different env vars, more granular)
- `local-knowledge-engine` — for the broader RAG stack (Ollama + ChromaDB + SQLite)
