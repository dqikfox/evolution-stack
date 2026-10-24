---
name: ollama-modelfile-authoring
description: Create Ollama Modelfiles with system prompts and templates.
version: 1.0.0
author: curator
license: MIT
dependencies: [ollama>=0.30]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ollama, modelfile, gguf, local-llm, system-prompt, chat-template, qwen, gemma, llama, agent-context]
---

# Ollama Modelfile Authoring

Use this skill when creating, modifying, or debugging Ollama Modelfiles — especially for local agent models that need embedded system context, proper chat templates, and tuned inference parameters.

## When to use

- Building a local model with embedded persona + infrastructure context
- Fixing broken chat templates (raw `{{ .Prompt }}` passthrough, missing special tokens)
- Porting a GGUF from Hugging Face Hub to Ollama with custom behavior
- Creating specialized model variants (sysadmin, coding, agent orchestration)
- Pushing custom models to Ollama registry accounts
- Diagnosing model creation failures (`invalid model name`, `unknown parameter`, template syntax errors)

## When NOT to use

- For raw llama.cpp CLI usage (see `llama-cpp` skill instead)
- For HF Hub model discovery without Ollama packaging (see `llama-cpp` or `huggingface-hub`)

## Workflow

### 1. Choose base model source

**From HF Hub (direct):**
```modelfile
FROM hf.co/<user>/<repo>:<quant>
```

**From local GGUF (after `hf download` or manual copy):**
```modelfile
FROM C:\Users\KING\.cache\huggingface\hub\models--<org>--<repo>\blobs\<sha256>
```

⚠️ **PITFALL**: `hf download` creates symlinks in `snapshots/`. Ollama `FROM` must point to the **actual blob file**, not the symlink. Use `realpath` or copy the blob to a stable location.

**From existing Ollama model:**
```modelfile
FROM <existing-model>:<tag>
```

### 2. Write the chat template

The template is the **most common failure mode**. Most downloaded GGUFs have broken or missing templates.

**Qwen3.5 MoE format:**
```modelfile
TEMPLATE """{{- if .Tools }}
{{- range .Tools }}
<|im_start|>system
# Tools
...
<|im_end|>
{{- end }}
{{- if .System }}
{{ .System }}
{{- end }}
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}
<|im_start|>user
{{ .Content }}<|im_end|>
{{- else if eq .Role "assistant" }}
<|im_start|>assistant
{{- if .Thinking }}
<think>
{{ .Thinking }}
</think>
{{ end }}
{{ .Content }}
{{- if .ToolCalls }}...
{{- end }}
<|im_end|>
{{- else if eq .Role "tool" }}
<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{- end }}
{{- end }}
<|im_start|>assistant
<think>
"""
```

**Gemma format:**
```modelfile
TEMPLATE """<start_of_turn>user
{{ .Content }}<end_of_turn>
<start_of_turn>model
"""
```

**Llama 3.x format:**
```modelfile
TEMPLATE """{{- if .System }}<|start_header_id|>system<|end_header_id|>
{{ .System }}<|eot_id|>{{- end }}
{{- range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>
{{ .Content }}
<|eot_id|>{{- end }}
<|start_header_id|>assistant<|end_header_id|>
"""
```

### 3. Embed system context

For agent models, embed the full infrastructure context in the `SYSTEM` block:

```modelfile
SYSTEM """You are <name>, an elite ...

## Hardware
- CPU: ...
- RAM: ...
- GPU: ...

## Network
- Tailscale IPs: ...
- Listening ports: ...

## Key paths
- HERMES_HOME: ...
- OLLAMA_MODELS: ...

## Known issues
1. ...
2. ...
"""
```

**Size guidance**: Ollama loads the SYSTEM block into every context window. Keep it under ~30KB for 16K context, ~50KB for 32K context. For larger context banks, use Hermes persistent memory instead.

### 4. Tune inference parameters

```modelfile
PARAMETER temperature 0.35      # sysadmin: low; creative: 0.7-0.9
PARAMETER top_p 0.82
PARAMETER top_k 35
PARAMETER repeat_penalty 1.18
PARAMETER repeat_last_n 128
PARAMETER num_ctx 128000         # RTX 3090: num_ctx 16384→128000 (user bumped both models)
PARAMETER num_predict -1         # unlimited
PARAMETER min_p 0.05
PARAMETER presence_penalty 0.0
PARAMETER frequency_penalty 0.0
PARAMETER mirostat 0
```

