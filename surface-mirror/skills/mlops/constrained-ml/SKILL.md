---
name: constrained-ml
description: Local tabular ML, image gen, and SQL via Hermes MCP tools.
version: 1.0.0
author: Jamie Hitch (dqikfox), Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [machine-learning, catboost, tabular, comfyui, image-generation, sql, mcp]
    related_skills: [comfyui, local-knowledge-engine]
    blueprint:
      schedule: "0 2 * * *"
      deliver: local
      prompt: "Run the nightly constrained-ML maintenance pass. List the trained CatBoost models under the model dir with the constrained_ml MCP server, report each model's size and age, and flag any model that has not been evaluated in the last 30 days. If no models exist, say so plainly and do not create one. End with a one-line summary."
      no_agent: false
---

# Constrained ML on THRONE

Local-first ML for the THRONE host: tabular models, image generation and SQL,
exposed to Hermes through the `constrained_ml` MCP server.

This skill describes what actually runs on this machine. It is adapted from a
broader Yandex-stack brief (YandexGPT / CatBoost / YaFSDP / Kandinsky /
YTsaurus) to the capabilities that are genuinely present and verified here.

## When to Use

Use this skill when the user asks to:

- train or score a tabular model, or run CatBoost inference on a record
- generate an image with the local ComfyUI stack
- run a SQL query against a configured SQL-over-HTTP endpoint
- set up a scheduled pass over the local model registry

Don't use it for: LLM inference (use the local Ollama models directly),
multi-GPU distributed training (this host has one RTX 3090 - YaFSDP's
sharding buys nothing with a single GPU), or YTsaurus queries (this host
has no reachable YTsaurus cluster).

## YandexGPT provider (staged, not enabled)

A YandexGPT provider is registered in `config.yaml` under `providers.yandex`
but is `enabled: false`, so it is invisible to the picker and to the runtime
resolver until real credentials exist. It is staged, not functional - do not
report it as working.

What the registered entry actually contains, and the corrections it encodes:

| Field | Value | Why |
|---|---|---|
| `api` / `base_url` | `https://ai.api.cloud.yandex.net/v1` | The OpenAI-compatible endpoint. The commonly cited `https://llm.api.cloud.yandex.net/foundationModels/v1` is the NATIVE Yandex API and its OpenAI-style paths return **404**; the `/v1` host returns 401 (auth required) for the same paths, which is what a live endpoint does. |
| `key_env` | `YANDEX_API_KEY` | The credential name. Hermes resolves it from the environment; the value is never in `config.yaml`. |
| `extra_headers` | `OpenAI-Project: ${YANDEX_FOLDER_ID}` | The folder ID travels as a header, not in the URL. |
| `default_model` | `gpt://${YANDEX_FOLDER_ID}/yandexgpt-5.1` | Yandex models are addressed by URI, not by bare name. |
| `context_length` | `65536` | Hermes refuses any model below `MINIMUM_CONTEXT_LENGTH = 64_000`. The `32768` in the source brief is invalid on this installation. |
| `models` | LIST form (`- id: ...`) | Env expansion only rewrites VALUES, never dict KEYS. In the dict form the `${YANDEX_FOLDER_ID}` placeholder would sit in the key and never expand. The list form puts the model id in a value, so it expands. |

Credentials live in 1Password (`credentials/YANDEX_AI_STUDIO` and
`credentials/YANDEX_FOLDER_ID`) and are injected into the environment by the
`secrets.onepassword` block. Both currently hold `REPLACE_WITH_...`
placeholders, so the provider cannot authenticate until they are filled in.

To enable it once the credentials are real: set `enabled: true` on
`providers.yandex`, then restart the gateway so the new environment is
picked up. Verify with `hermes models` (the provider and its models must
appear) and a single real completion - a `401` means the key or the folder ID
is still wrong, and a `404` means the base URL is wrong.

## Prerequisites

The `constrained_ml` MCP server must be registered in `config.yaml`:

```yaml
mcp_servers:
  constrained_ml:
    command: C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe
    args:
      - C:/Users/KING/AppData/Local/hermes/mcp/constrained_ml/server.py
    timeout: 60
    tools:
      include:
        - catboost_predict
        - catboost_train
        - list_models
        - generate_image
        - sql_query
```

