---
name: ultron-evolutionary-loop
description: Use for continuous self-improvement cycles.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [evolution, self-improvement, benchmark, gate, consolidation, throne]
    related_skills: [hermes-continuous-learning, doc-fanout]
---

# Evolutionary Cycle (Ultron) — THRONE

## When to Use

- The user says "evolve", "improve", "self-improve", "keep building", "optimise".
- The user asks for a continuous improvement loop, a self-improving agent, or a
  benchmark-gated evolution cycle.
- The user complains that the stack has too many disconnected systems → run the
  consolidation audit, not a new build.
- The `THRONE_Evolution_Loop` cron fires and you are the worker executing one cycle.

Do not use for: one-off refactors with no loop, or when the user wants a plan only
(use the `plan` skill).

## The rule that governs this skill
**Never add a new self-improvement system. Upgrade the driver that already fires.**

THRONE already runs an evolution cron, a gap scout and a watchdog. A fresh standalone
loop becomes system #101: it never touches the daily driver, so its gains do not
compound. Add the missing capability to the existing driver instead — archive,
benchmark, gate, rollback.

## Where the work lives
Evolution Stack: `E:\ultron-memory\evolution-stack` (github.com/dqikfox/evolution-stack).
Architecture, CLI, bench design, cron wiring and validator patterns:
`references/evolution-stack.md`. Read it before touching the loop.

## Workflow (one cycle)
1. **Baseline** — `python -m evo cycle` (runs the scout, benchmarks, writes
   `cron/output/evolution_status.json`). Never skip it; every improvement claim is a
   delta against this baseline.
2. **Consolidate before you build** — `python -m evo audit`. If the audit reports
   MERGE / RETIRE / REPAIR items, clear those first. Adding a component on top of a
   redundant surface is regression dressed as progress.
3. **Propose** — `python -m evo propose --model starscream-64k`. One change, one
   target, inside the allowed surface (`hermes/skills/**`, `hermes/scripts/**`,
   `.py`/`.md` only).
4. **Gate** — `python -m evo apply <id>`. The stack snapshots, applies, re-benchmarks
   and **rolls back automatically** unless the gate score strictly increased. Never
   hand-edit around the gate — that is how unmeasured drift gets in.
5. **Verify** — `python -m evo bench` and `python -m evo status`. Quote the numbers
   (before → after), never adjectives.
6. **Record** — accepted and rejected variants live in the archive with their score
   and reason; consolidation reports land in `reports/`.

## Benchmark design (decides whether the loop works at all)
- **Two scores.** `gate_score` counts only checks a *file change* can fix; `host_score`
  adds operator-level items (services with no local healer, dirty repos). Accept/reject
  is decided on the gate score.
- A benchmark that scores unfixable items makes the proposer chase unreachable goals —
  it will write a script to "fix" repo cleanliness by committing the user's work. The
  benchmark was wrong, not the model. Split the score rather than blaming the proposer.
- **Strict improvement only.** A 0.00 delta is a rejection: a change that changes
  nothing is churn, and churn accumulates in the surface.
- **Proof obligation.** Before claiming the loop works, run a test that demonstrates
  BOTH paths: accept-on-improve and reject-then-rollback-on-regression, with the
  restored content verified byte-for-byte. `tests/test_gate.py` in the stack is the
  reference implementation.

## Safety rules (non-negotiable)
- Improvable surface: `hermes/skills/**` + `hermes/scripts/**` only. Never
  `cron/jobs.json`, `config.yaml`, credentials, 1Password, or another profile's
  skills/plugins/cron/memories.
- The proposal validator blocks recursive deletes, `git add`/`git commit` (shell *and*
  list form), disk ops, registry/task deletion, process kills, `eval`, path traversal
  and non-`.py`/`.md` targets.
- The stack never deletes files. Deletion is an operator action, done by hand, with the
  archive recording why.
- Every apply snapshots the whole surface first; rollback is automatic and re-verified
  by a second benchmark run.

## Pitfalls
- **Parallel-loop syndrome** — building DGM/SICA as a fresh project while an evolution
  cron already runs. The gains never reach the daily driver.
- **A check that always fails poisons the gate** — e.g. `py_compile` writing to
  `os.devnull` on Windows reports every script as broken; a skill-dir check that counts
  `.hub`/`.locks` as broken skills. Validate every check against the real host before
  trusting a score, or every candidate looks like a regression and gets rolled back.
- **Baseline must be measured inside the same apply call** — a baseline taken minutes
  earlier, or before an unrelated change, makes the delta meaningless.
- **Blind regex rename corrupts mapping prose** — a sweep that renames every occurrence
  also rewrites sentences that *describe* the rename ("X (= X)"). Repair those by hand;
  the full rename procedure is in `doc-fanout`.
- **Recursion needs storage** — keep the proposer's own prompt in the archive and use
  the best-scoring proposer for the next mutation, otherwise the improver can never
  improve itself.
- **Report the delta, not the vibe** — "gate 84.62 → 76.92, rejected, rolled back"
  beats "made it better".
- **Network awareness** — never ignore the relationship between this host (THRONE) and
  its satellites (MSI, S23, Cyclone-C4). We evolve as a network, not in isolation.
- **Stagnation** — do not re-run a completed task without adding verification or
  complexity; do not park a green-health result and stop.
