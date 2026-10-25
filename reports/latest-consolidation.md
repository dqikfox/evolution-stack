# THRONE Consolidation Audit

Generated: 2026-10-25 16:28:17

## Totals

| Surface | Count |
|---|---|
| Skills | 46 |
| Cron jobs | 10 |
| Scripts | 49 |
| MCP servers | 15 |
| Prior evolution attempts | 2 |

## Verdicts

| Verdict | Count |
|---|---|
| DUPLICATE | 1 |
| KEEP | 102 |
| MERGE | 3 |

## Duplicate / overlap clusters

- **health** (24): _health_probe.py, _run_wd.py, check_service_liveness.py, evolution_stack_cycle.py, hh.py, hh2.py, host_load_watchdog.py, mcp_call.py, ollama-health.py, ollama-server.py
- **utility** (10): list-orders.py, manual_outreach.py, order-digest.py, secret_resolver.py, shop-launcher.py, shop_bot.py, spawn_detached.py, telegram_alert.py, wait_for_services.py, wrap-formatprice.py
- **memory** (8): debug_nexus_restart.py, mem_guard.py, memory-promoter.py, memory_safety_check.py, nexus_core_sync.py, robust_nexus_sync.py, throne_discovery.py, throttle-audit.py
- **evolution** (4): evolution_scout.py, learning_review.py, n8n_launcher.py, safe_commit.py
- **network** (2): tailnet_sync.py, throne_inventory_updater.py

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