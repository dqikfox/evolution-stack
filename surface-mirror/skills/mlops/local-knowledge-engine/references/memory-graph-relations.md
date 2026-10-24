# Memory Graph Relation Building

Technique for building relations between memories in a SQLite-based memory graph (e.g., ultron-memory-graph). The database had 3,666 memories with zero relations — this approach built 70,132 weighted edges.

## Schema

```sql
CREATE TABLE memories (
    id INTEGER PRIMARY KEY,
    uuid TEXT,
    content TEXT,
    summary TEXT,
    category TEXT,
    tags TEXT,        -- JSON array string
    entities TEXT,    -- JSON array string
    source TEXT,
    confidence REAL,
    created_at TEXT,
    updated_at TEXT,
    ...
);

CREATE TABLE memory_relations (
    id INTEGER PRIMARY KEY,
    source_uuid TEXT,
    target_uuid TEXT,
    relation TEXT,
    strength REAL,
    created_at TEXT
);
```

## Relation Building Algorithm

For each memory, find the top-K most related memories by computing tag + entity + source overlap:

```python
def compute_related(m, all_mems, k=5):
    m_tags = set(m['tags'])
    m_ents = set(m['entities'])
    m_src = m['source']
    scores = []
    for other in all_mems:
        if other['uuid'] == m['uuid']:
            continue
        o_tags = set(other['tags'])
        o_ents = set(other['entities'])
        tag_overlap = len(m_tags & o_tags)
        ent_overlap = len(m_ents & o_ents)
        same_src = 1 if m_src and m_src == other['source'] else 0
        # Weight: entities > tags > source
        score = (tag_overlap * 0.3) + (ent_overlap * 0.5) + (same_src * 0.2)
        if score > 0:
            scores.append((other['uuid'], score, tag_overlap, ent_overlap))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]
```

## Relation Types

| Type | Condition | Meaning |
|---|---|---|
| `shares_context` | tag_overlap > 0 AND ent_overlap > 0 | Strongest — shared tags + entities |
| `shares_entity` | ent_overlap > 0 only | Named entity overlap |
| `shares_tags` | tag_overlap > 0 only | Topic/category overlap |
| `same_source` | same_src only (no tag/entity overlap) | Weakest — same ingestion source |

## Deduplication

Use a `seen_pairs` set with `tuple(sorted([uuid_a, uuid_b]))` to avoid inserting both A→B and B→A:

```python
seen_pairs = set()
for m in memories:
    for other_uuid, score, tag_o, ent_o in compute_related(m, memories):
        pair = tuple(sorted([m['uuid'], other_uuid]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        relations.append((m['uuid'], other_uuid, rel_type, round(score, 4), now))
```

## Ingesting Vault Notes as Memories

To bridge an Obsidian vault into the memory graph:

1. Read each `.md` file (excluding `.obsidian/`, `.agents/`, `Archive/` dirs)
2. Extract title from frontmatter (`title:` field) or first `# H1` heading
3. Extract tags from frontmatter `tags:` field (parse inline array, block list, or single value)
4. Create a memory with:
   - `content`: `[Obsidian Vault] {title}\nPath: {rel_path}\n\n{first 500 chars}`
   - `category`: `"obsidian"`
   - `tags`: `JSON.dumps(["obsidian", "vault", ...extracted_tags])`
   - `source`: `"obsidian:{relative_path}"`
5. After ingestion, run the relation builder again to connect vault memories to existing memories by shared tags

## Scale Notes

- 3,666 existing memories → 16,920 intra-memory relations (top-5 per memory)
- 246 vault notes ingested → 53,212 additional cross-relations (tag overlap ≥ 2)
- Total: 3,912 memories, 70,132 relations
- Average ~18 edges per node — dense but queryable
- If traversal gets slow, raise the tag-overlap threshold from 2 to 3 to prune weak edges

## Python Gotcha

`datetime.now(timezone=True)` fails — `timezone` is a class, not a boolean. Use `datetime.now(timezone.utc).isoformat()` instead:

```python
# BROKEN
now = datetime.now(timezone=True).isoformat()

# WORKS
from datetime import timezone
now = datetime.now(timezone.utc).isoformat()
```