The interpreter path is ABSOLUTE on purpose: a bare `python` does not resolve
in a minimal environment, and the server would then fail to start with no
useful error. Restart the gateway (`hermes gateway restart`) after changing
`config.yaml` so the new server is picked up.

## Quick Reference

| Tool | Purpose |
|---|---|
| `mcp_constrained_ml_catboost_train` | Train a CatBoost model from a CSV; saves `.cbm` under the model dir |
| `mcp_constrained_ml_catboost_predict` | Score one record against a saved model; returns prediction + probabilities |
| `mcp_constrained_ml_list_models` | List trained models with size and age |
| `mcp_constrained_ml_generate_image` | Generate an image through local ComfyUI |
| `mcp_constrained_ml_sql_query` | Run SQL against a configured SQL-over-HTTP endpoint |

Environment overrides (all optional):

- `CONSTRAINED_ML_MODEL_DIR` - where trained models live (default `E:\ultron-memory\ml-models`)
- `COMFYUI_URL` - ComfyUI base URL (default `http://127.0.0.1:8188`)
- `COMFYUI_ROOT` - ComfyUI portable install (default `D:\ai\ComfyUI_windows_portable`)
- `CONSTRAINED_ML_SQL_ENDPOINT` - SQL-over-HTTP endpoint for `sql_query`

## Procedure

### 1. Train a tabular model

1. Inspect the source CSV's schema before training. Confirm the target column
   exists and note which columns are categorical.
2. Call `catboost_train` with the CSV path, the target column, a model name,
   and `task_type` (`classification` or `regression`).
3. Confirm the response reports `ok: true`, the expected row count, and the
   detected `categorical_features` list. A wrong categorical list is the most
   common cause of a model that trains but predicts badly.
4. The model is written to `E:\ultron-memory\ml-models\<name>.cbm`.

Completion criterion: the tool returned a `model` path that exists on disk.

### 2. Score a record

1. Call `catboost_predict` with the model's path and a JSON object of feature
   name to value.
2. Confirm the response includes both `prediction` and `probabilities`.
3. A missing model, malformed JSON, or an unfitted model returns
   `{"ok": false, "error": ..., "fix": ...}`. Report the `fix` field rather
   than retrying blindly - the error already names the problem.

Completion criterion: probabilities are returned for the record.

### 3. Generate an image

1. Call `generate_image` with a prompt and an output path.
2. The tool starts ComfyUI through its documented launcher if it is not
   already running, then submits a txt2img graph over ComfyUI's real HTTP API
   (`POST /prompt`, poll `GET /history/{id}`, fetch `GET /view`).
3. Confirm `size_bytes` is non-zero and the file exists at the output path.

ComfyUI has NO `/hermes/generate` route and no JSON convenience endpoint. The
real contract is exactly the three calls above, and a 405 from any other path
means the tool is calling a route that does not exist.

The graph the tool submits is the minimal txt2img chain:
`CheckpointLoaderSimple` -> `CLIPTextEncode` (positive and negative) ->
`EmptyLatentImage` -> `KSampler` -> `VAEDecode` -> `SaveImage`.

The image checkpoint on this host is `v1-5-pruned-emaonly.safetensors`
(Stable Diffusion 1.5) in `ComfyUI/models/checkpoints`. The tool skips
checkpoints whose name looks like a video model.

**Verify the checkpoint before generating.** A truncated or stale checkpoint
produces a plausible-looking but wrong image, or fails mid-graph. Two checks
on a `.safetensors` file: the JSON header's highest `data_offsets` end must
land exactly on the last byte of the file, and the file's sha256 must match
the sha256 the Hugging Face tree API publishes for that path. The download
recipe is in the `hf-models` skill.

Completion criterion: a non-empty PNG exists at the requested path.

## Pitfalls

- **VRAM is the binding constraint.** The RTX 3090 has 24 GB and the agent's
  own `starscream-64k` model holds 17.5 GB of it. Keep generation at 512x512
  with modest step counts. Do NOT load a second large pipeline (a diffusers
  Kandinsky 3 pipeline, for instance) while the agent model is resident - it
  will OOM the agent itself. This is why image generation goes through
  ComfyUI and not diffusers.
