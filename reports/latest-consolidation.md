# THRONE Consolidation Audit

Generated: 2026-10-24 14:37:13

## Totals

| Surface | Count |
|---|---|
| Skills | 48 |
| Cron jobs | 8 |
| Scripts | 36 |
| MCP servers | 15 |
| Prior evolution attempts | 2 |

## Verdicts

| Verdict | Count |
|---|---|
| DUPLICATE | 1 |
| KEEP | 88 |
| MERGE | 2 |
| REPAIR | 2 |

## Duplicate / overlap clusters

- **health** (15): _health_probe.py, _run_wd.py, hh.py, hh2.py, ollama-health.py, ollama-server.py, restart_nexus.py, run_throne_health.py, shop_server.py, start_tesseract.py
- **memory** (7): debug_nexus_restart.py, mem_guard.py, memory-promoter.py, memory_safety_check.py, robust_nexus_sync.py, throne_discovery.py, throttle-audit.py
- **utility** (7): list-orders.py, manual_outreach.py, order-digest.py, shop-launcher.py, shop_bot.py, telegram_alert.py, wrap-formatprice.py
- **evolution** (3): evolution_scout.py, tesseract_evo_logger.py, throne_evolution.py
- **network** (3): final_patch_script.py, tailnet_sync.py, throne_inventory_updater.py

## Non-KEEP verdicts

| Surface | Item | Verdict | Reason |
|---|---|---|---|
| skill | `security` | REPAIR | no SKILL.md — cannot be loaded |
| skill | `web-development` | REPAIR | no SKILL.md — cannot be loaded |
| script | `tesseract_evo_logger.py` | MERGE | overlaps the evolution stack — fold into evo/ |
| script | `throne_evolution.py` | MERGE | overlaps the evolution stack — fold into evo/ |
| ? | `nexus-core` | DUPLICATE | present in profiles: default, vision |

## Prior attempts (do not build a 4th)

- **darwinian_evolver** — `E:\ultron-memory\darwinian_evolver` — population/mutation engine (imbue-ai), git-tracked (exists=True)
- **legacy_prompt_evolution** — `C:\Users\KING\Projects\evolution` — prompt evolution vs LM Studio :1234 (endpoint retired) (exists=True)