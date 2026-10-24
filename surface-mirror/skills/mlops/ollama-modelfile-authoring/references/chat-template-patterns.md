# Chat Template Patterns by Model Family

## Qwen3.5 (incl. MoE variants)

**Tokens:** `<|im_start|>`, `<|im_end|>`, `<|endoftext|>`
**Roles:** system, user, assistant, tool
**Tool format:** XML `<tool_call>` / `<tool_response>` blocks
**Thinking:** `<think>` / `</think>` tags (renders as collapsible reasoning)

```
<|im_start|>system
{{ .System }}<|im_end|>
<|im_start|>user
{{ .Content }}<|im_end|>
<|im_start|>assistant
{{ .Content }}<|im_end|>
```

## Gemma 4

**Tokens:** `<start_of_turn>`, `<end_of_turn>`
**Roles:** user, model (not "assistant")
**No native tool format** — embed tools in SYSTEM prompt
**Thinking:** `<thinking>` / `</thinking>` tags

```
<start_of_turn>user
{{ .Content }}<end_of_turn>
<start_of_turn>model
{{ .Content }}<end_of_turn>
```

## Llama 3.x / 3.1 / 3.2

**Tokens:** `<|start_header_id|>`, `<|end_header_id|>`, `<|eot_id|>`
**Roles:** system, user, assistant
**Tool format:** Native via `tools` field in messages (OpenAI-compatible)
**No explicit thinking tags** — reasoning in plain text

```
<|start_header_id|>system<|end_header_id|>
{{ .System }}<|eot_id|>
<|start_header_id|>user<|end_header_id|>
{{ .Content }}<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
```

## Mistral / Mixtral

**Tokens:** `</s>` (end of sequence), `[INST]`, `[/INST]`
**No system role** — prepend system prompt to first user message

```
[INST] {{ .System }}

{{ .Content }} [/INST]
{{ .Response }}
</s>
```

## Tool Call XML Block (universal pattern)

For models without native tool support, embed this in SYSTEM:

```
If you choose to call a function, reply ONLY in this format:

<tool_call>
<function=FUNCTION_NAME>
<parameter=PARAM1>value1</parameter>
</parameter=PARAM2>value2</parameter>
</function>
</tool_call>
```

## Thinking Tag Handling

Models that support reasoning blocks:

| Model | Open tag | Close tag | Notes |
|---|---|---|---|
| Qwen3.5 MoE | `<think>` | `</think>` | Renders as collapsible in most UIs |
| Gemma 4 | `<thinking>` | `</thinking>` | May affect token counting |
| DeepSeek R1 | `<think>` | `</think>` | Native chain-of-thought |

When the user asks to strip reasoning from output, remove the entire block including tags.
