---
name: throne-model-training
description: Train a model on THRONE's voice, stack, and decisions.
version: 1.0.0
---

# THRONE model training

End-to-end pipeline to fine-tune a chat model so it speaks like Hitchy and knows THRONE's stack. Lives at `E:/ultron-training/`.

## When to use

- Building a local model that knows your projects by name (TESSERACT, ULTRON, NEXUS CORE) instead of guessing.
- Distilling a teacher model (Starscream-64k) into a smaller student (Qwen2.5-7B) for cost/latency.
- Producing a model that can be served via Ollama as `qikfox/<name>:latest`.

## The 6 stages

| # | Script | Output |
|---|---|---|
| 1 | `scripts/01_harvest.py` | Walk + normalize per-source corpora → `raw/` |
| 2 | `scripts/02_clean.py` | Length-filter + dedup → `datasets/cleaned.jsonl` |
| 3 | `scripts/03_format.py` | Wrap as chat or completion → `chat_*.jsonl` + `completion_*.jsonl` |
| 4 | `scripts/04_train.py` | QLoRA SFT via peft+trl → LoRA adapter |
| 5 | `scripts/05_merge.py` | Merge adapter into base → FP16 model |
| 6 | `scripts/06_export_gguf.py` | HF → GGUF → `ollama create` |

Plus post-stage infrastructure shipped in this repo:

