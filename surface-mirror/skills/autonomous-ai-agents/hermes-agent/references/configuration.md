# Configuration, Toolsets & Voice

Edit with `hermes config edit` or `hermes config set section.key value`.
Full reference: https://hermes-agent.nousresearch.com/docs/user-guide/configuration

### Config Sections (most-used keys)

| Section | Key options |
|---------|-------------|
| `model` | `default`, `provider`, `base_url`, `api_key`, `context_length`, `aliases` |
| `agent` | `max_turns` (90), `tool_use_enforcement`, `service_tier`, `verify_on_stop` |
| `terminal` | `backend` (local/docker/ssh/modal/daytona/singularity), `cwd`, `timeout` (180) |
| `compression` | `enabled`, `threshold` (0.50), `target_ratio` (0.20) |
| `display` | `skin`, `interface` (cli/tui), `language`, `show_reasoning`, `show_cost`, `pet` |
| `approvals` | `mode` (smart/manual/off), `timeout`, `cron_mode` |
| `stt` | `enabled`, `provider` (local/groq/openai/mistral/elevenlabs/deepinfra) |
| `tts` | `provider` (edge/elevenlabs/openai/minimax/mistral/neutts/gemini/piper/kittentts/deepinfra/xai) |
| `memory` | `memory_enabled`, `user_profile_enabled`, `provider`, `write_approval` |
| `security` | `redact_secrets`, `website_blocklist` |
| `delegation` | `model`, `provider`, `max_concurrent_children`, `max_iterations` (50), `max_spawn_depth` |
| `checkpoints` | `enabled`, `max_snapshots` (50) |
| `curator` | `enabled`, `consolidate` (false, opt-in aux-model consolidation), `interval_hours`, `stale_after_days` |

`hermes config check` reports sections missing from an older config.

### Toolsets

Enable/disable via `hermes tools` (interactive) or `hermes tools enable/disable NAME`.
Full enumeration: `TOOLSETS` dict in `toolsets.py` (`_HERMES_CORE_TOOLS` is the default bundle most platforms inherit).

| Toolset | What it provides |
|---------|-----------------|
| `web` / `search` | Web search + extraction / search-only subset |
| `browser` | Browser automation (Browserbase, Camofox, or local Chromium) |
| `terminal` | Shell commands and process management |
| `file` | File read/write/search/patch |
| `code_execution` | Sandboxed Python execution |
| `coding` | Code-editing helpers (LSP-backed) |
| `computer_use` | Desktop GUI control (cua-driver) |
| `vision` | Image analysis |
| `image_gen` | Image generation and image-to-image editing |
| `video` / `video_gen` | Video analysis / video generation |
| `x_search` | X (Twitter) search (X OAuth or API key) |
| `tts` | Text-to-speech |
| `skills` | Skill browsing and management |
| `memory` | Persistent cross-session memory |
| `session_search` | Search past conversations |
| `context_engine` | Pluggable context-engine hooks |
| `project` | Named multi-folder workspace tools |
| `delegation` | Subagent task delegation |
| `cronjob` | Scheduled task management |
| `clarify` | Ask user clarifying questions |
| `todo` | In-session task planning |
| `kanban` | Multi-agent work-queue tools (gated to workers) |
| `debugging` | Extra introspection tools (off by default) |
| `safe` | Minimal low-risk toolset for locked-down sessions |
| `spotify`, `discord`, `discord_admin`, `feishu_doc`, `feishu_drive`, `yuanbao` | Service integrations (gated on their credentials). `homeassistant` (`ha_*` tools) is not built in: it comes from the `homeassistant` catalog plugin (`hermes plugins install homeassistant`) |

Tool changes take effect on `/reset` (new session) — never mid-conversation, to preserve prompt caching.

### Video Generation

`video_generate` ships with no default backend. Pick one from the in-tree plugins (`plugins/video_gen/{xai,fal,openrouter,deepinfra}` in the source tree):

