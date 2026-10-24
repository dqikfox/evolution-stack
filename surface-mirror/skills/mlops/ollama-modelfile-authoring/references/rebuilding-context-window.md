# Rebuilding Ollama Model Context Window (Zero Storage Cost)

## The Pattern

When an Ollama model was created with a wrong `num_ctx` (e.g., 8192 instead of 65536), you can fix it without re-downloading anything — the GGUF blob is reused, only the config layer changes.

## Pitfalls

### Circular FROM Trap
`ollama create <name> -f Modelfile` where the Modelfile's `FROM` references the SAME model name being created fails with:
```
400 Bad Request: unknown type
```
The FROM line must reference a DIFFERENT model name or a raw blob hash.

### Raw Blob Hash FROM Also Fails
```
FROM sha256:1c9fddff1f446b917aadacb1ca9eecbd0177562d09959fa6ba59f8a54fd707dc
```
Produces the same `unknown type` error. FROM must be an Ollama model name.

## Correct Workflow

1. Copy source to temp:
```bash
ollama cp megatron-fixed:latest megatron-fixed-tmp:latest
```

2. Write Modelfile with FROM pointing to temp:
```dockerfile
FROM megatron-fixed-tmp:latest
PARAMETER num_ctx 65536
PARAMETER num_predict -1
PARAMETER repeat_penalty 1.18
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"
PARAMETER temperature 0.35
PARAMETER top_k 35
PARAMETER min_p 0.05
PARAMETER presence_penalty 0
PARAMETER repeat_last_n 128
PARAMETER top_p 0.82
PARAMETER frequency_penalty 0
```

3. Build:
```bash
ollama create megatron-fixed-tmp -f Modelfile-fix
```

4. Verify:
```bash
curl -s http://localhost:11434/api/show -d '{"name":"megatron-fixed-tmp:latest"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(l.strip()) for l in d.get('parameters','').split(chr(10)) if 'num_ctx' in l]"
# Should output: num_ctx 65536
```

5. Swap:
```bash
ollama rm megatron-fixed:latest
ollama cp megatron-fixed-tmp:latest megatron-fixed:latest
ollama rm megatron-fixed-tmp:latest
```

Storage impact: < 1KB (only the config layer changes). Verify blob digest matches:
```bash
ollama show megatron-fixed:latest | grep -E "^[a-f0-9]{64}"
```

## Ollama Env Vars vs Modelfile Parameters

The Modelfile `PARAMETER num_ctx` overrides the `OLLAMA_CONTEXT_LENGTH` env var. Always check the actual loaded model params:
```bash
curl -s http://localhost:11434/api/show -d '{"name":"<model>:latest"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(l.strip()) for l in d.get('parameters','').split(chr(10)) if 'num_ctx' in l]"
```
If empty output, the model inherits env var defaults.