- **ComfyUI holds VRAM even when idle.** A started ComfyUI parks roughly
  3.2 GB of CUDA context on the GPU even with no model loaded. ComfyUI is
  therefore registered in `SERVICES.json` with `start.heal: false` - it HAS a
  working launcher (the MCP server uses it), but the estate watchdog must
  report it and never heal it, so it cannot permanently starve the agent's
  model. The launcher and the heal permission are separate fields: a service
  can have both a path and an explicit opt-out. If a cycle or a tool adds a
  start path without the opt-out, ComfyUI becomes always-on and the agent
  loses its VRAM.
- **The tool cleans up after itself.** If the tool started ComfyUI, it stops
  it again after the image is written (`comfyui_started` / `comfyui_stopped`
  in the response say which happened). A ComfyUI that someone else launched is
  left running. Without this, every image job would cost the agent ~3.2 GB
  of VRAM permanently.
- **Release the diffusion model after every job.** The tool POSTs
  `/free` with `{"unload_models": true, "free_memory": true}` once the image
  is fetched. Without that, ComfyUI keeps the model resident, Ollama evicts
  `starscream-64k` to make room, and every subsequent turn pays a multi-GB
  reload. If the agent model ever disappears from `ollama ps` right after an
  image job, this is the cause.
- **Video checkpoints are not image checkpoints.** This host's ComfyUI ships
  `ltx-video-2b`, which `CheckpointLoaderSimple` cannot use for a txt2img
  graph. The tool skips video checkpoints and reports honestly when no image
  checkpoint is present.
- **ComfyUI has Kandinsky5 NODES but no Kandinsky WEIGHTS.** The nodes are
  not the model. A checkpoint must be present in
  `ComfyUI/models/checkpoints` before generation can work.
- **Never one-hot encode for CatBoost.** Pass categorical column names
  straight through as `cat_features`. Manual encoding throws away the
  ordered-target statistics that are CatBoost's reason to exist.
- **`sql_query` needs a configured endpoint.** There is no YTsaurus cluster
  reachable from this host, so the tool fails with a clear message and a
  `fix` rather than a fabricated result.
- **Never report a tool result that was not returned.** Every tool returns
  JSON with an explicit `ok` field. If `ok` is false, the task failed.

## Automation

The skill's frontmatter carries a Hermes blueprint:

```yaml
metadata:
  hermes:
    blueprint:
      schedule: "0 2 * * *"
      deliver: local
      prompt: "Run the nightly constrained-ML maintenance pass. ..."
      no_agent: false
```

A blueprint is a SUGGESTION until it is accepted. Registering the suggestion
(`register_blueprint_suggestion`) only queues it for review; creating the job
(`create_blueprint_job`) is what actually installs it. The deployed job here
is `blueprint:constrained-ml` (id `55992e507031`), scheduled daily at 02:00
local, delivering to `local`.

Two corrections to the source brief, both verified against the installed
Hermes:

- `deliver: desktop` is not a delivery target. The known platforms are
  telegram, discord, slack, whatsapp, signal, matrix, mattermost, dingtalk,
  feishu, wecom, wecom_callback, weixin, sms, email, webhook, bluebubbles,
  qqbot and yuanbao. `local` writes the run to the job's output directory.
- The blueprint's prompt referenced a YTsaurus CHYT query, which cannot run
  here. The deployed prompt asks for the local model registry instead, so the
  nightly job does real work on this host.

## Verification

Run the round-trip test to prove the server works end to end:

```bash
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  C:/Users/KING/AppData/Local/hermes/scripts/test_constrained_ml.py
```

The image path has its own test, which asserts a real PNG on disk:

```bash
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  C:/Users/KING/AppData/Local/hermes/scripts/test_ml_image.py
```

It trains a model on a generated dataset, predicts two different records,
asserts the probabilities differ, and asserts that every failure path returns
an honest error. It also confirms the MCP server is registered and
discoverable:

```bash
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  -m hermes_cli.main mcp test constrained_ml
```

Expect `Connected` and `Tools discovered: 5`.