```bash
hermes config set video_gen.provider xai   # or fal / openrouter / deepinfra
hermes config set video_gen.model grok-imagine-video   # optional; provider default otherwise
```

Credentials: xAI → `XAI_API_KEY` or xAI Grok OAuth (subscription-billed, preferred); FAL → `FAL_KEY`; OpenRouter → `OPENROUTER_API_KEY`; DeepInfra → `DEEPINFRA_API_KEY`. The tool reads `video_gen.provider` from config.yaml at call time and refreshes plugin discovery on a miss, so a `config set` takes effect without a gateway restart.

## Voice

### STT (Voice → Text)

Voice messages from messaging platforms are auto-transcribed.

```yaml
stt:
  enabled: true
  provider: local   # local (faster-whisper, free) | groq | openai | mistral | elevenlabs | deepinfra
  local:
    model: base     # tiny, base, small, medium, large-v3, turbo
```

Auto-detect priority: local faster-whisper (`python -c "import pm; pm.sync_venv(['stt-whisper'], explicit=True)"`) → Groq (`GROQ_API_KEY`, free tier) → OpenAI (`VOICE_TOOLS_OPENAI_KEY`) → Mistral Voxtral (`MISTRAL_API_KEY`).

### TTS (Text → Voice)

| Provider | Env var | Free? |
|----------|---------|-------|
| Edge TTS (default) | None | Yes |
| ElevenLabs | `ELEVENLABS_API_KEY` | Free tier |
| OpenAI | `VOICE_TOOLS_OPENAI_KEY` | Paid |
| MiniMax | `MINIMAX_API_KEY` | Paid |
| Mistral | `MISTRAL_API_KEY` | Paid |
| Gemini | `GOOGLE_API_KEY` | Free tier |
| NeuTTS / Piper / KittenTTS (local) | None | Free |

Voice commands: `/voice on` (voice-to-voice), `/voice tts` (always voice), `/voice off`.

## Config Editing Safety

Hermes config files are guarded against stale overwrites. **Do not use `write_file` or `patch` directly on `config.yaml` or `.env`** — the tool will refuse with a staleness error.

**Single-key changes:**
```bash
hermes config set model.provider anthropic
hermes config set model.default claude-sonnet-4-6
hermes config unset model.base_url
```

**Profile-specific changes:**
```bash
hermes config set --profile vision model.provider anthropic
hermes config set --profile vision model.default claude-sonnet-4-6
```

**Bulk structural fixes (broken keys, corrupted YAML):**
Write a Python script that uses PyYAML, then run it through the Hermes venv Python:
```bash
# Find the active venv path
VENV="$(ls -d ~/.hermes/installs/*/environments/*/venv 2>/dev/null | tail -1)"
$VENV/bin/python fix.py
```
On Windows (THRONE), the venv Python is at:
```
C:/Users/KING/AppData/Local/hermes/installs/59bf9ddfe703d23a/environments/f0d3db20919c4d5097d61305f0d37b68/venv/Scripts/python.exe
```

**Pitfall:** Config keys containing unquoted colons (e.g., `google/gemini-1: 5-flash:`) silently create phantom nested dicts that break the gateway. After any bulk edit, always run `hermes doctor` to validate before restarting the gateway.

## Provider Configuration

### Primary + Fallback Chain

