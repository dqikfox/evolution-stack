---
name: hf-models
description: HuggingFace search/download/upload via mcp_hf_* tools.
---

# HuggingFace Ops

Use `mcp_hf_*` tools. Token from HF_TOKEN env (1Password `HF_TOKEN`).

## Quick reference
- `mcp_hf_search_models(query, limit=20, sort='downloads')` — search public models
- `mcp_hf_search_datasets(query, limit=20)` — search datasets
- `mcp_hf_model_info(repo_id)` — full metadata + siblings (files)
- `mcp_hf_list_repo_files(repo_id, revision='main')` — file tree
- `mcp_hf_download_file(repo_id, filename, revision='main')` — to HF_HOME
- `mcp_hf_whoami` — authed user info
- `mcp_hf_list_my_models(limit=50)` — your repos
- `mcp_hf_create_repo(name, repo_type='model', private=False)` — new repo

## Workflows
- **Find a GGUF**: `search_models(query="qwen2.5 7b gguf", limit=10)` → `model_info(repo_id)` → `list_repo_files(repo_id)` → `download_file(repo_id, filename='q4_k_m/...gguf')`
- **Default download dir**: `HF_HOME` env (default `~/.cache/huggingface/hub/`). THRONE convention: large durable GGUFs land in `D:\ai\models\`, not the default cache.
- **No auth required for**: search, model_info, list_repo_files, public downloads
- **Auth required for**: whoami, list_my_models, create_repo, private downloads

## Pitfalls

**1. Check D:\ai\models\ before downloading.** THRONE already has HERETICSEEK-7B-Ditill Q4_K_M (4.68GB), Mistral-7B-Instruct-v0.3 Q4_K_M (4.37GB), and Qwen2.5-7B-Instruct Q4_K_M (4.68GB) — the official Qwen quant, not bartowski. Before pulling a 4–5GB GGUF, list the directory and skip if the base quant already exists. Same model, different quantizer filenames collide silently (`Qwen2.5-7B-Instruct.Q4_K_M.gguf` vs `Qwen2.5-7B-Instruct-Q4_K_M.gguf` differ by one dash).

**2. list_repo_files returns a different shape than the JSON you'd get from `curl`.** The HF tree API returns `[{"type":"file","oid":"...","size":...,"path":"..."}]` for files. The MCP server returns this verbatim — there's no `files` key wrapping it. Iterate the array directly: `for f in json.loads(result): print(f['path'], f.get('size'))`. Older docs show a `siblings` key, but that's the model_info response, not tree.

**3. whoami 401 doesn't break search.** The current HF_TOKEN in 1Password lacks `user_read` scope — `whoami` and `list_my_models` will return 401. Search/model_info/list_repo_files/public downloads all work without auth, so the tool is fully usable for discovery. Only switch to a fresh token if you need account-scoped ops.

## Verification (2026-10-15)
`search_models('qwen2.5 7b gguf', limit=3)` returned Qwen2.5-Coder-7B-Instruct-GGUF (321k downloads), bartowski/Qwen2.5-7B-Instruct-GGUF, etc.
