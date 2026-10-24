# Stop Token Traps & Template Endings

## The Stop-Token-Matches-Template-Start Bug

**Problem**: When `PARAMETER stop` matches a token that the model naturally generates as its FIRST token (because the template left an open turn), the model halts immediately with zero output.

### Qwen3.5 broken pattern (causes empty responses)

```modelfile
TEMPLATE """...<|im_start|>assistant
{{ .Content }}
"""
PARAMETER stop <|im_start|>
```

**Why it breaks**: The template ends with `<|im_start|>assistant` which starts an assistant turn. But `PARAMETER stop <|im_start|>` means "stop when you generate `<|im_start|>`". The model's first token is `<|im_start|>` (to continue the assistant turn), so it stops immediately.

### Qwen3.5 corrected pattern

```modelfile
TEMPLATE """...<|im_start|>assistant
{{ .Content }}
<|im_end|>
"""
PARAMETER stop <|im_end|>
```

**Why it works**: The template now includes the closing `<|im_end|>`. The stop token is `</code></pre>` which the model generates at the END of its response, not the beginning.

## num_ctx vs VRAM for Large Models

**Rule of thumb**: Context window costs VRAM linearly.

| Model size | Quant | num_ctx 8192 | num_ctx 32768 | num_ctx 128000 |
|---|---|---|---|---|
| 7B | Q4_K_M | ~5 GB | ~7 GB | ~14 GB |
| 21B (Qwen MoE) | Q4_K_M | ~12 GB | ~16 GB | **OOM on 24GB** |
| 70B | Q4_K_M | ~40 GB | OOM | OOM |

**Fix for megatron (21B Qwen MoE on RTX 3090 24GB)**:
- `num_ctx 8192` → fits with ~2-3 GB headroom
- `num_ctx 128000` → OOM, model returns empty
- Check with `ollama ps` after creation — if offload shows `0% GPU`, VRAM is saturated

## Windows `ollama create` Timeout

On Windows, `ollama create` for large models (20GB+) can take 5-10 minutes. The CLI appears to hang.

**Fix**: Run in background with extended timeout:
```bash
# In Hermes terminal (background mode recommended)
ollama create <name> -f Modelfile
# OR use Python subprocess with 600s timeout
```

## Verification After Creation

```bash
# Check the model actually responds
ollama run <name> "Say hello briefly"

# Check GPU offload
curl http://localhost:11434/api/ps
```

If empty response → check `ollama logs` for OOM or re-examine stop token.

## Quick Diagnostic Checklist

1. Does `ollama show <name> --modelfile` show the expected `PARAMETER stop`?
2. Does the template END with an open assistant turn? (If yes + stop matches start token = broken)
3. Does `ollama ps` show GPU offload > 0%?
4. Does a simple "Say hello" test return text?
5. Is `num_ctx` small enough for available VRAM?
