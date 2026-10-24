# THRONE Evolution Stack — reference

Location: `E:\ultron-memory\evolution-stack` · repo: github.com/dqikfox/evolution-stack

One integrated DGM/SICA-style self-improvement loop. It exists because THRONE had
evolution pieces that never connected: a gap scout, a watchdog, an upstream
`darwinian_evolver` checkout, a legacy prompt-evolution script pointed at a retired
LM Studio port, and a cron job that applied fixes with no memory of what worked.

The stack adds the three things none of them had: **ARCHIVE**, **BENCHMARK**, **GATE**.

## Layout

```
evo/paths.py          canonical locations, service map, operator-level service set
evo/bench.py          benchmark; gate score vs host score
evo/archive.py        SQLite archive (variants, events, benchmarks)
evo/snapshot.py       snapshot / restore / diff of the improvable surface
evo/mutate.py         Ollama proposer + proposal safety validator
evo/learn.py          the learning bridge: lessons + cron failures + archive -> proposer prompt
evo/mirror.py         copies accepted surface changes into the repo (git-tracked history)
evo/services.py       registry-driven service health + autonomous healing
evo/consolidation.py  inventory + KEEP/MERGE/RETIRE/REPAIR/DUPLICATE audit
evo/loop.py           single CLI entry point
tests/test_gate.py    end-to-end proof of both gate paths
state/archive.db      live archive      reports/  consolidation reports
snapshots/            pre-apply snapshots (zip of the whole surface)
surface-mirror/       git-tracked copy of the surface as the loop changes it
archive/legacy-scripts/  dead one-shot scripts retired from the surface
```

## CLI

```powershell
cd E:\ultron-memory\evolution-stack
python -m evo bench            # scorecard: GATE SCORE + HOST SCORE, per-check pass/fail
python -m evo learn            # rebuild the proposer prompt from live evidence
python -m evo learn --status   # what the loop currently knows
python -m evo audit            # consolidation audit -> reports/latest-consolidation.md
python -m evo status           # archive stats, benchmark trend, best variant, snapshots
python -m evo propose          # ask the local model for one change (records a variant)
python -m evo apply <id>       # snapshot -> apply -> bench -> keep OR auto-rollback
python -m evo rollback <snap>  # manual restore
python -m evo mirror --all     # mirror the surface into this repo
python -m evo services          # registry-driven service survey
python -m evo services --heal   # restart anything down that has a start path
python -m evo history          # variant + benchmark history
python -m evo cycle            # cron-safe: scout + LEARN + HEAL + bench + status file
```

`python -m evo bench` exit code is non-zero while gate-actionable failures remain.

## The service registry (E:\ultron-memory\infra\SERVICES.json)

The registry is what turned "dead service" into "recovered service". Each entry
carries a start path, a health URL and a status:

| status | meaning | loop behaviour |
|---|---|---|
| `up` | listening and healthy | scored, no action |
| `down` + start path | service died | **gate-actionable** — the cycle restarts it before scoring |
| `down`, no start path | nothing to run | host score only (operator action) |
| `retired` | no implementation exists | not checked, never counted as a failure |

`evo cycle` runs `services.survey(auto_heal=True)` before benchmarking, so a
service that dies between cycles is back up before the score is taken. The
registry and `PORT_MAP.json` must stay in sync — PORT_MAP owns the port
contract, SERVICES.json owns the start path.

Proof that healing works: kill HERETIK, run `python -m evo services --heal`,
and it comes back via `heretik\start_demand_proxy.cmd` (recovered :8080).

## The learning bridge (evo/learn.py)

This is what makes the loop *learn* rather than *repeat*:

```
sessions ──► LESSONS.md ─┐
cron failures ───────────┤
rejected proposals ───────┼──► lessons brief ──► proposer prompt ──► candidate ──► GATE
accepted wins ────────────┘        (state/proposer_prompt.txt, versioned in the archive)
```

