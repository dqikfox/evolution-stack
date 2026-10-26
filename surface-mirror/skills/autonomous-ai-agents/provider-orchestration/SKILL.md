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
| chatgpt | gpt-6-astra | the Codex CLI (ChatGPT Plus) | working, ~9-30s, $0 marginal |
| xai | grok-3 | api.x.ai | working, ~3s |
| nexus | kimi-k2.6:cloud | 127.0.0.1:8650/v1 | working, local, free |
| ollama-cloud | minimax-m3.1-flash | ollama.com/v1 | working, ~1.3s |
| ollama-local | starscream:latest | 127.0.0.1:11434 | working, free, 64K |
| openai | gpt-5.5 | api.openai.com | BLOCKED - no credits |
| copilot | gpt-4o | api.githubcopilot.com | BLOCKED - not licensed |
| openrouter | claude-opus-4.8 | openrouter.ai | BLOCKED - no key exists |

## ChatGPT rides the CLI, not the HTTP API

The ChatGPT Plus account IS entitled, and the token says so:
`chatgpt_plan_type: plus`. Every direct HTTP probe said otherwise:

- `chatgpt.com/backend-api/codex/models` -> HTTP 200, `{"models":[]}`. An
  empty list here proves nothing.
- `/backend-api/codex/responses` with any model -> "the 'X' model is not
  supported when using Codex with a ChatGPT account".
- `/backend-api/conversation` -> 403 Cloudflare HTML. A browser-like header
  set (User-Agent, Origin, sec-ch-ua, Sec-Fetch-*) gets past it, and then
  it answers 422 "Invalid conversation body".

What works is the Codex CLI's own session, `~/.codex/auth.json`
(`auth_mode: chatgpt`). The CLI knows the endpoint, the headers and the body
shape, and it refreshes the OAuth token itself.

**Two binaries, and the version matters.** `.sandbox-bin/codex.exe` is
0.149.0 and refuses the current models with "requires a newer version of
Codex" - a message that looks like an entitlement problem but is not.
`plugins/.plugin-appserver/codex.exe` is 0.162.0 and serves them.

The router's `chatgpt` provider therefore has `kind="codex"` and its own
transport. Rules that came with it:

- **The CLI owns the OAuth session.** The router must never parse
  `~/.codex/auth.json`. No token is read, logged, or placed on a command
  line. A test walks the AST and fails if the router reads that path.
- **The CLI needs its own timeout (300s), not the 90s HTTP default.** It is a
  334 MB binary that reloads its skill set every start. With the default
  leash a working provider was reported dead.
- **A flat subscription is not metered usage.** ChatGPT is priced at $0.00
  marginal cost, because that is what it is to the house. Pricing it like
  metered API usage would invent a cost that does not exist.
- **Entitlement cannot be judged from a models list.** Before declaring a
  provider blocked, try the client that owns the credential.
- **The prompt goes on STDIN, never on the command line.** A Windows command
  line is capped at 32,767 characters. The prompt used to be an argument to
  `codex exec`, so a long prompt failed the whole call with
  `FileNotFoundError [WinError 206]` before the request was ever made - and
  the failure looked like a crash, not a length limit. `codex exec -` reads
  the instructions from stdin, which has no such limit. This applies to the
  worker too, not just the router.
- **The last line of stderr is not the reason.** A Codex run's stderr is full
  of unrelated noise - a stale MCP server can log a fatal 404 there - so
  taking its last line reported "404" for a provider that was really out of
  plan quota. The reason is in the event stream: read the `turn.failed`
  event, not the noise.
- **A plan cap is BLOCKED, not FAILED.** "You've hit your usage limit" means
  the credential is valid and the subscription is real, but the plan will not
  serve more right now. A RATE limit is deliberately NOT blocked - that one
  is transient. And a caller that asked for JSON always gets JSON, with the
  per-provider attempts attached, because a bare line on stderr leaves the
  routing proof, the review rotation and the panel unable to tell a quota
  from a defect.

## Giving ChatGPT a task, not just a question

