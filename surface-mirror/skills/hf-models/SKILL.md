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

**Check `D:\ai\models\` before downloading.** THRONE already has HERETICSEEK-7B-Ditill Q4_K_M (4.68GB), Mistral-7B-Instruct-v0.3 Q4_K_M (4.37GB), and Qwen2.5-7B-Instruct Q4_K_M (4.68GB) — the official Qwen quant, not bartowski. Before pulling a 4–5GB GGUF, list the directory and skip if the base quant already exists. Same model, different quantizer filenames collide silently (`Qwen2.5-7B-Instruct.Q4_K_M.gguf` vs `Qwen2.5-7B-Instruct-Q4_K_M.gguf` differ by one dash).

**list_repo_files returns a different shape than the JSON you'd get from `curl`.** The HF tree API returns `[{"type":"file","oid":"...","size":...,"path":"..."}]` for files. The MCP server returns this verbatim — there's no `files` key wrapping it. Iterate the array directly: `for f in json.loads(result): print(f['path'], f.get('size'))`. Older docs show a `siblings` key, but that's the model_info response, not tree.

**whoami 401 doesn't break search.** The current HF_TOKEN in 1Password lacks `user_read` scope — `whoami` and `list_my_models` will return 401. Search/model_info/list_repo_files/public downloads all work without auth, so the tool is fully usable for discovery. Only switch to a fresh token if you need account-scoped ops.

**Fetch the token from 1Password, and check it is non-empty.** `op item get
HF_TOKEN --vault credentials --fields credential --reveal` returns the value;
`--fields credential=HF_TOKEN` is a FIELD-NAME typo that returns an empty
string silently, and an empty token becomes `Illegal header value b'Bearer '`
far from the cause. Prefer `op run` / `op inject` over exporting the token
into a persistent shell.

**A stale background job can report a failure for work that already
succeeded.** A supervised download that failed earlier may be re-reported
long after a later, successful run replaced it. Before acting on a reported
download error, check the artifact on disk and its hash — not the log line
that announced it.

## Verifying a large download

**A completed download is a claim, not a fact — verify the bytes.** A download
that reports success can still leave a truncated file, and a resumed or
backgrounded transfer is the case where it happens. Two cheap checks, in
order:

1. **Structural completeness.** A `.safetensors` file is an 8-byte
   little-endian header length, then that many bytes of JSON, then the raw
   tensor data. The JSON header's highest `data_offsets` end must land exactly
   on the last byte of the file:

   ```python
   import json, struct
   with open(p, "rb") as f:
       n = struct.unpack("<Q", f.read(8))[0]
       hdr = json.loads(f.read(n))
   end = max(v["data_offsets"][1] for k, v in hdr.items() if k != "__metadata__")
   assert 8 + n + end == os.path.getsize(p)   # truncated otherwise
   ```

2. **Hash against the registry.** The HF tree API publishes the LFS sha256
   for each file. Compare it to the local `sha256sum` and to the upstream
   `size`:

   ```bash
   curl -s -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/models/<repo_id>/tree/main?recursive=1" \
     | python -c "import json,sys; [print(e.get('lfs',{}).get('oid') or e.get('oid'), e.get('size')) for e in json.load(sys.stdin) if e.get('path','').endswith('<file>')]"
   sha256sum <local_file>
   ```

Both must match. This is the only check that distinguishes a correct file
from a same-named file left behind by an earlier run.

## Verification (2026-10-15)
`search_models('qwen2.5 7b gguf', limit=3)` returned Qwen2.5-Coder-7B-Instruct-GGUF (321k downloads), bartowski/Qwen2.5-7B-Instruct-GGUF, etc.
