# The disk-cleanup plugin deletes permanent artifacts by NAME and by TRACKING age

The house `disk-cleanup` plugin sweeps the Hermes home at the end of every task. Two of its rules will silently delete work that is supposed to be permanent.

## The rules

| Rule | Effect |
|---|---|
| A file whose name starts with `test_` or `tmp_` (or ends `.test.py`, `.test.js`, `.test.ts`, `.test.md`) is category `test` | **Deleted at the end of the next task, age >= 0.** The only exemption is a file inside a git worktree — `hermes/scripts/` is not one. |
| Anything under `hermes/cron/output/` is category `cron-output` | Deleted when its **tracking** age exceeds 14 days. The tracking timestamp is written once and **never refreshed**, so a report rewritten every single day still ages from the day it was first tracked. |
| Anything under `hermes/cache/` is category `temp` | Deleted after 7 tracked-days. |

Source of truth: `plugins/disk-cleanup/disk_cleanup.py` in the Hermes install tree.

- `_TEST_PATTERNS = ("test_", "tmp_")`, `_TEST_SUFFIXES = (".test.py", ".test.js", ".test.ts", ".test.md")`
- `guess_category()` — `cron/output/*` -> `cron-output`, `cache/*` -> `temp`, test-shaped names -> `test`
- `_is_auto_delete(cat, age)` — `cat == "test" or (cat == "temp" and age > 7) or (cat == "cron-output" and age > 14)`
- `track_file()` — `if any(item["path"] == str(path) for item in tracked): return False`, so **an already-tracked path keeps its original timestamp forever**

## What it cost on THRONE (2026-10-25)

Two artifacts were deleted by the same sweep at 16:28 local, taken from `hermes/disk-cleanup/cleanup.log`:

```
[2026-10-25 06:28:05] DELETED: ...\hermes\cron\output\evolution_scout.json (cron-output, 1.9 KB)
[2026-10-25 06:28:05] DELETED: ...\hermes\scripts\test_nexus_launcher_contract.py (test, 7.2 KB)
```

- The scout report had been tracked on **2026-10-01** and rewritten every day since. The plugin deleted it on its 24th tracked-day while the benchmark was reading it as its freshness input.
- The launcher contract — the file that proves NEXUS comes back from one canonical launcher with exactly one supervisor chain and a second supervisor refused — was deleted out from under a passing run because of its *name*. The published mirror pruned it in the same pass, which is how the loss became visible.

## Rules that follow

- **A permanent artifact is named like one.** `nexus_launcher_contract.py`, not `test_nexus_launcher_contract.py`. If it really is a disposable test, it belongs in `hermes/cache/scratch/`.
- **A gate input belongs where its writer owns it.** The scout writes `hermes/state/evolution_scout.json`, which nothing tracks. `hermes/cron/output/` is a convenience copy, and the benchmark reads the owned copy first, the convenience copy second, and the append-only log last.
- **When an artifact vanishes, read the audit log before hunting for a bug in your own code.** The code search across the evolution stack, `hermes/scripts/` and the cron engine found nothing — the plugin is not in any of those trees.

## Where to look

| What | Where |
|---|---|
| Audit log: every file tracked and deleted, with category, size, timestamp | `hermes/disk-cleanup/cleanup.log` |
| Tracking ledger: path, first-tracked timestamp, category, size | `hermes/disk-cleanup/tracked.json` |
| What the next sweep would take | call the plugin's `dry_run()` — returns the auto-delete list without touching anything |

## Reproducing the classification

```python
import importlib.util, sys
p = (r"C:/Users/KING/AppData/Local/hermes/installs/<hash>/environments/<env>/workspace"
     r"/plugins/disk-cleanup/disk_cleanup.py")
spec = importlib.util.spec_from_file_location("dc", p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
auto, prompt = m.dry_run()
for it in auto:
    print(it["category"], it["path"])
```
