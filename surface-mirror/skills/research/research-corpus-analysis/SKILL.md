---
name: research-corpus-analysis
description: Use when decoding local corpora into structured study logs.
---

# Research Corpus Analysis

Distill a local user corpus (chat exports, PDF libraries) into a canonical study log with decoded terminology and verified claims.

## Procedure

1. **Survey the archive before reading content.** `ls` the export dir; count messages (`grep -c 'class="message default clearfix"'`), extract date ranges (`title="DD.MM.YYYY` attributes) and sender roster FIRST — knowing who speaks most tells you whose statements are doctrine vs. questions.
2. **Extract sender names from Telegram Desktop HTML exports** with the regex `from_name">\s*([^<]+)` via Python — names sit on the line after the `<div class="from_name">` tag, so line-based grep misses them. Count with `collections.Counter`.
3. **Grep multi-file exports for each coded term** with context: `grep -ioE '[^<]{0,150}(term1|term2)[^<]{0,250}' messages*.html` — bounded `[^<]` windows avoid HTML tag bleed and keep snippets quotable.
4. **Build a decode table**: coded term → stated properties → function → aliases. Quote the source verbatim for every claim; never paraphrase doctrine from memory.
5. **Machine-diff comparable corpora to the same schema.** When two sources are comparable
   (two recipe books, author notebook vs. treatise), extract each with the IDENTICAL regex
   field-set (materials, quantities, operations, durations, colors) into sibling JSONs and
   Counter-diff them. Partitioned material/operation sets (e.g. melt×39 vs boil×52) prove
   workshop specialization that narrative comparison misses. For dated notebook entries,
   split on `\b(?:Jan|Feb|...|Dec)\w*\.?\s*\d{1,2}` and field-extract grain-weights and
   alchemical symbol literals (♁♂☿♄♀🜹) as materials.
6. **Extract PDF libraries to text** with pymupdf (`pip install pymupdf`) into `<corpus>/_extracted/*.txt`, recording page/char counts. Then term-frequency tag every alias across all files (`str.count`) — density concentration reveals which document is the operating manual vs. theory text. Zero-counts matter too: a key term *absent* from a corpus is evidence of deliberate concealment.
6. **Verify all numerals computationally.** Any formula in the corpus must be checked in code and factorings listed before writing conclusions.
7. **Write the study log INTO the source folder** (user's stated preference: deliverable lives next to the data), named in the user's chosen title. Append further research as new dated Parts; never rewrite earlier Parts.
8. **Correlate with external scholarship** (web_search) only after the internal decode is stable — cite historians/projects by name, and mark clearly where the external record diverges from the group's doctrine.

## Pitfalls

- When DDG `web_extract` declines to extract, don't retry it — curl the page, strip tags, and fall back to archive.org `_djvu.txt` streams for scanned historical translations that lack a clean web page.
- Telegram export HTML splits sender names from their div across lines; use Python regex over the raw file, not grep line-matching.
- Do not treat apparent numeric contradictions in primary sources as errors until tested against a unit-scaling framework — authors deliberately state the same stage at different units; gather ALL count passages verbatim into a ledger first, then test reconciliations.
- Filenames with non-ASCII characters (e.g. è in French titles) can silently fail opens on Windows; catch and report rather than skipping.
- Answer the literal question first, then offer the extension — the user's 'KEEP BUILDING' pattern means ship the complete decode in one pass, not incremental teasers.
- When a corpus author explicitly compares two routes and deprecates one, capture the
  comparison verbatim and record the author's stance as its own finding. The text
  "Some use X, but the other way (which is most secret) we commend" is the gold:
  the corpus has a recommended practice AND a deprecated alternative, and the
  distinction is evidence about both routes. File the deprecation in the dossier's
  `counterevidence` and the recommended practice in `ordered_operations`.
- When an author says "I never yet tried it" of an alternative, that alternative is
  hearsay-tier (others' claims), not personal-report-tier (author's bench
  experience). Mark the unverified route separately in any audit; do not lump it
  with the author's attested procedure.
- When the same operation appears in both verse and prose forms (e.g. 17c alchemical
  verse Marrow vs. prose Starkey MS 13), the verse is the literary surface and the
  prose is the operational core. Quote both, but treat the prose as the primary
  source for operation counts and time estimates.
