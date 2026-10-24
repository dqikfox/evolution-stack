# Embedding Provider Switching & Dynamic Collection Names

## The dim-mismatch problem

ChromaDB stores vectors in collections with a fixed dimension determined by the embedding model used at first write. When you change providers, the new writes either:

- Fail with `Collection expecting embedding with dimension of 768, got 384`
- Or worse: silently write to a *different* collection if the name was computed from the provider

## The dynamic-collection-name trap

The most common anti-pattern is computing the collection name from the embedding provider:

```python
# BAD — breaks silently
DEFAULT_COLLECTION = f"nexus-{EMBEDDING_PROVIDER}-{EMBEDDING_MODEL}"
```

When the provider changes, the reindex writes to `nexus-ollama-nomic-embed-text` while the search code reads from `nexus-chroma-default-chroma-default`. The brain looks empty in `/health`, but `chroma.list_collections()` shows three different collections each with partial data.

**Diagnostic:**

```python
import chromadb
c = chromadb.PersistentClient(path="data/chroma")
for col in c.list_collections():
    print(col.name, col.count())
```

You will see multiple collections, each populated by a different historical provider. The "current" one is usually empty.

## The fix — pin the collection name

Hardcode the collection name (or read it from an env var) so reindex always writes to the same place the search code reads from:

```python
# GOOD
import os
DEFAULT_COLLECTION = os.environ.get("NEXUS_CHROMA_COLLECTION", "nexus")
```

The env override is the safety valve: if you ever DO need to switch providers and want a clean reindex, you can set `NEXUS_CHROMA_COLLECTION=nexus-v2` and the reindex populates the new collection without poisoning the old one.

## The clean-switch recipe

When you actually want to change embedding providers (e.g., from `nomic-embed-text` 768-dim to `all-MiniLM-L6-v2` 384-dim):

1. **Update config**: set `EMBEDDING_PROVIDER` and `EMBEDDING_MODEL` to the new values
2. **Wipe ChromaDB entirely** — partial collections with mixed dimensions are unrecoverable:
   ```python
   import shutil
   from pathlib import Path
   shutil.rmtree(Path("data/chroma"))
   ```
3. **Bulk reindex** all notes — never rely on incremental writes after a provider change. Use the batch reindex path that reads from SQLite and embeds with the new provider in one pass.
4. **Verify** before declaring success: the `count` from `get_collection()` should equal the SQLite `notes_count`.

## Detecting which collection is in use

```python
# /health endpoint should report
chroma: { "ok": true, "count": 1018, "collection": "nexus" }

# If collection name is empty or mismatched with the search code's DEFAULT_COLLECTION,
# the reindex wrote to the wrong place. Don't trust the health count alone — verify
# by running a search and confirming results come back.
```

## Why this happens in practice

Q: drive (or any UNC path) is slow for vector writes, so reindex is usually run in the background. The background process starts before the config change propagates, and finishes after the search code has been hot-reloaded with the new provider. The result: the new provider's writes go to a fresh collection, the old collection is read, and nothing matches.

Always restart the search-reading process AFTER the reindex completes, or pin the collection name to a single value across all processes.

## See also

- `references/ollama-rag-troubleshooting.md` — empty RAG responses from `/api/generate` vs `/api/chat`
- `references/nexus-core-build-log.md` — the full reindex failure chain that exposed this
