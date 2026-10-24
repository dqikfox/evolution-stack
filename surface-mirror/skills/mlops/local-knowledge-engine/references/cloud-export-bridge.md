# Cloud Export Bridge — NEXUS to External Catalogs

Use when exporting local NEXUS CORE knowledge to cloud data-intelligence platforms (IBM watsonx DI, Snowflake, BigQuery, etc.) for governance, cataloging, and cross-system search.

## Architecture

```
NEXUS SQLite (data/nexus.db)
    ↓ read_nexus_notes()
Markdown docs (docs/ + notes/)
    ↓ read_docs_frontmatter()
Ingest sources (ingest/)
    ↓ sanitize_nexus_export.py
Sanitized JSONL/CSV
    ↓ organize_nexus_data.py
Topic-classified catalog
    ↓ upload
IBM watsonx DI / Cloud catalog
```

## Step 1 — Read Local Sources

NEXUS CORE schema (confirmed working):

```python
# SQLite columns: id, slug, title, body, tags, source, created_at, updated_at, source_hash
# NOT 'content' — use 'body'
# NOT 'origin' — use 'source'
# NO 'archived' column — do not filter on it
cursor.execute("SELECT title, body, tags, source, created_at FROM notes")
```

**Pitfall — Column name mismatch.** The NEXUS DB uses `body` (not `content`) for note text and `source` (not `origin`) for provenance. Queries using `content` or `origin` fail with `no such column`.

Markdown docs may live in both `docs/` and `notes/`:

```python
for md_file in [*DOCS_PATH.rglob("*.md"), *NOTES_PATH.rglob("*.md")]:
    if "_archive" in str(md_file):
        continue
```

**Pitfall — Only scanning `docs/`.** NEXUS stores canonical notes in `notes/` and reference docs in `docs/`. Export scripts that only scan `docs/` miss the bulk of the knowledge base.

## Step 2 — Sanitize Sensitive Data

Always sanitize before cloud ingestion. Scan for these patterns:

| Pattern | Regex | Replacement |
|---------|-------|-------------|
| ElevenLabs | `sk_[a-zA-Z0-9]{20,}` | `[ELEVENLABS_KEY_REDACTED]` |
| OpenAI | `sk-proj-[a-zA-Z0-9_-]{20,}` | `[OPENAI_KEY_REDACTED]` |
| GitHub PAT | `ghp_[a-zA-Z0-9]{20,}` | `[GITHUB_PAT_REDACTED]` |
| HuggingFace | `hf_[a-zA-Z0-9]{20,}` | `[HF_TOKEN_REDACTED]` |
| Generic API key | `(?i)(api[_\s]?key[:\s=]+)([a-zA-Z0-9_\-\/\+]{8,})` | `\1[GENERIC_KEY_REDACTED]` |
| Generic token | `(?i)(token[:\s=]+)([a-zA-Z0-9_\-\/\+]{8,})` | `\1[TOKEN_REDACTED]` |
| Bearer | `Bearer\s+[a-zA-Z0-9_\-\/\+]{10,}` | `[BEARER_TOKEN_REDACTED]` |
| JWT | `eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*` | `[JWT_REDACTED]` |

**Pitfall — False positives.** The word "token" appears in benign contexts (CSRF token, access token discussion). Use case-insensitive boundary matching or whitelist common safe patterns.

**Pitfall — Partial matches.** A regex like `sk_[a-zA-Z0-9]+` catches "sk_5f2...3823" but also "ask_for_help" or "risk_assessment". Anchor with minimum length: `{20,}`.

## Step 3 — Auto-Classify by Topic

Use regex-based classification for speed over LLM inference when processing thousands of records:

```python
TOPIC_RULES = {
    "api_keys_credentials": {
        "patterns": [r"api[_\s]?key", r"token", r"secret", r"password", r"credential"],
        "sensitivity": "HIGH"
    },
    "ai_ml_models": {
        "patterns": [r"llm", r"ollama", r"embedding", r"vector", r"rag"],
        "sensitivity": "LOW"
    },
    "infrastructure_systems": {
        "patterns": [r"server", r"ssh", r"network", r"firewall", r"dns"],
        "sensitivity": "MEDIUM"
    },
    # ... extend as needed
}

def classify_record(record):
    text = (record.get("title", "") + " " + record.get("content", "")).lower()
    scores = {name: sum(len(re.findall(p, text)) for p in rules["patterns"])
              for name, rules in TOPIC_RULES.items()}
    return max(scores, key=scores.get) if any(scores.values()) else "uncategorized"
```

**Pitfall — Overlapping topics.** A note about "SSH key for GitHub" scores in both `api_keys_credentials` and `infrastructure_systems`. Pick the highest score and store runner-up topics for manual review.

## Step 4 — Detect and Merge Duplicates

Before uploading, find and merge duplicate records. Notion exports and vault syncs often create multiple copies of the same page with different timestamps or UUIDs in filenames.

```python
from collections import defaultdict
import re

def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '', t)
    t = re.sub(r'\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', '', t)
    t = re.sub(r'\s+\d+(/\d+)?\s*$', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def find_duplicate_groups(records: list) -> dict:
    groups = defaultdict(list)
    for i, rec in enumerate(records):
        norm = normalize_title(rec.get("title", ""))
        if len(norm) >= 3:
            groups[norm].append(i)
    return {k: v for k, v in groups.items() if len(v) > 1}

def select_best_record(indices: list, records: list) -> dict:
    candidates = [records[i] for i in indices]
    def score(rec):
        s = 0
        if rec.get("content", "").strip(): s += len(rec["content"])
        if rec.get("tags") and str(rec["tags"]) not in ("", "[]", "null"): s += 100
        if rec.get("source") and rec["source"] != "unknown": s += 50
        return s
    candidates.sort(key=score, reverse=True)
    best = candidates[0].copy()
    best["_merged_from"] = len(candidates)
    return best
```

