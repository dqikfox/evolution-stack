# THRONE Evolution Stack

One integrated self-improvement loop for THRONE. It unifies the pieces that
existed separately (and never connected):

| Existing piece | Role now |
|---|---|
| `%LOCALAPPDATA%/hermes/scripts/evolution_scout.py` | gap detection (kept, used by `evo cycle`) |
| `%LOCALAPPDATA%/hermes/scripts/watchdog.py` | host health (kept, run separately by cron) |
| `E:/ultron-memory/darwinian_evolver` | upstream population/mutation engine (reference; not required) |
| `C:/Users/KING/Projects/evolution/evolve.py` | legacy prompt evolution against a retired LM Studio endpoint — archived |
| cron job `THRONE_Evolution_Loop` | the driver — now calls this stack |
| `scripts/throne_evolution.py`, `tesseract_evo_logger.py`, `final_patch_script.py`, `simple_merger.py` | dead one-shot debris — moved to `archive/legacy-scripts/` |

The stack adds the three things none of them had:

1. **ARCHIVE** — SQLite lineage of every proposed variant, its score, its fate.
2. **BENCHMARK** — objective ground truth. No score, no change.
3. **GATE** — apply → snapshot → re-bench → keep *or auto-rollback*.

## Quick start

```powershell
cd E:\ultron-memory\evolution-stack
python -m evo bench          # scorecard (gate score + host score)
python -m evo audit          # consolidation audit -> reports/latest-consolidation.md
python -m evo status         # one-screen summary
python -m evo propose        # ask the local model (Ollama) for one change
python -m evo apply <id>     # snapshot -> apply -> bench -> keep or roll back
python -m evo rollback <snap># manual restore
python -m evo history        # variant + benchmark history
python -m evo cycle          # cron-safe: scout + bench + status file
```

## Two scores, on purpose

* **gate score** — only checks a *file change* can fix (skills, scripts, cron,
  config, memory, scout freshness, NEXUS/Ollama API, stack archive).
  This is what accept/reject is decided on.
* **host score** — everything, including operator-level items (services with no
  local healer, repo cleanliness). Reported, never chased by the automated loop.

Without this split the proposer chases unreachable goals — it tried to
"fix" repo cleanliness by writing a script that ran `git add .` (rejected by
the proposal validator, then excluded from the gate entirely).

## The improvable surface

Only these may be changed by a proposal:

* `%LOCALAPPDATA%/hermes/skills/**` (`.md`, `.py`)
* `%LOCALAPPDATA%/hermes/scripts/**` (`.py`, `.md`)

Never: `cron/jobs.json`, `config.yaml`, credentials, 1Password, or anything
outside the Hermes home. The proposal validator rejects destructive content
(recursive deletes, `git add`/`commit`, disk ops, process kills, eval).

## Safety

* Every apply snapshots the whole surface first (`snapshots/snap-*.zip`).
* A change that does not strictly improve the gate score is rolled back automatically.
* The stack never deletes files; `os.remove`/`rmtree`/`unlink` are blocked.
* Human override: `python -m evo rollback <snapshot-id>`.

## Layout

```
evo/paths.py         canonical locations + service map
evo/bench.py         the benchmark (checks, weights, gate vs host score)
evo/archive.py       SQLite archive (variants, events, benchmarks)
evo/snapshot.py      snapshot / restore / diff
evo/mutate.py        proposer (Ollama) + proposal safety validator
evo/consolidation.py inventory + KEEP/MERGE/RETIRE/REPAIR/DUPLICATE audit
evo/loop.py          single CLI entry point
tests/test_gate.py   end-to-end gate test (accept + reject/rollback)
state/archive.db     live archive
reports/             consolidation reports
snapshots/           pre-apply snapshots
```

## Scheduled driver

Cron job `THRONE_Evolution_Loop` (every 60m, model `starscream-64k` via
`ollama-launch`) runs `scripts/evolution_stack_cycle.py` → `evo cycle`, then
proposes one change, gates it, and reports:

```
STATUS: OK|PARTIAL|BLOCKED
SCORE: <before> -> <after>
VARIANT: #N <accepted|rejected> (<target>)
```
