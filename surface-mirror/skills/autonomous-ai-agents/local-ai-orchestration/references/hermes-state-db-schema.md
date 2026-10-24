# Hermes Agent `state.db` Schema Reference

**Source of truth for "the memory graph" when the agent in question is Hermes Agent itself.**

`%LOCALAPPDATA%\hermes\state.db` is a SQLite database. It is the canonical record of every session, message, model call, and tool use. Verified against a real installation with 238 sessions and 28,250+ messages (2026-08-26).

## Why this matters

There is no separate "memory graph" file. `memories/MEMORY.md` is a flat markdown export and not the graph. If the user says "import the memory graph" and means their Hermes installation, the data lives here. Don't go looking for a JSON dump, a vector store export, or a graph database — it isn't there.

## Tables

### `sessions` (one row per chat)

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | Primary key. Format: `YYYYMMDD_HHMMSS_<6hex>` for human sessions, `cron_<uuid>_<n>` for cron jobs |
| `source` | TEXT | `desktop` / `cli` / `cron` / `kanban` |
| `model` | TEXT | Ollama model id, e.g. `qikfox/starscream:latest` |
| `started_at` | REAL | Unix timestamp |
| `ended_at` | REAL | Unix timestamp; null while active |
| `end_reason` | TEXT | `user_exit` / `ws_orphan_reap` / `error` / etc. |
| `message_count` | INTEGER | Can be 0 even when `messages` table has rows — count separately if you need truth |
| `tool_call_count` | INTEGER | |
| `input_tokens` / `output_tokens` / `cache_read_tokens` / `cache_write_tokens` / `reasoning_tokens` | INTEGER | |
| `title` | TEXT | Auto-generated; useful for topic classification |
| `display_name` / `last_activity_description` | TEXT | Human-readable label candidates |
| `profile_name` | TEXT | Hermes profile (e.g. `default`, `vision`) |
| `archived` / `pinned` | INTEGER 0/1 | |
| `cwd` / `git_branch` / `git_repo_root` | TEXT | Working dir at session start |
| `estimated_cost_usd` / `actual_cost_usd` | REAL | |
| `parent_session_id` | TEXT | For forked / continued sessions |

**Don't trust `message_count` blindly.** On this installation the top session shows `message_count=687` but the `messages` table has 14,995 rows for it — likely because the column is updated periodically and the table is the live count. Always `SELECT COUNT(*)` from `messages` for ground truth.

### `messages` (one row per turn)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Auto-incrementing primary key |
| `session_id` | TEXT | FK to `sessions.id` |
| `role` | TEXT | `user` / `assistant` / `tool` |
| `content` | TEXT | The message body. Can be empty for tool results when content is in `tool_calls` |
| `tool_name` | TEXT | Set when role=`tool` |
| `tool_call_id` | TEXT | |
| `tool_calls` | TEXT | JSON list of tool invocations for assistant messages |
| `token_count` | INTEGER | |
| `timestamp` | REAL | Unix timestamp |
| `reasoning` / `reasoning_content` / `reasoning_details` | TEXT | Chain-of-thought payload for reasoning models |
| `finish_reason` | TEXT | |
| `codex_reasoning_items` / `codex_message_items` | TEXT | For Codex sessions |
| `platform_message_id` | TEXT | ID on the originating platform (Telegram, Discord, etc.) |
| `observed` / `active` / `compacted` | INTEGER 0/1 | State flags |

### `system_prompts`
Cache of system prompts by hash. 46 rows typical.

### `session_model_usage`
Billing attribution per session per model. 279 rows typical.

### `state_meta`
Key/value table for misc state. 4 rows typical.

### `messages_fts` + `messages_fts_data` + `messages_fts_idx` + `messages_fts_docsize` + `messages_fts_config`
Standard SQLite FTS5 mirror of `messages.content`. Use this for any text search — it's <50ms for 28k rows. The trigram FTS5 (`messages_fts_trigram*`) supports `LIKE`-style substring queries via `MATCH`.

## Quick query patterns

**Get all sessions with message counts (ground truth):**
```sql
SELECT s.id, s.title, s.model, s.started_at, s.source,
       COUNT(m.id) AS msg_count
FROM sessions s
LEFT JOIN messages m ON m.session_id = s.id
GROUP BY s.id
ORDER BY s.started_at DESC;
```

**Search the full conversation history (fast):**
```sql
SELECT m.session_id, m.role, m.content, m.timestamp
FROM messages_fts
JOIN messages m ON m.id = messages_fts.rowid
WHERE messages_fts MATCH 'metasploit OR kali OR exploit'
ORDER BY rank
LIMIT 20;
```

**Tool usage distribution:**
```sql
SELECT tool_name, COUNT(*) AS uses
FROM messages
WHERE tool_name IS NOT NULL AND tool_name != ''
GROUP BY tool_name
ORDER BY uses DESC
LIMIT 30;
```

**Daily activity timeline:**
```sql
SELECT DATE(timestamp, 'unixepoch') AS day,
       COUNT(*) AS turns,
       COUNT(DISTINCT session_id) AS sessions
FROM messages
GROUP BY day
ORDER BY day;
```

**Total token spend:**
```sql
SELECT model,
       SUM(input_tokens)  AS in_tok,
       SUM(output_tokens) AS out_tok,
       SUM(actual_cost_usd) AS cost
FROM sessions
WHERE actual_cost_usd IS NOT NULL
GROUP BY model
ORDER BY cost DESC;
```

## Adjacent files (often confused with `state.db`)

| File | Purpose |
|---|---|
| `%LOCALAPPDATA%\hermes\kanban.db` | Separate SQLite — goal/task kanban |
| `%LOCALAPPDATA%\hermes\projects.db` | Separate SQLite — desktop projects |
| `%LOCALAPPDATA%\hermes\verification_evidence.db` | Verify run history |
| `%LOCALAPPDATA%\hermes\cron\executions.db` | Cron job execution log |
| `%LOCALAPPDATA%\hermes\cron\notepad.db` | Cron job scratchpad |
| `%LOCALAPPDATA%\hermes\memories\MEMORY.md` | Flat markdown memory export (8 KB) |
| `%LOCALAPPDATA%\hermes\config.yaml` | Active config (do NOT edit directly — use `hermes config set`) |
| `%LOCALAPPDATA%\hermes\.env` | Secrets and env vars |

## Building a graph from this

The `templates/hermes_memory_graph.py` template uses these tables to produce a `{nodes, edges}` graph JSON in 5 lines of SQL. The graph has these node kinds:

- `user` (1)
- `agent` (1, "Hermes Agent")
- `model` (one per distinct `model` in `sessions`)
- `topic` (auto-classified from `title` + `last_activity_description`)
- `tool` (one per distinct `tool_name` in `messages`, top 40 by usage)
- `session` (one per row in `sessions`)

And edge kinds:

- `user` → `session` (owned)
- `session` → `agent` (uses)
- `session` → `model` (model)
- `session` → `topic` (topic)
- `session` → `tool` (tool, weight = call count)
- `session` → `session` (chronological, same day)

Render with d3-force-graph. See the d3-force-graph skill for the perf checklist at 1k+ nodes (this is small enough to fit comfortably at 300 nodes).