**Pitfall — Aggressive normalization.** Removing UUIDs and timestamps is safe for Notion exports, but may falsely merge genuinely different notes with numeric titles like "Meeting 1" and "Meeting 2". Review groups with short normalized titles before bulk-merging.

**Typical results on a 3,000-record NEXUS export:**
- 350+ duplicate groups detected
- 500–700 redundant records removed (~18% reduction)
- Completeness improved by keeping the fullest version of each group

## Step 5 — Export Formats

### JSONL (for catalog ingestion)

```json
{"record_type": "note", "title": "...", "content": "...", "tags": [...], "source": "...", "timestamp": "...", "classification": {"primary_topic": "...", "sensitivity": "HIGH"}}
```

### CSV (for metadata enrichment)

```csv
title,content,tags,source,sensitivity,topic
```

**Pitfall — CSV quoting with newlines.** Note bodies contain Markdown tables and newlines. Use `csv.DictWriter` with default quoting rules; do not manually quote.

## Step 6 — Windows Credential Retrieval

When credentials live in Windows user environment variables (not `.env`):

```python
import subprocess

def get_windows_env(var_name: str) -> str:
    """Read Windows user environment variable from registry."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"[Environment]::GetEnvironmentVariable('{var_name}', 'User')"],
        capture_output=True, text=True
    )
    return result.stdout.strip()

# Example: IBM watsonx API key stored in Windows env
ibm_key = get_windows_env("IBM_API_KEY")
```

**Pitfall — `os.environ` does not reflect Windows user env changes.** Python's `os.environ` reads the process environment at startup. If the user set `IBM_API_KEY` via Windows Settings or PowerShell `SetEnvironmentVariable`, a running Python process does not see it. Spawn a fresh PowerShell subprocess or restart the Python process.

## Step 7 — Upload to IBM watsonx DI

The IBM watsonx Data Intelligence MCP server exposes 56 tools. After export, use natural-language commands in Hermes:

```
"Import my NEXUS catalog from E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl"
"Create data protection rules for API key patterns in my catalog"
"Run data quality analysis on my exported notes"
```

Or use the Python SDK directly:

```python
from ibm_watsonx_ai import APIClient, Credentials

credentials = Credentials(
    url="https://api.au-syd.dai.cloud.ibm.com",
    api_key=ibm_key
)
client = APIClient(credentials)
# Upload catalog asset
client.data_assets.create(
    name="nexus-core-catalog",
    file_path="E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl",
    project_id=project_id
)
```

**Pitfall — `DI_APIKEY` vs `IBM_API_KEY`.** The MCP server expects `DI_APIKEY`; the IBM Python SDK expects `api_key` in the `Credentials` object. The value is the same IBM Cloud API key. Store one env var and reference it for both.

## Step 8 — Trial Maximization (Extract Permanent Value)

Cloud tool trials expire. Before the IBM trial ends (e.g., Nov 10, 2026), run analysis and export **permanent local artifacts** that remain useful after disconnection.

```python
def maximize_trial(records: list, cloud_client):
    # 1. Data quality analysis
    quality = cloud_client.run_data_quality_analysis(records)
    
    # 2. Business glossary extraction
    glossary = cloud_client.extract_glossary(records)
    
    # 3. Sensitivity classification
    classified = cloud_client.classify_sensitive_data(records)
    
    # 4. SAVE ALL RESULTS LOCALLY
    with open("data_quality_report.json", "w") as f:
        json.dump(quality, f, indent=2)
    with open("enhanced_glossary.csv", "w") as f:
        glossary.to_csv(f, index=False)
    with open("master_catalog.json", "w") as f:
        json.dump(classified, f, indent=2)
    
    return ["data_quality_report.json", "enhanced_glossary.csv", "master_catalog.json"]
```

**Keep after trial expires:**
- `enhanced_glossary.csv` — Business terms discovered by cloud analysis
- `data_quality_report.json` — Actionable fix list for local data
- `master_catalog.json` — Searchable local index with topic + sensitivity tags
- `merge_report.json` — What was merged, sources preserved

**Pitfall — Uploading raw data without extracting insights.** If you only push data to the cloud catalog and never export the analysis results, the insights vanish when the trial expires. Always mirror analysis outputs to local files.

## Verification Checklist

After export and upload:

- [ ] `nexus_catalog.jsonl` line count matches `SELECT COUNT(*) FROM notes`
- [ ] `nexus_catalog_sanitized.jsonl` exists (redacted version)
- [ ] Sanitization audit log shows no unredacted secrets
- [ ] Topic distribution covers expected domains
- [ ] Duplicate merge report shows expected reduction
- [ ] Local trial outputs exist (glossary, quality report, catalog)
- [ ] IBM MCP test passes: `hermes mcp test ibm-watsonx`
- [ ] Cloud catalog shows expected record count

## Related Files

- `scripts/sync-nexus-to-ibm.ps1` — PowerShell automation wrapper
- `src/throne_intelligence/nexus_to_ibm_bridge.py` — Full bridge implementation
- `src/throne_intelligence/sanitize_nexus_export.py` — Sanitization engine
- `src/throne_intelligence/organize_nexus_data.py` — Auto-classifier
- `src/throne_intelligence/merge_nexus_duplicates.py` — Duplicate merger
- `src/throne_intelligence/ibm_trial_maximizer.py` — Trial value extractor