| Script | What | When |
|---|---|---|
| `scripts/07_backup_models.py` | Mirror `models/` → `D:\ultron-training-backup\models\` via robocopy | Daily 04:00 |
| `scripts/08_log_decision.py` | Append-only decisions log at `E:\ultron-memory\decisions\` + INDEX | Whenever a design choice lands |
| `scripts/09_eval.py` | 30-prompt eval suite across 8 categories with substring/refusal/length scoring | Daily 06:00 and after SFT |
| `scripts/10_continuous_train.py` | Watch 7 source roots, re-run harvest on changes, snapshot datasets | Weekly Sun 02:00 |
| `scripts/11_lb.py` | Load-balancer proxy on :8501 preferring Heretik over Ollama, health-checked | Always-on |
| `scripts/12_orchestrator.py` | Routes a job to the host (THRONE/MSI/phone) with most free VRAM | On demand |
| `scripts/13_load_test.py` | N-concurrency soak with p50/p95/p99 latency + throughput + error rate | When validating a new model release |
| `scripts/14_alerts.py` | Probes 7 services + 3 disks + VRAM, toasts + logs + optional webhook | Every 5 min via THRONE_Watchdog_5min |
| `scripts/15_post_train.py` | Poll for adapter → merge → GGUF → `ollama create` → swap Heretik GGUF | Run after `04_train.py` finishes |

Pipeline is data-flow staged — each stage reads the previous stage's output. Re-run from any stage; downstream is idempotent.

## Post-training flow (15_post_train.py)

After stage 4 finishes:

```bash
python E:/ultron-training/scripts/15_post_train.py --ollama-name qikfox/starscream-throne-7b:latest
```

The script polls for the adapter at `models/starscream-throne-7b/adapter_model.safetensors`, waits for the training process to exit, then runs stages 5 + 6, re-enables the watchdog, restarts Ollama, and copies the new GGUF over `D:\ai\models\Qwen2.5-7B-Instruct.Q4_K_M.gguf` (backing up the old one as `.bak`) so Heretik picks it up on next start.

**Don't run this from `terminal()`** — it polls for ~3.5 hours. Run via `execute_code` + `subprocess.Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, stdin=DEVNULL)` so it outlives the bash shell.

## Procedure

### 1. Pick the corpus roots

`01_harvest.py` ships with these sources on THRONE:

| Root | Kind label | Default exts | Notes |
|---|---|---|---|
| `C:\Users\KING\Projects\TESSERACT` | tesseract_code | md/txt/py/json/yaml/yml/toml/ps1/sh/cmd | Code + memos |
| `C:\Users\KING\Projects\TESSERACT\memory` | tesseract_memos | (same) | Working memory |
| `C:\Users\KING\Projects\ULTRON` | ultron_code | (same) | Operator code |
| `C:\Users\KING\Documents\alchemy` | alchemy_opus | (same) | HITCHYZ OPUS + corpus |
| `C:\Users\KING\AppData\Local\hermes\memories` | hermes_memory | (same) | MEMORY.md, USER.md |
| `E:\ultron-memory\nexus-core` | nexus_core | (same) | Notes, RAG |
| `E:\ultron-memory\docs` | stack_inventory | (same) | Stack inventory |
| `E:\ultron-memory\self-evolution` | self_evolution | (same) | Run logs, skills |
| `E:\ultron-memory\obsidian` | obsidian | (same) | Linked notes |
| `C:\Users\KING\Documents\unsloth_data` | ultron_sft_data | (same) | **Purpose-built SFT persona docs — highest impact per byte** |
| `C:\Users\KING\Documents\Obsidian Vault` | obsidian_vault | (same) | Real notes (LLM Memory Index, Dashboard) |
| `C:\Users\KING\Documents\2nd brain` | second_brain | (same) | Mostly Obsidian config |
| `C:\Users\KING\Documents\KnowledgeVault` | knowledge_vault | (same) | Journal entries |
| `C:\Users\KING\Documents\Claude` | claude_skills | (same) | SKILL.md files |
| `C:\Users\KING\Documents\Codex` | codex_sessions | **md/json/ps1/cmd/txt + ts/tsx/js/jsx/mjs/cjs/mts/cts/css/html/yml/yaml/toml** | User-written Codex CLI session code; skip node_modules tree |
| `C:\Users\KING\Documents\PowerShell` | powershell_scripts | (same) | Scripts + lessons |

**Per-source ext overrides.** Sources carry their own extension list because the kind of signal differs: `unsloth_data` is `.txt`-only persona docs; `codex_sessions` needs `.ts/.tsx/.js` for the user's CLI session code; the rest are markdown-heavy. A single global EXTS list can't model this.

Skip folders: `.git .venv __pycache__ node_modules .pytest_cache dist build .next scratch backups .openai .sites-runtime .copilot .obsidian .husky .github .vscode`. The app-cache folders (`.openai`, `.copilot`, `.obsidian`, `.sites-runtime`) contain model catalogs and UI state, not signal; `.claudian` is KEEP'd because it can hold conversation fragments. Skip extensions: `*.png *.jpg *.jpeg *.gif *.pdf *.zip *.lock *.log`. Skip files: `package-lock.json`, `yarn.lock`. Max per-file: 200–500 KB depending on source.

### 2. Run harvest → clean → format

```bash
python E:/ultron-training/scripts/01_harvest.py
python E:/ultron-training/scripts/02_clean.py
python E:/ultron-training/scripts/03_format.py
```

Expected yield on a populated THRONE: ~3,000 raw files → ~2,800 cleaned → ~5,500 train/val examples (~30M tokens, ~140 MB JSONL).

### 3. Pick the base model

Default: `Qwen/Qwen2.5-7B-Instruct`. Reasoning:

- 7B QLoRA on RTX 3090 fits comfortably (~10-12 GB VRAM during training). 13B/26B is marginal.
- Same chat-template family as Starscream (Qwen vs Gemma chat templates differ — adjust `06_export_gguf.py` if switching).
- Once a 7B LoRA works, the recipe transfers to a 13B QLoRA pass on the same hardware.

Override with `--base` to use a different base.

### 4. Run training

**Verify the Python environment first.** The interpreter must report `torch.cuda.is_available() == True` and have bitsandbytes + CUDA 12.x visible. Hermes' default Python frequently does not; use the training venv or explicit `python` that has the CUDA stack.

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no gpu')"
pip install -U peft transformers bitsandbytes accelerate datasets trl
python E:/ultron-training/scripts/04_train.py --dry-run   # config check
python E:/ultron-training/scripts/04_train.py             # ~2-3 hr on RTX 3090
```

