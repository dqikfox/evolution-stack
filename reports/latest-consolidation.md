# THRONE Consolidation Audit

Generated: 2026-10-26 22:44:38

## Totals

| Surface | Count |
|---|---|
| Skills | 45 |
| Cron jobs | 10 |
| Scripts | 77 |
| MCP servers | 15 |
| Prior evolution attempts | 2 |

## Verdicts

| Verdict | Count |
|---|---|
| DUPLICATE | 1 |
| KEEP | 129 |
| MERGE | 3 |

## Duplicate / overlap clusters

- **health** (37): _health_probe.py, _run_wd.py, check_service_liveness.py, estate_watchdog.py, estate_watchdog_contract.py, evolution_stack_cycle.py, fix_api_server_platform.py, verify_all_branches.py, hermes_remote.py, hh.py
- **utility** (22): apply_brand_fixes.py, chatgpt_worker.py, extract_public_copy.py, push_all_branches.py, push_rewritten.py, rewrite_identity.py, rewrite_local_identities.py, rewrite_queue.py, list-orders.py, manual_outreach.py
- **memory** (7): debug_nexus_restart.py, mem_guard.py, memory-promoter.py, memory_safety_check.py, nexus_core_sync.py, robust_nexus_sync.py, throttle-audit.py
- **evolution** (4): evolution_scout.py, learning_review.py, n8n_launcher.py, safe_commit.py
- **network** (4): register_service.py, start_discovery.py, tailnet_sync.py, throne_inventory_updater.py
- **backup** (2): rewrite_remote.py, mcp_doctor.py

## Non-KEEP verdicts

| Surface | Item | Verdict | Reason |
|---|---|---|---|
| script | `learning_review.py` | MERGE | overlaps the evolution stack — fold into evo/ |
| script | `n8n_launcher.py` | MERGE | overlaps the evolution stack — fold into evo/ |
| script | `safe_commit.py` | MERGE | overlaps the evolution stack — fold into evo/ |
| ? | `nexus-core` | DUPLICATE | present in profiles: default, vision |

## Prior attempts (do not build a 4th)

- **darwinian_evolver** — `E:\ultron-memory\darwinian_evolver` — population/mutation engine (imbue-ai), git-tracked (exists=True)
- **legacy_prompt_evolution** — `C:\Users\KING\Projects\evolution` — prompt evolution vs LM Studio :1234 (endpoint retired) (exists=True)