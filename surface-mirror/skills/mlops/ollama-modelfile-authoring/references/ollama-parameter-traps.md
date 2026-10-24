# Ollama Parameter Traps

Parameters that **work in llama.cpp but are REJECTED by Ollama's Modelfile parser**.

## Rejected Parameters

| Parameter | llama.cpp | Ollama | Notes |
|---|---|---|---|
| `tfs_z` | ✅ Native | ❌ Rejected | Tail Free Sampling z-parameter |
| `typical_p` | ✅ Native | ❌ Rejected | Typical sampling p-parameter |
| `mirostat_tau` | ✅ Native | ❌ Rejected | Mirostat target entropy |
| `mirostat_eta` | ✅ Native | ❌ Rejected | Mirostat learning rate |
| `penalize_nl` | ✅ Native | ❌ Rejected | Penalize newline tokens |
| `presence_penalty` | ⚠️ Partial | ⚠️ Ignored | Ollama parses but may not apply correctly |
| `frequency_penalty` | ⚠️ Partial | ⚠️ Ignored | Same as above |

## Error Messages

```
Error: unknown parameter 'tfs_z'
Error: unknown parameter 'typical_p'
Error: unknown parameter 'mirostat_tau'
```

## Safe Alternatives

If you need the behavior of a rejected parameter, use these Ollama-native equivalents:

| Goal | Rejected | Safe Alternative |
|---|---|---|
| Reduce repetition | `mirostat_tau` + `mirostat_eta` | `repeat_penalty 1.15-1.20` + `repeat_last_n 128` |
| Tail-free sampling | `tfs_z` | `top_p 0.82` + `min_p 0.05` |
| Typical sampling | `typical_p` | `top_p 0.85` + `temperature 0.4` |
| Control newline frequency | `penalize_nl` | `repeat_penalty` (affects all repeated tokens) |

## Verified Working Parameters

```modelfile
PARAMETER temperature 0.35
PARAMETER top_p 0.82
PARAMETER top_k 35
PARAMETER repeat_penalty 1.18
PARAMETER repeat_last_n 128
PARAMETER num_ctx 16384
PARAMETER num_predict -1
PARAMETER min_p 0.05
PARAMETER presence_penalty 0.0
PARAMETER frequency_penalty 0.0
PARAMETER mirostat 0
PARAMETER stop <|im_end|>
PARAMETER seed 0
```

## Per-Model Notes

### Qwen MoE (CyberStrike, Qwen3.5, etc.)
- `repeat_penalty` is **critical** — MoE routing can loop on the same expert
- `num_ctx 16384` is safe for RTX 3090 24GB with Q4_K_M
- `num_ctx 32768` may cause CPU offload due to KV cache size

### Gemma 4
- `mirostat` is not well-supported; use `temperature` + `top_p` instead
- `repeat_penalty` should be lower (~1.05-1.10) due to Gemma's already-low repetition

### Llama 3.x
- `temperature 0.6-0.7` is Meta's recommended default for Llama 3.1 Instruct
- `top_p 0.9` works well with the Instruct format