```yaml
model:
  provider: anthropic
  default: claude-sonnet-4-6
  aliases:
    megatron: local-ollama/starscream-64k
    starscream: local-ollama/starscream-64k:latest
  providers:
    ollama_local:
      api_key: ollama-local
      base_url: http://127.0.0.1:11434/v1
      default_model: starscream-64k
      models: [starscream, qikfox/starscream, CYBA, qikfox/CYBA]
    anthropic:
      api_key: env:ANTHROPIC_API_KEY
      default_model: claude-sonnet-4-6
    openai:
      api_key: env:OPENAI_API_KEY
      default_model: gpt-5
    xai:
      api_key: env:XAI_API_KEY
      default_model: grok-3
  context_length_overrides:
    google/gemini-1.5-flash:
      context_length: 128000
fallback_providers:
  - provider: openai
    model: gpt-5
  - provider: xai
    model: grok-3
  - provider: ollama-launch
    model: qikfox/starscream:latest
providers:
  ollama-launch:
    api: http://127.0.0.1:11434/v1
    base_url: http://127.0.0.1:11434/v1
    default_model: starscream
    discover_models: true
  openrouter:
    api: https://openrouter.ai/api/v1
    base_url: https://openrouter.ai/api/v1
    name: OpenRouter
    default_model: anthropic/claude-sonnet-4
```

**Pitfall:** When changing `model.provider` from a local endpoint (e.g., `ollama-launch`) to a cloud provider (e.g., `anthropic`), always unset `model.base_url` and `model.api_key` first — otherwise the cloud provider receives an Ollama base URL and fails with a 404.

## MOA Preset Configuration

```yaml
moa:
  presets:
    default:
      reference_models:
        - provider: anthropic
          model: claude-sonnet-4-6
          enabled: true
        - provider: openai
          model: gpt-5
          enabled: true
        - provider: xai
          model: grok-3
          enabled: true
      enabled: true
```

**Pitfall:** The MOA preset validates provider names against the Hermes auth system. `openai-codex` and `openrouter` require specific auth states (OAuth for Codex, API key for OpenRouter). If a preset references a provider with missing credentials, Hermes silently skips it — the MOA still runs but with fewer reference models than configured.

## api_server Platform (OpenAI-compatible local API)

The `api_server` platform exposes `/v1/chat/completions`, `/v1/models`, `/v1/runs`, and `/health` on a local port so other tools (Codex CLI, Cline, Aider, or another Hermes instance) can peer with this agent.

**Activation requirements:**
1. `API_SERVER_KEY` env var in `.env` (min 16 characters; auto-validated by `has_usable_secret`)
2. `gateway.platforms.api_server.enabled: true` in `config.yaml`
3. Gateway restart (`hermes gateway restart`)

**Minimal stanza:**
```yaml
gateway:
  platforms:
    api_server:
      enabled: true
      extra:
        key: env:API_SERVER_KEY
        host: 127.0.0.1
        port: 8642
```

**Verification:**
```bash
curl -s http://127.0.0.1:8642/health
# → {"status": "ok", "platform": "hermes-agent", "version": "..."}

curl -s -H "Authorization: Bearer $API_SERVER_KEY" http://127.0.0.1:8642/v1/models
# → {"object": "list", "data": [{"id": "hermes-agent"}]}
```

**Pitfall:** If the port is already occupied by a stale process, the restart warns but may still report success. Verify `netstat -ano | grep 8642` and kill the stale PID before claiming the API is live.

## Provider Credential Diagnostics

When a provider is misconfigured, use this ordered check:
```bash
hermes auth list          # shows which providers have stored credentials
hermes doctor             # checks config validity, deprecated keys, auth status
hermes auth status nous   # per-provider OAuth state
```

For Nous Portal programmatic access (listing agents, querying inference APIs), extract the OAuth token from `auth.json`:
```bash
token=$(python -c "import json; d=json.load(open('~/.hermes/auth.json')); print(d['providers']['nous']['access_token'])")
curl -s -H "Authorization: Bearer $token" "https://portal.nousresearch.com/api/agents"
```
The token expires hourly; refresh with `hermes auth refresh nous`.

**Pitfall:** The Nous Portal inference API (`https://inference-api.nousresearch.com/v1/models`) returns available models but the `/api/agents` endpoint for listing your cloud instances returns an HTML page, not JSON — it is a Next.js app that requires a browser session. Use the `/api/agents` endpoint for agent discovery when building automation.