`evo cycle` calls `evo learn` first, so every hourly cycle starts from current
evidence. The brief includes a **DO NOT REPEAT** section built from rejected
variants and a **WHAT WORKED** section built from accepted ones.

Three benchmark checks make learning measurable and gate-actionable:
`learning:lessons_present`, `learning:proposer_current` (prompt carries a
learned context and is under 24h old), `learning:no_repeat` (rejected variants
are carried into the prompt).

## Benchmark model

`gate_score` = weighted checks that a **file change can fix**:
skills manifest, script compilation, cron health (parse / paid-model pins / failure
streaks), config validity, memory budget, scout freshness, NEXUS + Ollama API health,
stack archive integrity.

`host_score` = everything, including `scored=False` informational checks:
services with no local file-level healer (ultron/krysys/heretik) and managed-repo
cleanliness. Informational checks are reported, never chased by the automated loop.

To move a check from informational to scored, give it a real file-level healer —
otherwise the proposer invents a nonsense fix for it (it wrote a script that ran
`git add .` to "fix" a dirty repo).

## Proposal validator (evo/mutate.py)

Allowlist: target under `skills/` or `scripts/`, suffix `.py` or `.md`, no `..`.
Blocked content patterns: `git ... add` / `git ... commit` (both shell and subprocess
list form), `reset --hard`, `git clean -f`, recursive delete (`Remove-Item -Recurse`,
`shutil.rmtree`), file deletion (`os.remove`/`os.unlink`), disk ops (`Format-`,
`diskpart`, `Clear-Disk`), `Invoke-Expression`/`eval(`, registry delete,
`schtasks /delete`, `sc delete`, force-kill of core processes, and path traversal.

The proposer's own prompt lives in the archive as a variant of kind `proposer`; the
best-scoring proposer is used for the next mutation (the recursive part).

## Cron wiring

Job `THRONE_Evolution_Loop` (every 60m, `starscream-64k` via `ollama-launch`):
- `script` = `evolution_stack_cycle.py` in `%LOCALAPPDATA%/hermes/scripts`, which
  runs `evo cycle` and prints GATE SCORE / HOST SCORE / GATE-ACTIONABLE FAILURES.
- The job prompt tells the agent: propose → `evo apply` (the gate) → verify → report
  `STATUS / SCORE before→after / VARIANT #N accepted|rejected / NEXT`.
- `continuity` is on, so each run sees the previous run's output.
- Operator-level items are routed to the agent with an explicit rule: act only if a
  documented start path exists; never improvise one.

## Consolidation audit

`evo audit` inventories skills, cron jobs, scripts, MCP servers, prior evolution
attempts and cross-profile skill duplication, then emits a verdict per item:

| Verdict | Meaning |
|---|---|
| KEEP | load-bearing, leave alone |
| MERGE | overlaps the evolution stack — fold into `evo/` |
| RETIRE | placeholder or dead one-shot script |
| REPAIR | broken (no SKILL.md, missing description frontmatter) |
| DUPLICATE | same skill in more than one profile |

Rules learned while building it:
- Skip dot-directories (`.hub`, `.locks`, `.curator_backups`) — they are not skills.
- A directory whose children have SKILL.md is a **category**, not a broken skill.
- "Single-file skill" is not a defect; "SKILL.md without description frontmatter" is.
- Detect the same skill name across profiles (default vs vision) as real duplication.
- Archive dead scripts into `archive/legacy-scripts/` rather than deleting — the
  compile check scans the whole scripts dir and one dead file breaks the gate.
- Group scripts by purpose keyword to surface overlap clusters (health, memory,
  evolution, network, utility).

## Gate test (reference implementation)

`tests/test_gate.py`: writes a broken probe into the surface, records a fixing
variant, applies it and asserts ACCEPT with a positive delta; then records a
re-breaking variant, applies it and asserts REJECT plus byte-identical content
restored from the snapshot and the score back at baseline.
