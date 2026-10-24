# Vault Sync Automation Patterns

## Incremental vs Full Sync

### Full Sync (initial population)

```python
def sync_full(vault_path: Path):
    """Wipe existing DB and re-import all vault notes."""
    # Clear existing
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM notes_fts")
    
    for md_file in vault_path.rglob("*.md"):
        body = md_file.read_text()
        slug = slugify(md_file.relative_to(vault_path).stem)
        create_note(slug=slug, title=md_file.stem, body=body, source="obsidian")
        
    # Rebuild vector index
    rebuild_chroma_index()
```

**Pitfall:** Interactive confirmation. If `sync_vault.py` contains `input("Press Enter to confirm...")`, headless execution (cron, background jobs, automated pipelines) hangs forever.

**Fix:** Replace interactive prompt with command-line flags:

```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--full", action="store_true", help="Wipe and rebuild (non-interactive)")
parser.add_argument("--yes", action="store_true", help="Auto-confirm destructive operations")
args = parser.parse_args()

if args.full:
    if not args.yes:
        print("Use --yes to confirm full rebuild")
        sys.exit(1)
    sync_full(vault_path)
```

### Incremental Sync (watch mode)

```python
def sync_incremental(vault_path: Path):
    """Only update changed files based on mtime."""
    for md_file in vault_path.rglob("*.md"):
        mtime = md_file.stat().st_mtime
        slug = slugify(md_file.stem)
        
        existing = get_note(slug)
        if existing and existing["updated_at"] and existing["updated_at"] >= mtime:
            continue  # Unchanged
            
        body = md_file.read_text()
        update_or_create_note(slug=slug, title=md_file.stem, body=body)
```

**Pitfall:** Slug collisions. Two notes with the same filename in different folders overwrite each other.

**Fix:** Include relative path in slug:

```python
rel_path = md_file.relative_to(vault_path)
slug = slugify(str(rel_path.with_suffix("")).replace(os.sep, "--"))
# "AI/Knowledge/Skills/hermes.md" → "ai--knowledge--skills--hermes"
```

## Slugify Rules

```python
import re

def slugify(text: str) -> str:
    """Create URL-safe slug from filename or title."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)  # Remove special chars
    text = re.sub(r"[\s_]+", "-", text)   # Spaces → hyphens
    text = re.sub(r"-+", "-", text)        # Collapse multiple hyphens
    return text[:80]  # Truncate to avoid DB overflow
```

## ChromaDB Rebuild After Provider Switch

When changing embedding models (which changes vector dimensions):

```python
import shutil
from pathlib import Path

CHROMA_DIR = Path("data/chroma")

def rebuild_chroma_index():
    """Clear and rebuild vector index from SQLite notes."""
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Re-embed all notes
    for note in list_notes(limit=10000):
        full_note = get_note(note["slug"])  # Need body
        if not full_note or not full_note.get("body"):
            continue
        vector = embed_text(full_note["body"][:2000])
        index_note(full_note, vector)
```

**Pitfall:** `list_notes()` often omits `body` for performance. Always fetch the full note with `get_note(slug)` before indexing.

## Sync Verification

After sync, verify counts match:

```python
def verify_sync(vault_path: Path):
    md_count = len(list(vault_path.rglob("*.md")))
    db_count = count_notes()
    print(f"Vault files: {md_count}")
    print(f"DB notes: {db_count}")
    assert md_count == db_count, f"MISMATCH: {md_count} files vs {db_count} notes"
    
    # Verify graph links
    graph = get_vault_graph()
    print(f"Graph nodes: {len(graph['nodes'])}")
    print(f"Graph links: {len(graph['links'])}")
```
