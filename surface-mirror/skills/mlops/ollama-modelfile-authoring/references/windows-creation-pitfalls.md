# Windows Ollama Model Creation Pitfalls

Session: 2026-08-16  
Problem: `ollama create` fails on Windows with seemingly unrelated errors.

## Error: `invalid model name`

**Root cause:** The `ollama create` command fails when run from outside the `.ollama/models/` directory on Windows. The FROM path resolution gets confused.

**Fix:** Always create from inside the models directory:

```bash
cd ~/.ollama/models && ollama create <name> -f ../Modelfile
```

Creating from the project directory or home directory produces:
```
Error: 400 Bad Request: invalid model name
```

## Error: `unknown parameter 'tfs_z'`

**Root cause:** Ollama's Modelfile parser does not expose certain llama.cpp-native parameters.

**Parameters to REMOVE:**
- `tfs_z`
- `typical_p`
- `mirostat_tau`
- `mirostat_eta`

**Keep:** `mirostat 0` (deprecated warning but non-blocking)

## Error: `FROM` path unreachable

**Root cause:** `hf download` creates symlinks in `snapshots/`. The real blob is in `blobs/`.

**Fix:** Copy the blob to a stable location:
```bash
cp ~/.cache/huggingface/hub/models--org--repo/snapshots/*/file.gguf ~/.ollama/models/base.gguf
```
Then use `FROM ./base.gguf` in the Modelfile.

## Context Size: 128K Minimum

This user requires `num_ctx 128000` minimum. The examples in the main SKILL.md show 16K as a conservative default. For this user's setup (RTX 3090 24GB, 64GB RAM), 128K is achievable with Q4_K_M quantization on 35B MoE models.