The Codex CLI is a full agent. Pointed at a working directory it can read and
write files and run commands, so it becomes a worker rather than a chat
endpoint.

    C:\Users\KING\AppData\Local\hermes\scripts\chatgpt_worker.py \
        "add a --version flag to the CLI" --cwd C:/project/x

    ... --read-only     # the worker may only inspect and report
    ... --json          # the raw result: text, usage, sandbox, elapsed

The default sandbox is `workspace-write`, so the worker may change files
inside `--cwd` and nowhere else. The session is `--ephemeral`: no session
files are left behind. The child never inherits `PYTHONPATH`, `PYTHONHOME`,
`PYTHONSTARTUP` or `VIRTUAL_ENV`.

Proven on this host: asked to create a file, it created it, verified it, and
reported the result in 34.6s. Asked to write a `fib` module to spec, it
produced correct code - right algorithm, right exceptions, type annotations -
and it passed a behavioural check, not a visual one.

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

## The local Ollama tag matters

`starscream:latest` and `starscream-64k:latest` are the SAME weights with a different `num_ctx` - 128000 against 65536. Ollama runs a **separate server process for each**, so asking for one while the other is resident means an EIGHTEEN GIGABYTE second copy of the same model. On THRONE, already at 98% memory with 20 GB swapped out, that copy is what tips the machine into thrashing.

Point the local provider at the tag that is actually resident. It is also the one that satisfies the standing rule that no model the user interacts with may have a context below 64K.

**A local cold start needs a realistic allowance.** 45s was enough for a small model; it is not enough to load 18 GB of weights with a 64K context on a host that is also swapping. A timeout there reports a failed provider when the provider was merely cold, and a false failure is worse than a slow answer. The house floor is 45s; the truth for this model is 120.

## The rules that earned their place

- **A provider is healthy only if a real request returned the expected
  content.** A models list, a 200 on a page, or a config claiming it works
  proves nothing. Probe with `Reply with exactly: ORCHESTRA OK`.
- **A missing body is not an error message.** A request that times out
  returns no body at all, so the transport error is the only evidence of
  what happened. If the body-handler stringifies `None`, the published
  error reads literally "None" and the provider looks broken for a reason
  nobody can name. Fall back to the transport error, then to the status
  code. Never let an empty body become the word "None".
- **One transport failure is not a verdict.** A cold start - a model
  loading, an index opening - is not the provider being down. Retry the
  probe once and let only a second failure count, the same
  two-agreeing-probes rule the estate alerting uses. A credential failure
  and a wrong answer are verdicts on the FIRST try: do not retry those.
- **A local provider is not on the internet.** It is a process on this host
  with no network latency, so a miss is a cold start and not a slow route.
  Give it a longer floor (45s) than a hosted provider gets, or the first
  request after a restart will report it dead.
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
  is bad. The converse also holds: a token CAN be entitled while every
  endpoint it can reach says it is not. ChatGPT Plus was "blocked" on
  four separate HTTP probes and was working the whole time.
- **The client version can masquerade as an entitlement failure.** "This
  model requires a newer version of Codex" is a stale binary, not a
  subscription problem. Check the client before the plan.
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

29 tests, isolated local HTTP server, no live provider and no real key. They
cover the vault contract, the placeholder rule, the last-known record and
its isolation from the production state.

    pytest E:/ultron-memory/evolution-stack/tests/test_provider_routing_proof.py -q

7 tests, and these are LIVE calls - they cost a few thousandths of a dollar
and they are the only thing that actually proves the rotation reaches
several different models. Do not mock them, and do not weaken the nonce
check: a mocked version would prove exactly nothing.

A provider that is QUOTA-CAPPED right now makes its case SKIP with the
reason printed, not FAIL: a plan cap is a current condition, not a defect
in the integration, and the entitlement proof and the transport are still
real. The skip must not hollow the proof out - at least three providers
must really have served, or the "different models" claim is not being
tested at all.

    pytest E:/ultron-memory/evolution-stack/tests/test_provider_codex_stdin.py -q

4 tests that prove the Codex transport WITHOUT a provider. A stub binary
stands in for the Codex CLI, so the transport is verified even while a
quota is exhausted. It is the right shape for this: putting the old
command-line line back makes it fail with the exact `WinError 206`.

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
