# Dataset curriculum

How to weight and slice the cleaned corpus for different training goals.

## Default mix (operator model)

The `03_format.py` writer takes all cleaned records as one stream. The implicit weighting follows source volume:

| Source | Approx weight | Why |
|---|---|---|
| **ultron_sft_data** | ~1% by volume, **highest impact per byte** | Purpose-built persona docs; anchor the operator voice |
| obsidian_vault | ~10% | Real notes (LLM Memory Index, Dashboard, project pages) |
| powershell_scripts | ~7% | Scripts + lessons |
| nexus-core | ~55% | Largest mass; mostly research notes — down-weight for balance |
| self-evolution | ~15% | Run logs, skill drafts |
| alchemy | ~6% | HITCHYZ OPUS, corpus, JSON |
| tesseract code | ~4% | Production code, tests |
| codex_sessions | ~3% | User-written Codex CLI session code |
| ultron code | <1% | Operator code |
| obsidian | <1% | Linked notes (legacy E:\) |
| hermes memory | <1% | Identity-bearing, repeats |
| second_brain | <1% | Mostly Obsidian config |
| claude_skills | <1% | SKILL.md files |
| knowledge_vault | <1% | Journal entries |
| stack_inventory | <1% | Stack-inventory snapshot |

**Don't balance purely by file count.** `unsloth_data/` is small (35 files) but should NOT be down-weighted in the corpus mix — it's the densest signal. Treat T1/T2 tier labels as the primary weighting signal and file count as secondary.

## Per-task specialists

| Specialist | Slice | Approx % of full corpus |
|---|---|---|
| `starscream-throne-code` | tesseract_code + ultron_code + tesseract_memos | ~5% (small, focused) |
| `starscream-throne-ops` | tesseract_code (system.py, services.py, tailscale.py, ssh.py) + self_evolution (cron runs) + hermes_memory | ~10% |
| `starscream-throne-alchemy` | alchemy/* + nexus-core/flyxion-corpus-* + nexus-core/research-projects-main-rsvp-* | ~15% |
| `starscream-throne-general` | default mix above | 100% |

## Quality tiers

When auditing, label each record:

- **T1 (high signal)** — direct operator decisions: `system.py`, `services.py`, hands.py, MEMORY.md, USER.md, HITCHYZ_OPUS main body, run logs with timestamps.
- **T2 (mid signal)** — context and structure: stack inventory, AGENTS.md, README files, skill drafts.
- **T3 (low signal)** — repetitive: darwinian_evolver metrics JSON, raw scrape logs without commentary.

Default training mix: 100% T1+T2, drop T3.

## Augmentation

For T1 records, generate 1-3 paraphrases via the running Starscream-64k and append. Triples effective training mass without adding noise.

For chat-format training, prepend the system prompt to every row (already done by `03_format.py`).

## Distillation

Best uplift vs. cost:

1. Take ~500 cleaned T1 records.
2. For each, prompt Starscream-64k: "Here is a draft assistant response. Rewrite it to match the THRONE operator voice and embed the relevant infrastructure context."
3. Mix rewritten + original at 1:1.
4. Train on the mix.

Result: ~3-5× quality uplift on the same parameter count, because the rewritten set carries Starscream's latent knowledge compressed into 7B-shaped training signal.

## Validation split

10% hold-out, sha-based (deterministic). Make sure validation includes at least one record from each source kind — re-roll the seed if a source is missing from val.
