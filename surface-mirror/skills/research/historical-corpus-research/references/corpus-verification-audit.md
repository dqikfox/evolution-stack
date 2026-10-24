# Corpus Verification Audit

Run this at the end of every corpus build, before reporting. It catches the specific
classes of error that survive a *feeling* of correctness.

## File-level audit

1. **Existence + validity.** Glob the corpus dir for the expected file list; open every
   `.json` and confirm it parses; CSVs get a line-count. Missing/invalid entries are a
   hard stop — never audit a corpus with broken inputs.
2. **Record-count match.** For each file, compare the reported record count in the study
   log vs the live count on disk. Any divergence gets its own entry in the report.
3. **Schema sanity per record.** Open one record per file and eyeball the fields; confirm
   normalization preserved the raw source string adjacent to every normalized value.

## Substance-level audit

4. **Reload the raw claims, don't trust the narrative.** Re-list every claim of the form
   "X has N occurrences" / "Y never appears earlier than source Z" and re-run the exact
   regex/count over the corpus text (e.g. `text.lower().count('green lion')`). Report the
   actual found numbers, even if they contradict the conclusion already written.
5. **Duration ranges per corpus.** Re-collect every duration value from every corpus and
   list the *distinct buckets actually present* — minutes-hours / days / weeks / months —
   not the narrative range. Watch for one-off stragglers missed by the headline claim
   (e.g. a corpus reported as "max 2 days" but containing one longer entry, or a corpus
   reported as short-window while holding a 365-day value).
6. **Wrapper-dict artifact.** A counts-table built by naive `len(dict)` reads outer keys,
   not the real fragment count. Print the actual payload list length (e.g.
   `len(data['pdm'])`) before reporting the corpus size.

## Reporting rule

The audit output MUST include:

- a file-integrity table (expected vs present vs parse status per file),
- a claims-verified table (claim vs re-measured value vs verdict),
- an explicit limitations section (severity MEDIUM/LOW/ACCEPTABLE per known shortcoming),
- any *new datum* the audit surfaced that the earlier summary missed — write it into the
  chapter as a correction/amendment, not just into the audit file.

## Failure modes to log as limitations

- Text extracted from a **secondary translation layer** (e.g. French gloss interpolated
  into a Greek corpus) rather than from the primary-language text — record the provenance
  chain in the limitation note.
- **Paraphrase-based extraction** of a load-bearing bridge corpus (condensed modern
  translation standing in for the verbatim manuscript) — MEDIUM severity, mark for rerun
  with verbatim text at the same item numbers; the match engine is reusable.
- A **promised companion dataset** (e.g. a cross-manuscript diff) that is pending but
  unwritten at the time of audit — LOW severity, list as pending rather than shipped.
