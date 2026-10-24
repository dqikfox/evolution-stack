---
name: memory-promoter
description: Promote stable, demote dated, delete stale memory.
---

# Memory Promotion Strategy

## When to load
- "memory is full"
- USER.md > 85%
- MEMORY.md > 85%
- Daily cron: Memory_Hygiene

## Promotion rules
- **Stable identity/preference** -> USER.md
- **Procedure/pattern** -> SKILL (skill_manage)
- **Time-bound fact** (last verified YYYY-MM-DD) -> tagged `stale-30d` / `stale-60d` / `stale-90d`
- **Old, not re-verified** -> DELETE

## Aging criteria
| Entry age | Action |
|---|---|
| <30d | Keep, refresh verified-date |
| 30-60d | Verify or mark `stale-30d` |
| 60-90d | Move to skill or delete |
| >90d without verification | Delete unless core identity |

## Standing rules stay forever (never demote)
- The user's name
- The user's project canon (Ultron / Starscream / THRONE / TESSERACT)
- Authority directive (full autonomy)
- Secret handling (never echo, vault of record = 1Password)
- "Don't ask, build" posture

## Report format
"PROMOTED: N -> USER.md / SKILLS
DEMOTED: M (aged out)
DELETED: K (stale, no resurrection)
CURRENT: USER 89% / MEM 82%"

## Do not
- Delete identity entries
- Echo deleted content
- Batch-delete >5 entries in one session without summary