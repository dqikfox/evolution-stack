---
name: hermes-continuous-learning
description: Use when the user says evolve, overhaul, enhance, learn, reflect or "review yourself", and for the nightly Hermes_Learning_Review cron. Reviews recent sessions, failures and memory, distills lessons, and updates memory/skills, proposing (never silently rewriting) SOUL changes.
---

# Hermes continuous learning loop

## Triggers
- **evolve**: normal cycle (steps 1-6), last 26h.
- **enhance**: same, plus improve ONE existing skill that caused friction.
- **overhaul**: deeper review over 7 days (run the digest with env LEARN_HOURS=168), may propose larger SOUL/skill restructures. Still proposals only for SOUL.
- Nightly cron `Hermes_Learning_Review` runs **evolve** automatically.

## Steps
1. Get the digest. In cron it is injected above. Interactively run:
   `python C:/Users/KING/AppData/Local/hermes/scripts/learning_review.py`
   (read-only; set LEARN_HOURS for a different window). Optionally `session_search` for detail.
2. Distill 1-5 lessons: user corrections or frustration (caps, "rubbish", "STOP"), repeated tool errors, failing cron jobs, things that worked well. Evidence-based only; no invented lessons.
3. Append them to `C:/Users/KING/AppData/Local/hermes/memories/LESSONS.md` as:
   `- YYYY-MM-DD [tag] lesson -- evidence: <session title / error>`
   Skip duplicates of lessons already present. Promote only durable, high-value facts into MEMORY.md/USER.md via the memory tool (respect the char limit).
4. Skills: if a lesson maps to a skill, patch that skill with skill_manage (small, targeted edit). Never edit skills under 1password, and never edit addons nexus, nexus_command, office, x.
5. Identity: never rewrite soul.md. Append proposed changes to `C:/Users/KING/AppData/Local/hermes/SOUL_PROPOSALS.md` under `## Proposal YYYY-MM-DD` with rationale; Hitchy approves manually.
6. Log: append one JSON line to `C:/Users/KING/AppData/Local/hermes/logs/evolution-runs.jsonl`:
   `{"ts": ..., "phase": "review", "mode": "evolve|enhance|overhaul", "lessons": N, "skills_patched": [...], "soul_proposal": true|false}`

## Do not build a parallel improvement loop

A benchmark-gated code-evolution system already exists: the THRONE Evolution Stack at
`E:\ultron-memory\evolution-stack` (repo `dqikfox/evolution-stack`), driven by the
`THRONE_Evolution_Loop` cron. When a lesson implies "we need an automated
self-improvement loop", the action is to patch the stack (bench, archive, gate,
consolidation) — not to scaffold a new project. Read the `ultron-evolutionary-loop`
skill (and its `references/evolution-stack.md` file) before proposing anything in
this space.
Consolidate before building: an audit verdict of MERGE / RETIRE / REPAIR means fix
that first, because adding to a redundant surface is regression, not progress.

## Hard rules
- Never kill, stop or restart processes; never free ports. Observe and record only.
- Never touch 1Password / op CLI, secrets, .env, auth.json, or Vision files (C:/Users/KING/projects/vision).
- Back up any existing file before editing it (copy to `<file>.bak-YYYYMMDD`).
- One cycle per run, keep it short; RAM/VRAM on THRONE are tight.

## Final response format
STATUS: OK|PARTIAL|BLOCKED
LESSONS: ...
UPDATED: files/skills changed
SOUL: proposal added? (y/n)
NEXT: ...
