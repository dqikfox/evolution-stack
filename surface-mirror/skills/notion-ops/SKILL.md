---
name: notion-ops
description: Notion pages, databases, blocks via mcp_notion_* tools.
---

# Notion Ops

Use `mcp_notion_*` tools. Token from NOTION_TOKEN env (1Password `NOTION_API_KEY`).

## Quick reference
- `mcp_notion_search(query='', filter_type='', page_size=25)` — find pages/dbs
- `mcp_notion_get_page(page_id)` — metadata
- `mcp_notion_query_database(database_id, filter_json='', sorts_json='', page_size=50)` — query rows
- `mcp_notion_get_block_children(block_id, page_size=100)` — render content
- `mcp_notion_create_page(parent_id, title, properties_json='', content_md='')` — new page
- `mcp_notion_append_blocks(block_id, content_md)` — append paragraphs

## ID format
Notion IDs are 32-char hex. Accept with or without dashes; the server normalises.

## Property type shortcuts (query_database)
- title, rich_text → joined plain_text
- number → raw
- select → name
- multi_select → list of names
- date → start
- checkbox/url/email → raw

## Common patterns
- **Daily note in DB**: `create_page(parent_id=<db_id>, properties_json='{"Name":{"title":[{"text":{"content":"<date>"}}]}}', content_md="...")`
- **Append to ULTRON HQ**: `get_block_children(<page_id>)` → check last; `append_blocks(<page_id>, content_md=...)`
- **Search filter for "Compiled Knowledge Base"**: `search(query="Compiled Knowledge")`

## Pitfalls

**1. append_blocks splits on \n\n, not \n.** A block of text with single newlines becomes one paragraph block (truncated to 1900 chars). To get multiple paragraph blocks, double-newline-separate them. Markdown-style bullets/headings are NOT rendered as Notion blocks — every block is a `paragraph` rich_text. For real heading/bullet rendering, use the raw blocks API (not exposed in the current MCP server) or pre-render in the Notion UI.

**2. Page IDs are 32-char hex, with or without dashes.** The server normalises both forms (`page_id.replace("-", "")` + length check), so pass whatever Notion's URL gives you. Same applies to database_id, block_id.

**3. Database parent vs page parent detection is brittle.** `create_page` tries `page_id` first, falls back to `database_id`. If the parent is a database, supply the full `properties_json` matching that DB's schema — the `title` arg is ignored for database parents. Empty `properties_json` with a database parent fails with "property ... is required".

**4. search() returns 0 for filter_type='database' in page-only workspaces.** Don't conclude Notion has no databases without first trying filter_type='page' and inspecting what was found — the integration may simply not be shared with any DBs. ULTRON HQ is a single page, not a DB, so don't query it like one.

**5. No transaction safety on multi-step writes.** `append_blocks` doesn't return the appended block IDs, so you can't easily reference them in a follow-up call. For complex multi-block writes, prefer one `create_page` with `content_md` (single round-trip) over chained `append_blocks` calls.