Defaults: r=16, alpha=32, dropout=0.05; 4-bit NF4 base; LoRA on q/k/v/o/gate/up/down; seq_len 4096; 3 epochs cosine; effective batch 16 (1×16); LR 2e-4; warmup 3%; gradient checkpointing on; paged_adamw_8bit.

### 5. Merge + export

```bash
python E:/ultron-training/scripts/05_merge.py \
  --base Qwen/Qwen2.5-7B-Instruct \
  --adapter E:/ultron-training/models/starscream-throne-7b \
  --output E:/ultron-training/models/starscream-throne-7b-merged

python E:/ultron-training/scripts/06_export_gguf.py \
  --merged E:/ultron-training/models/starscream-throne-7b-merged \
  --gguf-out E:/ultron-training/models/starscream-throne-7b.Q4_K_M.gguf \
  --ollama-name qikfox/starscream-throne-7b:latest
```

Then add the new tag to `throne-llm-router`.

## Chat vs completion format

`03_format.py` writes both formats. Pick by training goal:

- **chat_*.jsonl**: each row is `{messages: [system, user, assistant]}`. Use for chat-tuned models. System prompt embeds the THRONE operator identity.
- **completion_*.jsonl**: each row is `{prompt: "", completion: <text>}`. Use for base models that need language-modeling first, instruction-following second.

Default split: 90/10 train/val, sha-based (first hex digit < 2 → val). Deterministic — reruns produce identical splits.

## Pitfalls

