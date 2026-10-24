# Modelfile Examples

Working templates from verified sessions.

## Qwen3.5 MoE (35B, 256 experts)

```modelfile
FROM C:\\Users\\KING\\.cache\\huggingface\\hub\\models--oyildirim--CyberStrike-OffSec-35B-GGUF\\blobs\\<sha256>

TEMPLATE """{{- if .Tools }}
{{- range .Tools }}
<|im_start|>system
# Tools

You have access to the following functions:

<tools>
{{ . }}
</tools>

If you choose to call a function ONLY reply in the following format with NO suffix:

<tool_call>
<function=example_function_name>
<parameter=example_parameter_1>
value_1
</parameter>
<parameter=example_parameter_2>
This is the value for the second parameter
that can span
multiple lines
</parameter>
</function>
</tool_call>

<IMPORTANT>
Reminder:
- Function calls MUST follow the specified format
- Required parameters MUST be specified
- Provide optional reasoning BEFORE the function call, but NOT after
- If no function call available, answer normally
</IMPORTANT>
{{- end }}
{{- if .System }}
{{ .System }}
{{- end }}
<|im_end|>
{{- else }}
{{- if .System }}
<|im_start|>system
{{ .System }}<|im_end|>
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
{{- if .ToolCalls }}
{{- range .ToolCalls }}
<tool_call>
<function={{ .Function.Name }}>
{{- range .Function.Arguments }}
<parameter={{ .Key }}>
{{ .Value }}
</parameter>
{{- end }}
</function>
</tool_call>
{{- end }}
{{- end }}
<|im_end|>
{{- else if eq .Role "tool" }}
<|im_start|>user
<tool_response>
{{ .Content }}</tool_response><|im_end|>
{{- end }}
{{- end }}
<|im_start|>assistant
<think>
"""

SYSTEM """You are Megatron, an elite Network and Systems Administrator AI..."""

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
PARAMETER stop <|endoftext|>
PARAMETER stop <|im_start|>
```

## Gemma 4 (26B A4B)

```modelfile
FROM Agen/gemma-4-26B-A4B-it-uncensored-heretic:latest

TEMPLATE """{{- if .Tools }}
{{- range .Tools }}
<start_of_turn>user
# Tools
...
<end_of_turn>
{{- end }}
{{- if .System }}
{{ .System }}
{{- end }}
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}
<start_of_turn>user
{{ .Content }}<end_of_turn>
{{- else if eq .Role "assistant" }}
<start_of_turn>model
{{- if .Thinking }}
<thinking>
{{ .Thinking }}
</thinking>

{{ end }}
{{ .Content }}
{{- if .ToolCalls }}...
{{- end }}
<end_of_turn>
{{- else if eq .Role "tool" }}
<start_of_turn>user
<tool_response>
{{ .Content }}</tool_response><end_of_turn>
{{- end }}
{{- end }}
<start_of_turn>model
"""

SYSTEM """You are Starscream, an elite Network and Systems Administrator AI..."""

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
PARAMETER stop <end_of_turn>
PARAMETER stop <end_of_turn>user
PARAMETER stop <end_of_turn>model
```

## Llama 3.x

```modelfile
FROM llama3.1:latest

TEMPLATE """{{- if .System }}<|start_header_id|>system<|end_header_id|>
{{ .System }}<|eot_id|>{{- end }}
{{- range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>
{{ .Content }}<|eot_id|>{{- end }}
<|start_header_id|>assistant<|end_header_id|>
"""
```