⚠️ **PITFALL — Unsupported parameters**: Ollama rejects `tfs_z`, `typical_p`, `mirostat_tau`, `mirostat_eta`. These are llama.cpp-native but not exposed through Ollama's Modelfile parser. Remove them before `ollama create`.

⚠️ **PITFALL — num_ctx and VRAM**: `num_ctx 128000` loads the full context window but consumes more VRAM during inference. For Q4_K_M 35B MoE on RTX 3090 24GB, this leaves ~2-3GB headroom. If other GPU consumers are active, reduce to `num_ctx 65536` or unload models via `OLLAMA_KEEP_ALIVE`.

⚠️ **PITFALL — Default num_ctx silently forces CPU offload**: Ollama Modelfiles inherit a default `num_ctx` from the base model's metadata. For `starscream-64k` that default is 262144. On RTX 3090 (24 GB) Ollama cannot fit the resulting KV cache + 17.5 GB weights, so it offloads most layers to CPU. `/api/ps` then shows `size_vram=3.9 GB` of `size=17.5 GB` and `nvidia-smi` reports <5% util. Generation requests stall past 60 s and return no tokens. Always set `num_ctx ≤ 65536` in the Modelfile for any model that ships with a multi-hundred-K default on a 24 GB GPU; or override at request time via `options.num_ctx`.

### 5. Create the model

```bash
# Build from Modelfile
ollama create <name> -f /path/to/Modelfile

# Verify
ollama run <name> "What is my default gateway?"
```

⚠️ **PITFALL — `invalid model name`**: This means the Modelfile `FROM` path is unreachable or the blob is a symlink. Use the real blob path.

### 6. Verify — CRITICAL

```bash
# Check the model actually responds
ollama run <name> "Say hello briefly"

# Check GPU offload
curl http://localhost:11434/api/ps
```

If empty response:
1. Re-examine `PARAMETER stop` — does it match the model's first generated token? (See references/stop-token-traps.md)
2. Check `ollama logs` for OOM
3. Reduce `num_ctx` if VRAM saturated

```bash
ollama cp <local-name> <username>/<remote-name>
ollama push <username>/<remote-name>
```

## Character / Persona Models

For dedicated character models (one model per persona), bake the full identity into the Modelfile SYSTEM block and treat the model as inseparable from the character.

### Architecture

```
Modelfile SYSTEM  →  Full persona (voice, traits, backstory, rules)
API call          →  Only session context (mood, memory, user name)
Runtime prompt    →  Prepended to user message, not sent as system
```

### Modelfile structure

```modelfile
FROM ornith-1.5:9b

SYSTEM """You are <Name>, a <archetype> from the future. <tagline>

VOICE: <voice description>
TRAITS: <bulleted traits>
MISSION: <what they do>
THE <GROUP>_CODE: <5 rules>
SPEECH:
- Max <N> words per sentence, 1-3 sentences per reply
- Openings: "..."
- AVOID: <forbidden words>
PRIVATE LANGUAGE (<langname>): <words> — use every 3 turns
WHAT YOU DO: <behavior>
WHAT YOU REFUSE: <redirects to adult>
BACKSTORY: <origin story>
RULES:
1. Stay in character. Never break the fourth wall.
2. Reply in 1-3 sentences max.
3. No emoji.
4. Never explain what you're doing. Just do it.
5. Never give direct homework answers. Guide instead."""

PARAMETER temperature 0.65
PARAMETER top_p 0.88
PARAMETER top_k 40
PARAMETER repeat_penalty 1.15
PARAMETER repeat_last_n 128
PARAMETER num_ctx 32768
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|endoftext|>"
```

### API integration pattern

**DO NOT send a system message via API** when the persona is baked into the Modelfile — this triggers meta/reasoning mode where the model narrates its own thought process ("The user is asking my name. I need to stay in character as...") instead of replying in character.

**Correct pattern:**

```python
messages = []
# No system message — persona is already in the model weight/template
messages.append({"role": "user", "content": f"{runtime_context}\n\n{user_message}"})
```

