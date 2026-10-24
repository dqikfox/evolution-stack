# Windows Model Creation Pitfalls

Session-derived fixes for Ollama model creation on Windows.

## `invalid model name` (Ollama ≥0.32.13 on Windows)

**Symptom:**
```
Error: 400 Bad Request: invalid model name
```
...even for simple names like `megatron`, `test123`, `megatronlocal`.

**Root cause:** Running `ollama create` from a directory other than `~/.ollama/models/` causes the name parser to fail on Windows builds.

**Fix:**
```bash
# WRONG — from any other directory
ollama create megatron -f Modelfile

# CORRECT — cd into models first, then reference Modelfile via parent path
cd ~/.ollama/models
ollama create megatron -f ../Modelfile
```

## `unknown parameter` errors

Ollama 0.32.13 rejects these llama.cpp-native parameters:
- `tfs_z`
- `typical_p`
- `mirostat_tau`
- `mirostat_eta`

`mirostat 0` is deprecated (emits warning) but still accepted.

**Fix:** Remove the rejected lines from Modelfile before `ollama create`.

## Context length sizing

Default `num_ctx 16384` is conservative. This user requires `num_ctx 128000`.

**Verified working:** RTX 3090 24GB + Q4_K_M 35B MoE + `num_ctx 128000` loads successfully and responds correctly.

**Rule of thumb for VRAM headroom:**
| GPU VRAM | Model Size | Quant | Safe num_ctx |
|---|---|---|---|
| 24GB | 35B | Q4_K_M | 128K |
| 24GB | 35B | Q6_K | 32K |
| 4GB | 4B | Q4_K_M | 16K |
| 4GB | 26B | Q4_K_M | 8K (will CPU offload) |

Do not use conservative defaults when the user has explicitly stated a context requirement.

## Registry push workflow

After successful `ollama create`:
```bash
ollama cp megatron qikfox/megatron
ollama push qikfox/megatron
```

Pushing 17-21GB takes ~1 hour on typical upload speeds. Run in background.