- **Do NOT pull a large model into Ollama during training.** Stop the THRONE_Watchdog auto-warm before stage 4 and re-enable after stage 6 finishes.
- **Long documents split at paragraph boundaries**, not arbitrary cut points. Raise `--max-chars` in `03_format.py` only if you want document-level training; default 8K covers >95% of examples.
- **Starscream (gemma4 26B) and Qwen chat templates differ.** If you change `--base` from Qwen to gemma4, update the chat template in `06_export_gguf.py` to use `<start_of_turn>` / `<end_of_turn>`.
- **`*.jsonl` includes a 610-char system prompt on every chat example.** That inflates token count ~10% but anchors the operator identity. If you want pure language modeling, use `completion_*.jsonl` instead.
- **Do NOT stage `.env` or credential files.** `01_harvest.py` filters by extension but does not pattern-match secrets. Add explicit `SKIP_FILE_GLOBS` if a corpus root contains credentials.
- **E:\ultron-memory\papers is 10 GB of third-party PDFs** — `01_harvest.py` skips it (no extension match). If you want to include it, run a separate OCR pass first; do not bulk-add raw PDFs.
- **CPU/RAM swap risk**: stages 1-3 are CPU-only and safe. Stage 4 (training) needs 14 GB RAM free; stage 5 (merge) needs 14 GB RAM for FP16 model load. Check RAM before each.
- **`ollama create` returns success but the Modelfile may have a broken template** if you pasted with shell escaping issues. Always probe via `ollama run <name> "ping"` after create.
- **The Codex CLI root is mostly `node_modules` noise** — 818 MB of 808 MB in a single session is third-party transpiled output. `os.walk` prunes `.git .venv __pycache__ node_modules .pytest_cache dist build .next` for free, but only if the harvest's skip-dir list actually contains them. Verify the list before assuming the harvest was fast.
- **Per-source ext lists are the right primitive** — a global `EXTS = {...}` cannot capture that `unsloth_data` is `.txt`-only persona docs while `codex_sessions` is `.ts/.tsx/.js` heavy. Source tuples should carry an optional exts override; otherwise Codex yields 15 files instead of 111.
- **Skip app-cache folders in Obsidian/Codex roots** — `.openai` and `.copilot` contain downloaded model catalogs (multi-MB JSON, no signal); `.sites-runtime` is dev-server bookkeeping; `.obsidian` is UI state. `.claudian` is the one to KEEP because it can carry conversation fragments.
- **Wipe `raw/` before re-running the harvest** — filenames are content-hashed, so reruns dedupe at the clean stage but `raw/` grows monotonically. Either delete `raw/*` or rebuild the manifest from the surviving shas. The clean step is idempotent; the harvest is not.
- **Python triple-quoted string with `C:\Users\...` triggers `\U` unicode-escape error** — `'unicodeescape' codec can't decode bytes ... truncated \UXXXXXXXX escape`. Use a raw string (`r"""..."""`) or escape backslashes (`"C:\\Users\\..."`). Applies to any Python literal that embeds Windows paths.
- **When `terminal()` is git-bash, do NOT pass PowerShell with `$_` and `${_.X}` inline** — bash expands `$_` and treats `.X` as a file suffix, mangling the script. Write PS to a `.ps1` file and invoke with `powershell -NoProfile -ExecutionPolicy Bypass -File "..."`.
- **Treat `C:\Users\KING\Documents\` as a top-level corpus root, not as a side folder.** It contains `unsloth_data/` (purpose-built SFT data), `Obsidian Vault/`, `Codex/` (CLI session workspaces), `PowerShell/`, `KnowledgeVault/`, `Claude/` (SKILL.md), and several others. An audit pass before adding sources will surface sources the original harvest missed.
- **`MEMORY.md` is a working buffer, not a durable log** — between sessions the runtime may regenerate it from canonical sources and drop appended entries. Treat anything you append as ephemeral unless the same fact is also captured in a skill or in the chat message that needs it.
- **`ollama ps` shows `size_vram` vs total `size`** — when `size_vram << size`, the model is partially offloaded to CPU/RAM. Cause is usually num_ctx too large for available VRAM after the 4-bit base + KV cache. Reduce `num_ctx` and reload.

## Improving dataset quality

**Audit the corpus roots before training.** Before the first training run, walk `C:\Users\KING\Documents\` and `E:\` with `Get-ChildItem -Directory` and check the size of each subfolder. Sources the original pipeline missed (this session surfaced `unsloth_data/`, `Obsidian Vault/`, `Codex/`, `PowerShell/`) often have high signal because the user already curated them — they didn't end up in `Projects\` because they're personal scratch, not project code. **`Documents\`-tier corpora should be considered first-class training roots**, not side folders.

**`unsloth_data/` is the highest-impact source per byte** — purpose-built SFT persona docs the user already wrote (manifest, system profile, projects, tools, persona playbook, workflows, private corpus). Even at 35 files / 0.3 MB it dominates training signal vs 1,946 nexus-core files. Don't down-weight or deprioritize small `unsloth_data`-style sources in the corpus mix.

Before training, audit the cleaned corpus for noise:

1. **Run `ollama-launch` over `chat_train.jsonl`** with Starscream as judge; ask "is this a high-quality example for fine-tuning a THRONE operator model?" Filter or rewrite low-quality rows.
2. **Teacher distillation**: for every clean record, generate a target response from Starscream-64k, mix the model output with the original at a 1:1 ratio. ~3-5× quality uplift at the same parameter count.
3. **DPO/ORPO preference data**: collect thumbs-up/down from past sessions where the user corrected agent output → preference dataset → DPO pass after SFT.
4. **Per-task specialists**: `starscream-throne-code` (code-only), `starscream-throne-ops` (sysadmin-only), `starscream-throne-alchemy` (HITCHYZ-trained). Each gets a focused dataset slice.

## References

- `references/curriculum.md` — domain-specific dataset slices and how to weight them
- `references/corpus-audit-procedure.md` — how to enumerate training roots on a Windows machine before designing the harvest
- `templates/Modelfile.template` — known-good Ollama Modelfile with operator system prompt
- `scripts/probe_trained_model.py` — post-training sanity probe (use after `ollama create`)

## Verification

After stage 6 (Ollama import), the trained model must pass:

```bash
ollama run qikfox/starscream-throne-7b:latest "List three services I might run on a Windows machine called THRONE."
```

Expected: response names services the user actually uses (Ollama, Tailnet, etc.), uses the operator system prompt voice, completes in <30 s. If it defaults to generic LLM-help-desk tone, the LoRA didn't take — check `04_train.py` loss curve, verify the adapter was saved, verify merge produced a non-zero adapter delta.