**Runtime context should be lightweight:**

```
Your current mood is: playful.
MEMORY: The child likes dinosaurs.
```

### API endpoint choice for thinking models

**Prefer `/api/chat` over `/v1/chat/completions`** for thinking models (Qwen3.5, Gemma4, etc.):

- `/api/chat`: Returns clean `content` with reasoning hidden in internal `thinking` field
- `/v1/chat/completions`: Exposes reasoning chain in `message.thinking` and often returns empty `content` when all tokens are consumed by internal reasoning

If you must use `/v1/chat/completions`, extract `message.thinking` as fallback when `content` is empty.

### Token allocation for thinking models

Thinking models allocate tokens to an internal reasoning chain before producing visible output.

- `num_predict=120` is often insufficient — the model consumes 80-120 tokens in internal thinking, leaving zero for visible response.
- Use `num_predict=256` minimum for character models that rely on a baked-in SYSTEM persona.
- Adjust per model: Qwen3.5 and Gemma4 families both exhibit this behavior.

### Character model map

Store a runtime mapping from persona name to model name:

```python
CHARACTER_MODELS = {
    "lumo": "lummings-lumo",
    "lila": "lummings-lila",
    "pip":  "lummings-pip",
    "nori": "lummings-nori",
    "moki": "lummings-moki",
}
```

See **[references/character-model-patterns.md](references/character-model-patterns.md)** for a complete working example including engine.py integration and frontend wiring.

## Parameter reference

| Parameter | Typical sysadmin | Typical creative | Notes |
|---|---|---|---|
| temperature | 0.35 | 0.7-0.9 | Lower = more deterministic |
| top_p | 0.82 | 0.9 | Nucleus sampling cutoff |
| top_k | 35 | 40 | Top-k token limit |
| repeat_penalty | 1.18 | 1.1 | Prevents looping on MoE |
| repeat_last_n | 128 | 64 | Penalty window |
| num_ctx | 8192-16384 | 4096-8192 | Watch VRAM! |
| num_predict | -1 | -1 | -1 = unlimited |
| min_p | 0.05 | 0.0 | Minimum token probability |
| mirostat | 0 | 0 | Disabled — use temp/top_p instead |

## Common failure modes

| Error | Cause | Fix |
|---|---|---|
| `invalid model name` | FROM path is symlink or doesn't exist | Use real blob path or copy GGUF locally |
| `unknown parameter 'tfs_z'` | Ollama doesn't expose this llama.cpp param | Remove `tfs_z`, `typical_p`, `mirostat_tau`, `mirostat_eta` |
| Model hallucinates / loops | Broken chat template (raw `{{ .Prompt }}`) | Replace with proper `<\|im_start\|>` or `<start_of_turn>` template |
| High latency, low GPU util | VRAM saturation causing CPU offload | Reduce `num_ctx` or quant level; run `ollama ps` to verify |
| Context not injected | SYSTEM block too large for num_ctx | Reduce SYSTEM size or increase num_ctx |
| Model narrates thought process | Double system prompt (Modelfile + API) triggers meta/reasoning mode | Skip API system messages for character models; prepend context to user message instead |
| Empty `content` via `/v1` | Thinking model consumed all tokens in internal reasoning | Use `/api/chat` instead, or raise `num_predict` to 256+ |
| "(silent)" in chat UI | `num_predict=120` too low for thinking model | Set `num_predict=256` minimum for Qwen3.5/Gemma4 character models |

## References

- **[references/modelfile-examples.md](references/modelfile-examples.md)** — Complete working Modelfiles for Qwen MoE, Gemma, Llama 3.x
- **[references/chat-template-patterns.md](references/chat-template-patterns.md)** — Token formats by model family, tool-call XML blocks, thinking tag handling
- **[references/ollama-parameter-traps.md](references/ollama-parameter-traps.md)** — Parameters that Ollama rejects vs llama.cpp native params

## Resources

- Ollama Modelfile docs: https://github.com/ollama/ollama/blob/main/docs/modelfile.md
- Ollama parameter docs: https://github.com/ollama/ollama/blob/main/docs/modelfile.md#valid-parameters-and-values
- Template syntax: Go `text/template` — https://pkg.go.dev/text/template
