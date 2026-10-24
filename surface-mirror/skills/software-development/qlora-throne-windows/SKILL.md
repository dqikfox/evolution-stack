---
name: qlora-throne-windows
description: QLoRA SFT on THRONE Windows RTX 3090 CUDA 13.3.
---

# QLoRA SFT on THRONE (Windows / RTX 3090 / CUDA 13.3)

End-to-end recipe for fine-tuning a 7B model with QLoRA on the user's Windows box.

## Install

CUDA torch wheel required (the default pip install pulls CPU-only):

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cu130 torch torchvision
python -m pip install -U transformers peft trl bitsandbytes accelerate datasets
```

Verify CUDA + 24 GB GPU: `python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`.

## VRAM etiquette

- One model resident at a time on RTX 3090 24 GB.
- Before training: `Get-Process ollama,llama-server | Stop-Process -Force`.
- Disable THRONE_Watchdog_5min cron so it doesn't auto-restart Ollama:
  `Get-ScheduledTask THRONE_Watchdog_5min | Disable-ScheduledTask`.
- Expected VRAM during training: 14 GB (Qwen 7B 4-bit + LoRA + activations + grad checkpoint).

## API changes (transformers 5.17 + trl 1.14)

`warmup_ratio` removed; use `warmup_steps` (compute from epochs × train_size / batch).

```python
total_steps = (args.epochs * len(train_ds)) // (args.batch_size * args.grad_accum)
warmup_steps = max(1, int(total_steps * 0.03))
targs = TrainingArguments(..., warmup_steps=warmup_steps)
```

`SFTTrainer(tokenizer=...)` is deprecated; use `processing_class`.

`dataset_text_field`, `packing`, `max_seq_length` moved out of `SFTTrainer.__init__` into `SFTConfig`. The new name is `max_length` (not `max_seq_length`):

```python
from trl import SFTConfig, SFTTrainer
sft_kwargs = dict(targs.to_dict())
sft_kwargs.pop("max_seq_length", None)  # SFTConfig rejects this
sft_kwargs.update({"dataset_text_field":"text","max_length":2048,"packing":True,"completion_only_loss":False})
sft_cfg = SFTConfig(**sft_kwargs)
trainer = SFTTrainer(model=model, processing_class=tok, args=sft_cfg,
                    train_dataset=train_ds, eval_dataset=eval_ds)
```

## Flash attention

flash-attn2 wheels are not yet built for CUDA 13.3 on Windows RTX 3090. Use `attn_implementation="sdpa"` as fallback. SDPA is ~2× slower than flash-attn2 on long sequences.

Without flash-attn, a 7B QLoRA pass at seq_len 4096, batch 1, grad_accum 16 on 6,205 examples (388 steps × 1 epoch) takes ~104 s/step → 11 hours. Drop to seq_len 2048 → 40 s/step → 3.5 hours.

## Pitfalls

- **Training dies silently with no checkpoint** if `save_strategy="epoch"` and the run is killed before epoch end (OOM, watchdog, power loss, user kill, parent shell exit). Loss = the entire run. Default to `save_strategy="steps"` + `save_steps=25` + `save_total_limit=3` so worst-case loss is ~17 min of work. Re-verify in `TrainingArguments` AND `SFTConfig` if you use both — patches to one don't propagate.
- **`targs.to_dict()` includes `max_seq_length`** even though `TrainingArguments` accepts `max_seq_length` for backwards compat. `SFTConfig` rejects it. Strip with `.pop()` before constructing SFTConfig.
- The trainer needs `trainable params: 40,370,176 || all params: 7,655,986,688 || trainable%: 0.5273` to confirm LoRA was applied. If you see 0 trainable params, the model wasn't passed through `get_peft_model`.
- The first step takes 2-3 min (bitsandbytes 4-bit quant + warmup); subsequent steps are normal speed.
- After SFT: disable the watchdog, restart ollama, run `05_merge.py` to merge LoRA into FP16, then `06_export_gguf.py` to make a GGUF for Ollama serving.
- **Ollama respawns after `Stop-Process`** — the Ollama desktop wrapper (`Ollama.exe`) auto-relaunches `ollama.exe`, and the `THRONE_Watchdog_5min` cron re-warms `starscream-64k` if it's not loaded. Disable the watchdog AND kill `Ollama.exe` (capital-O) before training. See `throne-windows-adaptation` for the exact sequence.
- **Multiple stale trainer processes halve throughput** — if the trainer was killed mid-run or a previous bash timeout left a zombie, a new launch shares the GPU. Always check `Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%04_train.py%'"` before starting; kill duplicates.
- **Launch detached, not via `terminal()`** — `terminal()` is a child of bash; when bash times out (420 s default) or exits, your trainer dies. Use `subprocess.Popen` with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` and `stdin=DEVNULL` so the trainer outlives the shell that started it. See `throne-windows-adaptation`.
- **`pip install torch` pulls CPU-only** by default on Windows. Use `--index-url https://download.pytorch.org/whl/cu130` to get the CUDA 13.3 wheel that matches the system's installed CUDA runtime.
- **`torch_dtype=...` deprecation warning** in transformers 5.17 — the kwarg was renamed to `dtype=`. Pass both to suppress the warning while staying compatible with older transformers: `dtype=torch.bfloat16, torch_dtype=torch.bfloat16`. The warning is harmless but floods the log.
- **Bash heredoc + Unicode bugs patch through incorrectly** — when patching a `.sh` file that contains UTF-8 chars (e.g. `•`, `°`, `△`) inside heredocs, the `patch` tool's old_string may not match the file's actual bytes (transcoding round-trips). Fix by reading the file in `rb` mode, doing byte-level `replace`, and writing back in `wb`. The Python heredoc generator is fine; the failure is at the patch boundary.
