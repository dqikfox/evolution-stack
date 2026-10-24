---
name: cia-research
description: Search the OCR'd declassified CIA documents (AI symposia, Stargate/SRI, JPRS) and run the expert-system and classifier tools.
---

# CIA research tools

MCP server `cia_research` (tool prefix `mcp_cia_research_*`). Documents: `C:\Users\KING\Documents\ADVANCED RESEARCH\ocr_full\` (OCR text, page level).

## When to load
- "find CIA documents about ..." / "what do the AI Steering Group papers say about ..."
- Questions on Stargate, remote viewing, SRI, Soviet AI research, 1980s intelligence-community AI programs
- Any "assess this situation with rules and confidence" request (expert system)
- Quick classifier training on a small table of numbers

## Tools
1. `search_docs(query, k=8)` - BM25 over every page. Returns doc id, page, snippet. Start here.
2. `read_page(doc, page)` - full OCR text of one page (use the id exactly as shown in search results).
3. `list_docs()` - all indexed documents with page counts.
4. `expert_assess(facts, rules?, explain?)` - forward chaining with MYCIN certainty factors. Facts are `{name: 0..1}`. Omit `rules` for the built-in indications-and-warning demo, or pass `[{"name","if":[...],"then","cf","text"}]`. Set `explain` to a conclusion name to get the derivation.
5. `train_classifier(X, y, hidden?, epochs?)` - numpy MLP, 70/30 split, returns validation accuracy. Limits: 5000 rows, 200 features, 500 epochs.

## Rules
- Quote document ids and page numbers when citing. OCR text has errors (run-together words, misread characters); say so when a quote looks garbled.
- Redacted passages ("25X1", "Denied") are blank in the source; do not guess their content.
- These are declassified historical records; treat claims in them as the authors' claims, not established findings.
- If search finds nothing, rebuild the index with `search_docs(..., refresh_index=true)` once, then report no match.

## Direct-OCR fallback when the MCP server is not connected

The MCP server may not appear in `manage_connections status` and the `mcp_cia_research_*` tool prefix may not resolve via `tool_search` / `tool_describe`. In that state, do not loop on the missing tool — the OCR corpus on disk is the same content the BM25 index would search, and direct file-level analysis is the durable fallback.

**Procedure (when the MCP server is not connected):**
1. `ls "C:\Users\KING\Documents\ADVANCED RESEARCH\ocr_full\"` to enumerate the 27 declassified files (names are bare `CIA-RDP<...>` or `DOC_<...>` strings with `.txt` suffix).
2. `head -c 3000 <file>.txt` to read a document's first pages and confirm content before quoting.
3. `grep -lic "<term>" *.txt` for binary presence checks across the whole corpus (zero hits = absent, not OCR error).
4. `grep -lic "<term1>\|<term2>\|<term3>" *.txt` to look for content by topic across categories (e.g. `magnet\|torsion\|spin\|angular momentum`).
5. Pair the file-level check with `du -sh` to confirm corpus size (~1.7 MB for the standard 27-file set) so you know whether you're looking at a full corpus or a partial mirror.

**Document-category quick map for this corpus (verified by file-level check):**
- 4 Stargate / SRI International / Edwin C. May documents (1985-1987) — the `CIA-RDP96-00789R002200150001-1` 90-page FY 1987 program status report with the DACOS expert system (Figures 1-3) is the canonical Stargate document here.
- ~20 1980s CIA AI / expert-system / neural-network research documents (the CIA-RDP85-, RDP86M-, RDP87M-, RDP88G-, RDP93B-series).
- 5 JPRS / Soviet AI research translations (1964 + 1980s).
- 1 Studies in Intelligence article (`DOC_0000619182`, Vol 27 Spring 1983).
- 0 Tesla documents, 0 Pavlita/Akimov/psychotronic documents, 0 alchemy / transmutation / torsion / Kozyrev / Hayasaka / pyramid / DST-1810S-387-75 content. Pasts that cite such IDs are not verifiable from this corpus.

**Catalog-fabrication detection (paired check):**
When a paste, transcript, or external LLM output enumerates several `CIA-RDP<...>` or `DOC_<...>` IDs under a single topic heading ("all STARGATE files", "all CIA torsion documents", "all Tesla papers"), at least one ID in the list is usually fabricated. The local corpus's file list is the durable ground truth: every ID in a paste must `ls` against the actual corpus. Pattern: 1) list the corpus, 2) diff the paste's IDs against the file list, 3) report verified-vs-unverified in a two-column table, 4) flag unverified IDs as fabrication candidates *before* they are promoted to load-bearing evidence. A "verified paper trail" claim with two fabricated IDs is a fabrication, not a verified trail — even if some other IDs in the same list are real.
