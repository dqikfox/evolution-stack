---
name: flash-attn-windows-cuda13
description: Why flash-attn2 wheel fails on Windows + CUDA 13.3 RTX 3090.
---

# flash-attn on Windows + CUDA 13.3

`pip install flash-attn` fails to build on Windows + CUDA 13.3 + RTX 3090.

## The error

```
× Failed to build installable wheels for some pyproject.toml based projects
╰─> flash-attn
```

## Why

- flash-attn2 upstream ships prebuilt wheels for Linux + CUDA 11/12 only.
- Windows wheel builds require a CUDA toolkit + MSVC toolchain + ninja, plus a compatible PyTorch + CUDA runtime.
- CUDA 13.3 (released late 2025) is newer than what flash-attn2 upstream tests against, so the build script fails to find a matching `cublasLt`/`cudnn` header set.

## The fix (for THRONE today)

Don't bother installing flash-attn. Use `attn_implementation="sdpa"` in `from_pretrained()`. PyTorch 2.14's SDPA backend on RTX 3090 is good enough — ~2× slower than flash-attn2 but trains correctly.

```python
model = AutoModelForCausalLM.from_pretrained(
    args.base,
    quantization_config=bnb,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
    attn_implementation="sdpa",
)
```

## When flash-attn works again

Watch these for Windows-compatible flash-attn builds:
1. https://github.com/Dao-AILab/flash-attention/releases — official releases; rarely ship Windows wheels.
2. https://github.com/kingdy2002/flash-attention-windows — community Windows port.
3. vLLM-flash-attn3 package (used by trl when `attn_implementation="kernels-community/vllm-flash-attn3"`).

Until then, SDPA is the path.

## Pitfalls

- `padding-free training` (trl flag) emits a warning when not using flash-attn. It's still correct, just slower.
- `packing=True` + SDPA can cross-contaminate attention between packed samples. The trl warning says so. If training loss looks weird, set `packing=False` and accept the slower training.
- `attn_implementation="eager"` is the slowest fallback — only use it to debug.
