---
name: provider-orchestration
description: "Use when routing a task across ChatGPT, Grok, Claude, Gemini or a local model. One verified rotation with live health, fallback and spend accounting."
description_zh: "当需要在 ChatGPT、Grok、Claude、Gemini 或本地模型之间路由任务时使用。一个经过验证的轮转机制，具备实时健康检查、回退和开销核算。"
author: Hermes Agent
tags: [providers, routing, multi-model, fallback, spend]
---

# Multi-provider orchestration

One entry point reaches every model on THRONE, falls back when one is down, and
records what each provider actually did.

    C:\Users\KING\AppData\Local\hermes\scripts\provider_router.py

## Commands

    provider_router.py health              # probe every provider with a REAL request
    provider_router.py health --json
    provider_router.py chat "your prompt"   # route it, with automatic fallback
    provider_router.py chat "p" --provider xai --model grok-3
    provider_router.py chat "p" --json
    provider_router.py stats                # the spend and latency ledger
    provider_router.py providers            # the registry

## The verified rotation (2026-10-26)

| Provider | Model | Endpoint | State |
|---|---|---|---|
| anthropic | claude-sonnet-4-6 | api.anthropic.com | working, ~1.2s |
| xai | grok-3 | api.x.ai | working, ~3s |
| nexus | kimi-k2.6:cloud | 127.0.0.1:8650/v1 | working, local, free |
| ollama-cloud | minimax-m3.1-flash | ollama.com/v1 | working, ~1.3s |
| ollama-local | starscream:latest | 127.0.0.1:11434 | working, free, 64K |
| openai | gpt-5.5 | api.openai.com | BLOCKED - no credits |
| openai-codex | gpt-5.5 | chatgpt.com backend | BLOCKED - no Codex entitlement |
| copilot | gpt-4o | api.githubcopilot.com | BLOCKED - not licensed |
| openrouter | claude-opus-4.8 | openrouter.ai | BLOCKED - no key exists |

## Proving the rotation (do it this way)

A proof whose PROMPT CONTAINS the expected answer proves nothing - the model
echoes it back from the prompt. A delegation batch whose goals said "Reply
with exactly: CLAUDE SAYS HELLO" passed 3/3 while every child ran on the
same inherited parent model; the delegation manifest showed `provider: null,
model: null`. That was not evidence of a rotation.

The real proof, and it is a permanent test
(`tests/test_provider_routing_proof.py` in the evolution stack):

1. The caller generates a **fresh random nonce** per provider. It is not in
   any prompt the caller pre-wrote, and it differs for every provider.
2. **Pin** one provider per call, so exactly one provider is eligible.
3. Require the response to contain **that provider's** nonce.
4. Require the **served** provider to equal the **pinned** one, and that a
   pinned call never falls through (`attempts` must be empty).
5. Require the **token counts to differ** between providers. That is the
   signature of genuinely different models: Anthropic answered in 23 tokens,
   the local 3090 in 6,796, xAI in 207.

    provider_router.py chat "Reply with exactly this token: RZHMHFHT" \
        --provider xai --json

Then check the ledger: `provider_router.py stats`. Each call is recorded
against its own provider with its own latency, tokens and cost.

## The rules that earned their place

- **A provider is healthy only if a real request returned the expected
  content.** A models list, a 200 on a page, or a config claiming it works
  proves nothing. Probe with `Reply with exactly: ORCHESTRA OK`.
- **A key that cannot pay is BLOCKED, not FAILED.** Keep it out of the
  rotation; do not retry it on every call.
- **A vault outage must not change a provider's verdict.** "The credential
  does not exist" and "the vault would not answer" are different facts. If
  the vault read swallows its errors and returns nothing, a 30-second 1Password
  rate limit silently reclassifies a working provider as broken - and the
  router, still needing an Authorization header, sends a placeholder to a
  hosted API, which answers `invalid_api_key`. The failure then looks like
  bad credentials when it is really a busy vault. Raise a distinct
  `VaultUnavailable`, report it as its own status, and keep the last state
  the provider was actually SEEN in.
- **Never send a placeholder credential to a hosted API.** The `nexus-local`
  placeholder exists for the local NEXUS proxy and nowhere else. A hosted
  endpoint that receives it answers `invalid_api_key`, which reads as a
  credential problem rather than the missing-credential problem it is.
- **Cache the resolved secret with DPAPI (CurrentUser scope).** A vault
  outage degrades a provider; it does not change what the provider IS. The
  plaintext never touches the disk and never appears on a command line.
- **Only a real response may update the last-known record.** If an
  infrastructure failure could write to that record, the next outage would
  read back its own state as if the provider had been seen in it.
- **A dead first fallback is worse than no first fallback.** Order the rotation
  by verified liveness, not by name or by preference.
- **Price a call by its MODEL, not its provider tier.** A per-model price
  table looked up by provider name silently records every paid call as free.
- **An OAuth token can authenticate and still have no entitlement.** A clean
  error naming the model means the account cannot answer, not that the token
  is bad.
- **The same env var can serve two targets.** `OPENAI_API_KEY` holds the
  literal placeholder `nexus-local`, which is right for the NEXUS proxy and
  wrong for api.openai.com.
- **NEXUS already speaks the OpenAI wire protocol**, so it is a provider in its
  own right - 36 local models, zero cost, and the fallback that always works.

## Secrets

Keys are read at call time from the Windows environment or from 1Password
(`ANTHROPIC_API_KEY`, `XAI_API_KEY`, `OLLAMA_API_KEY`, and 1Password's
`OpenAI Project Key`). They are never written to disk, logged, or echoed, and
no key material may be committed to this skill or to the router source.

## Adding a provider

Add a `Provider` to `REGISTRY` in the script, give it a `priority` that
reflects verified liveness, and add a test. If it cannot pay or has no
entitlement, add it to `BLOCKED` with a reason and an unblock instruction -
never to the rotation.

## Verifying

    pytest E:/ultron-memory/evolution-stack/tests/test_provider_router.py -q

19 tests, isolated local HTTP server, no live provider and no real key.

## The estate gate watches this

`evo/bench.py::check_providers` probes the live rotation and the gate FAILS if
fewer than 2 providers are healthy. The estate must not report 100.0/100 while
every model provider is dead.

Three checks, all body-aware:

| Check | Fails when |
|---|---|
| `providers:rotation` | fewer than 2 providers are healthy |
| `providers:accounted` | a provider reports no state and no error |
| `providers:fallback_depth` | the fallback chain is shallower than 2 |

A blocked provider is a KNOWN state, not a failure: it does not fail the gate,
it is never rotated into, and it must still be reported. The negative control
is in the house suite - break the rotation and the gate must drop.

The mirror's contract is the improvable surface only (`hermes/skills` +
`hermes/scripts`). The router and this skill are mirrored; `evo/bench.py` and
the tests live in the stack repo and are version-controlled there.

## The dashboard panel

TESSERACT shows the rotation on the NETWORK tab, under MODEL PROVIDERS. It
reads `E:/ultron-memory/evolution-stack/state/providers.json`, which the
estate's gate publishes - the panel never probes a provider itself, because
a live probe of five providers is five round-trips plus a model load on the
local GPU.

A provider that is BLOCKED is painted gold, never red, and carries both the
reason and the line that says how to unblock it. A blocked provider is not a
fault in the estate.
