---
name: historical-corpus-research
description: "Research old texts; build corpus + falsification ledger."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [Research, Corpus, Text-Analysis, Falsification, History]
    category: research
    related_skills: [grounded-citations, pdf, ocr-and-documents]
---

# Historical Corpus Research

## When to use

Use this skill when working with **multi-source research over old/primary documents** —
manuscripts, scans, translations, Telegram/forum exports, library PDFs — where the
deliverable is a **testable knowledge base**, not an essay. Build corpora that *test
claims*, never anthologies that accumulate confirmations. When reviewing prior corpus
work, run a hostile self-audit (three-tier 🟢/🟡/🔴 confidence ledger) before
extending it.

Do not use this skill for: single-document summaries, current-events research, or
tasks where the user wants a quick answer rather than a tested corpus. For
single-document extraction, see `pdf` or `ocr-and-documents`. For citation plumbing,
see `grounded-citations`.

When the user signals open-ended continuation ("KEEP COLLECTING", "KEEP BUILDING"),
or asks for tier discipline ("FACT vs FICTION"), or asks for a plain-English
translation pass, the dossier-series convention in
`references/evidence-dossier-series.md` is the default output shape.

## Procedure

For multi-source research over old/primary documents — manuscripts, scans, translations,
Telegram/forum exports — where the deliverable is a **testable knowledge base**, not an
essay. Build corpora that *test claims*, never anthologies that accumulate confirmations.
When reviewing prior corpus work, run a hostile self-audit (three-tier 🟢/🟡/🔴 confidence
ledger) before extending it.

0. **Fetch chain for dead URLs.** DDG-backed `web_extract` refuses URL extraction outright —
   go straight to `curl -sL -A "Mozilla/5.0" URL -o $LOCALAPPDATA/Temp/<name>.html`, then
   regex-strip tags + `html.unescape` to `.txt`. If a known source page is a stub (short
   Wikipedia/Wikisource entry), search for the *published translation* (e.g. archive.org
   `<title>_djvu.txt` full-text streams) — those give complete OCR of the scanned book.

1. **Extract texts to plain files.** PDFs with `pymupdf` (`import pymupdf`, NOT deprecated
   `import fitz`). Web pages: `curl -sL -A "Mozilla/5.0"` to Temp, strip tags via regex +
   `html.unescape`. Chat exports: scan raw HTML with `grep -ioE '[^<]{0,N}TERM[^<]{0,M}'`
   for context windows. **For JS-gated transcription readers (e.g., Chymistry of Isaac
   Newton, Archive.org bookreader): use the browser tool to capture
   `document.body.innerText`, save the raw JSON, then regex-split page markers.** See
   `references/js-gated-archive-extraction.md` for URL patterns and split regexes. Save under
   <project>/corpus/` and `_extracted/*.txt` — keep original recipe/section numbering.
   **When the OCR has lost reliable printed-page numbers, render PDF pages directly with
   PyMuPDF at 200 DPI and vision-check instead of mapping OCR line numbers back to pages.**
   See `references/pymupdf-page-anchoring.md` for the working pattern.

2. **Archive.org detail pages route through printdisabled/encrypted derivatives.**
   Do not trust the "Download" buttons or guessed PDF links; instead call
   `https://archive.org/metadata/<item>` to enumerate files, then test
   `https://archive.org/download/<item>/<filename>`. If OCR text streams (`.djvu.txt`,
   `_hocr_searchtext.txt.gz`) return 401, fall back to the public-domain PDF when available,
   or to browser capture of the BookReader/transcription.

2. **Field-normalize to JSON.** Regex-split numbered items (`re.split(r'\n(\d{1,3})\.\s+', text)`),
   fields: `no, source, title, raw_text, materials[], quantities[], operations[], durations[],
   colors[], endpoints[], uncertainty, source_page`. Preserve raw wording beside every
   normalized value — never normalize away the evidence.

3. **Motif-chronology matrix.** Regex per motif, presence-counts with sources ordered by date.
   Detect *ordered sequences* by comparing first-occurrence positions, not just counts.
   Individual motifs vs ordered sequences are different findings — a corpus can hold "white"
   and "red" labels without the staged sequence. A motif appearing ONLY in the newest source
   is an interpretive overlay retrojected onto old texts — say so, don't assume antiquity.

4. **Textual variant rule.** Contradictory glosses from one author (glossary says X, a body
   passage says Y): record BOTH with passage refs — never "correct" one with the other.
   A variant is data, not an error to flatten.

5. **Falsification before expansion.** For any numerical pattern or mass balance ($\sum\text{Mass}_{\text{in}}$ vs $\text{Mass}_{\text{out}}$): compute GCD/divisibility and check for unexplained gains; enforce provenance
  independence (a copy of a source is not a second witness); separate training vs held-out
  observations. If only sacred/scaffold values fit and empirical values don't, the pattern
  is a frame not a law — downgrade it in writing.; separate training vs held-out
   observations. If only sacred/scaffold values fit and empirical values don't, the pattern
   is a frame not a law — downgrade it in writing.

6. **Every claim carries [SRC-ID + passage ref]** and an evidence tier: 🟢 primary text ·
   🔵 archaeology · 🟣 experiment · 🟡 scholarship · 🟠 inference · 🔴 speculation. For
   citation plumbing use the `grounded-citations` skill.

6a. **Tier discipline for the user, not just the corpus.** When the user explicitly
    asks for "FACT vs FICTION" or "separate fact from interpretation" or
    "knowledge is key", apply the three-tier convention (FACT / STRONG INTERPRETATION /
    UNPROVEN) as a per-claim label in plain prose, not just an internal confidence
    flag. Each evidence section of the deliverable carries explicit tier labels so the
    user can read the document and know what is established vs. what is interpretation
    vs. what is unproven. The internal 🟢/🟡/🔴 codes are for the corpus; the three-tier
    prose labels are for the reader.

6b. **The plain-English translation pass.** When the user says "translate it into plain
    English" or "anyone can understand this mess", produce a dedicated plain-English
    dossier in addition to the source-critical technical version. Same evidence, same
    citations, but the prose explains every specialist term inline (what is "the Eagle
    operation", what is "Sulphur-Mercury-Salt theory", what is a "drachm"), and the
    tier discipline (FACT / STRONG INTERPRETATION / UNPROVEN) is applied to every
    claim in the body, not relegated to an appendix. The plain-English dossier is
    not a summary — it is a parallel re-presentation of the same evidence at a
    non-specialist reading level, and it should stand alone (a reader with no prior
    knowledge of the topic should be able to read it and understand what the corpus
    says and what the standing position is).

6c. **Dossier-series file convention for "keep going" prompts.** When the user
    signals an open-ended evidence-collection directive ("KEEP COLLECTING", "KEEP
    BUILDING IT", "continue"), organize the resulting evidence as a numbered letter
    series in a single dated folder: `G08.md`, `G08B.md`, `G08C.md`, `G08D.md`...
    Each dossier in the series is self-contained (one source class or one
    counter-evidence class), updates the standing position at the end, and ends with
    the same next-step pointer (typically "G04 modern reproduction is the natural
    next step"). Append, never rewrite. Patch WORK_LOG and the master DATA INDEX
    once per dossier with a dated entry. This convention is durable: a later session
    can pick up the next letter in the series without re-reading the whole corpus.

6d. **Hunt the opposing view in the same archive.** When the user prompts for
    "knowledge is key" or "separate fact from fiction", the strongest evidence
    move is to search the *existing corpus* for the contemporary critic, not to
    go looking for external counter-arguments. The corpus's strongest critic
    often sits in the archive unmapped (e.g. Robert Boyle's *Sceptical Chymist*
    1661, the founding text of modern chemistry's rejection of alchemy, may be
    in the corpus under a different tag). Locate it, read it, label it
    counter-evidence explicitly, and build a dedicated counter-evidence dossier
    (e.g. G08C). This is distinct from the closing self-audit: self-audit
    re-verifies the corpus's own claims; counter-evidence hunt looks for the
    contemporary position that the corpus is being tested against.

6e. **The final consolidation pass: wire a multi-dossier series into the
    central study log.** When a research cycle produces a letter-series
    dossier set (G08, G08B, G08C, ...) totaling hundreds of KB and
    dozens of evidence page images, the corpus's central study log
    (e.g. `HITCHYZ OPUS.md`, `STUDY_LOG.md`, or whatever the user
    has named it) needs a final consolidation pass before the
    research cycle is complete. Procedure: (1) add a top-of-document
    position statement as of the new revision date; (2) add a new
    "Corpus reconstruction" row to the evidence-framework table in
    the central study log; (3) insert targeted subsections at the
    existing relevant sections (e.g. philalethes, newton, chronology,
    mercury vocabulary) that summarize the new findings in 100-200
    words each; (4) add a "claims removed" entry for any
    newly-disproven claim (e.g. "R01 = the Helvetius 1666 recipe");
    (5) add new §N section that consolidates the dossier series
    (file-by-file table + the new findings in 5-10 bullets + tier
    discipline applied); (6) add a §N+1 standing-position section
    that restates the central question's answer in 3-5 paragraphs;
    (7) update WORK_LOG and DATA INDEX with one dated entry per
    dossier. The central study log is the spine; the dossier series
    is the muscle; the user has to be able to read the central log
    and know the standing position. Without the consolidation pass,
    the dossier series sits beside the central log unread, and the
    standing position drifts. The OPUS-style spine of a research
    corpus cannot be "append-only" once a major dossier cycle lands
    — it must be revised, not just extended.

6f. **Tier discipline applies to N-gate recipe audits, not just to claims.**
    When a dossier uses a multi-gate audit framework (e.g. 4-gate
    recipe: textual identification / recipe identification / material
    identity / independent reproduction with mass balance), the
    standing position summary must list gate status alongside claim
    tier. "R01 stands at Gates 1-2 met, Gate 3 partial, Gate 4 not
    met" is a more useful summary than "R01 stands at FACT tier." The
    gate framework is the operationalization of "FACT vs FICTION" for
    recipe dossiers; the gate-state table replaces the single-tier
    label. When revising a central study log that has a multi-gate
    audit, the gate-state table is one of the things that should
    appear in the standing-position section.

6g. **Direct file-level analysis is the fallback when a domain-specific
    MCP tool is unavailable.** When a domain-specific MCP tool
    (e.g. a `mcp_<domain>_*` connector) is documented in a skill
    but does not resolve via `manage_connections status` /
    `tool_search` / `tool_describe`, do not loop on the missing
    tool — fall back to direct file-level analysis of the corpus
    the skill points to. The skill's `SKILL.md` typically names the
    on-disk corpus path (e.g. `C:\Users\KING\Documents\ADVANCED
    RESEARCH\ocr_full\`); that path is the durable ground truth.
    The fallback workflow is: `ls` the directory, `head -c 3000
    <file>` to read content, `grep -lic` to do binary presence
    checks, `du -sh` to confirm corpus size, then build a quick
    document-category map from the file list. This is the same
    evidence a working MCP tool would surface, gathered without
    the tool. Pair the file-level check with a catalog-fabrication
    check (see cia-research skill for the working pattern).

7. **Run a validation/correction pass before extending the graph.** After absorbing a new
   source, compare its claims against the existing knowledge graph and study log; demote or
   remove entries that the new evidence contradicts, and append a dated validation report.
   Sync the updated triples to the knowledge engine immediately so the falsification surface
   stays live.

## Recipe-parallel classification

Use this when comparing corpora for transmission. **Same vocabulary or same material ≠ same tradition.** Classify every candidate link before claiming transmission:

```
DIRECT_QUOTATION          — author names the source explicitly (Tier A, strongest)
CLOSE_RECIPE_PARALLEL     — same material + operation + sequence + diagnostic
TECHNICAL_MOTIF           — same operation family, different context
SHARED_MATERIAL_ONLY      — same substance, different role → NOT transmission evidence
SHARED_OPERATION_ONLY     — same action, different material/purpose → NOT transmission evidence
NO_DEMONSTRABLE_RELATION  — no lexical + procedural chain exists
```

Build the candidate list, then **actively hunt the false positives** (the mandatory "collapses under scrutiny" category). A 25-candidate list should produce real discards; none collapsing is a red flag that thresholds are too loose.

## Duration-regime test

Multi-corpus duration comparison protocol (the 2520 lesson):
1. Extract every duration from every corpus, preregister the transforms (candidate constant
   K, 360, 365, 12×30, GCD, random×200 baseline).
2. Score exact-divisibility per model over ALL values; a model that fits only the sacred
   scaffold values and misses the empirical ones is a frame, not a law.
3. Compare K against its simpler factors — 360×7 must beat plain 360 to earn the extra term,
   otherwise demote to "360-family arithmetic".
4. Two corpora with the same author but different notebooks (e.g. Newton Add. MS 3973 vs
   3975) can carry different duration ceilings — check both before concluding a regime.

When comparing time/statements across corpora, don't just bucket values — ask *what kind of number each is*:

- **Sacred/round** (30, 40, 90, 150, 360-multiples) vs **empirical** (41, 46, 5 minutes, 2 days). Non-round values are stronger evidence of actual observation than round ones, which tend to be calendrical scaffold.
- **Multiple disjoint regimes** (e.g. 1h–30d in papyri, 5min–2d in Newton's bench, 40–150d in Philalethes) are *separate registers*, not one lineage. A claimed continuity requires durations to fall in overlapping ranges on the same operations.

## Pitfalls

- **Run the closing self-audit before reporting completion.** Verify file presence, JSON
  validity, record counts against the log, and re-run headline counts (motif counts,
  duration ranges) over the corpus text itself. Full procedure in
  `references/corpus-verification-audit.md`. If a subagent dies after pulling raw sources to
  disk, finish the extraction locally from those files rather than re-dispatching — the
  network payload is the expensive step and the regex pass is cheap.
- **Treat a dated lab notebook as bench evidence and a published treatise as doctrine.**
  A writer's notebook (grain-weighed entries, one-variable A/B ratio tests, hour-scale
  durations) can flatly diverge from their treatise — split them into separate corpora and
  compare durations/operations before equating reading with practice. Cross-check sister
  manuscripts too: the same author's second notebook may carry a different duration ceiling.
- **The corpus's strongest contemporary critic is often in the archive unmapped.** When
  the user asks for "FACT vs FICTION" or "knowledge is key", the durable evidence move
  is to *search the existing corpus for the contemporary critic* of the doctrine under
  study, not to hunt for external counter-arguments. The critic's text typically sits
  in the archive tagged by acquisition order or by a generic label ("Boyle", "modern
  chemistry") rather than by its actual role as the corpus's strongest counter-witness.
  Locate it via the corpus's directory search, read it for direct attacks on the
  corpus's own theoretical framework, and surface it as counter-evidence. The audit
  does not need to be exhaustive — a single primary source from the contemporary critic
  is more valuable than ten secondary critiques from the 20c.
- **The 17c alchemical "two-tier recipe" structure.** Most 17c alchemical texts
  (Helmont 1662, Philalethes, Basilius Valentinus) explicitly distinguish a
  "middle way" or "spagyric" recipe (for ordinary readers) from the true Adept
  recipe (for the elite). Authors state this in plain prose ("I will unfold a
  middle way... Take of clear Aloes, of the Best Myrrhe..."). The two-tier
  structure is the *standard* form, not an aberration, and it affects how to
  read any alchemical text: a single primary source is rarely the Adept recipe,
  it is usually the middle-way recipe, and the Adept recipe must be reconstructed
  by comparing multiple primary sources. When auditing, mark which tier each
  cited recipe is.
- **OCR errors on the title page are a routine source of citation mistakes.** A
  17c printed title page with hand-set type, ligatures, italics, and
  ornamentation is a poor OCR target — the publisher's name and the place of
  publication are the highest-value identifier on the page and the most likely
  to be misread. *Render the title page at 200 DPI and vision-verify the
  publisher and city of every primary source in the corpus* before citing it.
  OCR-only title-page reads are a fabrication-risk surface for the
  bibliography. A render + vision-verify takes seconds and prevents catalog
  errors that propagate through every subsequent citation.
- **The "primary in original language + English (or modern) translation" pattern
  is a free corroboration.** When the same case appears in the corpus twice —
  e.g. the 1667 Latin Helvetius *Vitulus Aureus* (P30) and the 1670 English
  translation *The Golden Calf* (P23), or the 1888 French Berthelot *Collection
  des anciens alchimistes grecs* and the 1889 French *Introduction à l'étude de
  la chimie des anciens* — the two are independent publications. Same
  case, different language, different publisher imprint, different city. The
  cross-language corroboration confirms the case was widely known and not a
  19c fabrication. The pattern: *pair the primary-language source with the
  English (or modern-language) translation and read both*; the publisher
  network (city + publisher) becomes a separate corroboration channel.
- **Modern institutional witnesses are a distinct evidence class from primary
  sources.** An academic project that has digitized, transcribed, and sometimes
  *experimentally reproduced* the corpus's recipes is more valuable than a 20c
  scholarly monograph *about* the recipes. Examples: the Newton Chymistry
  Project (Indiana University) has digitized Newton's alchemical papers and
  reproduces some experiments; Marchini et al. 2022 (PNAS) reproduces ancient
  mercury recipes; the Wellcome Collection hosts a 19c scholarly edition.
  When building an evidence dossier, list institutional witnesses (project
  name, host institution, scope, URL) as a separate category from primary
  sources. A institutional witness that has reproduced the recipe in a modern
  lab is the highest-value corroboration short of independent analytical
  verification.
- **When the user says "KEEP COLLECTING" / "KEEP BUILDING" / "continue" with
  no other direction, mine the corpus for unmined material instead of asking
  for scope.** The pattern: identify the most relevant unmined source class
  (Latin primary in original language, modern institutional witness,
  non-Western parallel tradition, contemporary critic), pick one per turn,
  extract the headline evidence, render the title page or key passage at 200
  DPI for vision verification, and write a numbered letter-series dossier
  (G08B, G08C, G08D, G08E) before the next turn. Do not ask "what next?" —
  decide and execute. The user has signalled open-ended continuation; the
  trust granted is to *use* it, not to surface it back as a question.
- **When OCR has lost printed-page numbers, render the PDF and vision-check instead of
  trying to map OCR line numbers back to pages.** Page-number recognizers fail on old
  multi-section books, on books with non-paginated sections, and on books with multiple
  pagination schemes (e.g. a Sammelband with a foreword paginated separately). The
  durable technique is: search the PDF text directly for the term (`page.search_for` over
  every page), then render those pages at 200 DPI with PyMuPDF and vision-verify. The
  OCR line number is unreliable as a page anchor; the PDF page number is reliable.
  See `references/pymupdf-page-anchoring.md` for the working pattern.
- **Install PyMuPDF into the durable agent venv, not an ad-hoc cwd.** `uv run --with
  pymupdf` and `uv pip install --target /tmp/x` both fail on Windows because ad-hoc cwds
  get auto-cleaned. The durable install is `python -m pip install pymupdf` against
  `AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`; then `import pymupdf`
  from execute_code works across sessions.
- **When a corpus author explicitly compares two routes and deprecates one, capture the
  comparison verbatim and record the author's stance.** The source-critical gold is the
  author's own evaluation, not a modern interpretation. Patterns to look for: "tedious
  labour" + failure rate, "the other way which is most secret", "I never yet tried it",
  "some use X but the better way is Y". A two-route structure in the corpus is itself
  a finding — the author has a preferred practice distinct from a known alternative, and
  that distinction is evidence about both routes.
- **The "I never yet tried it" pattern: hearsay tier, not personal-report tier.** When
  a corpus author explicitly says they have not tested an alternative method, that
  alternative is hearsay even if it appears in the same book. Demote it: the author is
  reporting others' claims, not their own bench experience. Mark the unverified route
  separately in any audit; do not lump it with the author's attested procedure.
- **When the same operation appears in both verse and prose forms, the verse is the
  literary surface and the prose is the operational core.** 17c alchemical verse
  (Marrow, Ripley) is consistent in operational details with the prose notebooks
  (Starkey MS 13, Three Tracts) but introduces an interpretation layer. Treat the verse
  as a translation target, not as the primary source; map each verse passage to its
  prose equivalent before counting operations.
- **Preserve OCR-era spellings verbatim in transcriptions.** Arsnick, Arfnick, fo (for
  so), loe (for lo), ftanza, &c. are not OCR errors to fix — they are 17c English and
  they are evidence. A normalized transcription that silently corrects "Arsnick" to
  "Arsenic" loses the etymological signal that the author was thinking of a specific
  arsenic compound (realgar/orpiment), not the modern element. Quote original spelling
  with a normalization note, never instead of.
- **Apply the 4-gate recipe audit (Gates 1-4) per candidate dossier.** Gate 1:
  8 critical fields populated, unknowns explicit. Gate 2: ≥2 verified passages,
  discrepancies reconciled, procedure reconstructable. Gate 3: material identity
  supported by analytical or strong contextual evidence, alternatives recorded. Gate 4:
  effect demonstrated by independent reproduction with controls, mass balance, and
  independent quantitative analysis. A dossier at Gates 1-2 with Gate 3 partial and
  Gate 4 unmet is the standard state for historical alchemy — do not treat Gate 3
  partial as failure; it is the calibration point that defines what independent
  reproduction would have to do.
- **Unicode filenames break naive open()** (e.g. `"Lumière"`) — glob and case-insensitive
  match rather than hardcoding paths.
- **Subagents on a rate-limited cloud provider die mid-task with HTTP 429.** Dispatch them
  with partial-file persistence (each batch appended to disk as it lands); if a subagent
  dies after pulling its raw sources, finish the extraction locally from those files rather
  than re-dispatching — the network payload is the expensive step, the regex pass is cheap.
- **Wikisource pages are often stubs** — verify extracted length >10KB before statistics;
  fall back to the published translation (e.g. archive.org djvu text).
- **Stats over boilerplate** — stripped HTML retains nav/footer noise; cut to content region
  or motif counts get polluted.
- Avoid searching for historical 'claims' or 'successes'; they are subjective overlays. Search technical logs specifically for 'assay error', 'imbalance', or 'unexplained weight change'.
- **Archive.org detail-page 'Download' buttons are UI entry points, not direct file URLs.**
  They often route through printdisabled or encrypted access. Enumerate files via
  `https://archive.org/metadata/<item>` and test `https://archive.org/download/<item>/<file>`;
  if OCR text streams return 401, fall back to the public-domain PDF or to browser capture
  of the transcription reader.
- **Preview-host sites (pdfroom, vdoc.pub, etc.) wrap downloads behind forms or obfuscated JS.** Their visible page text is often more accessible than their PDF link; capture the preview text with the browser or by saving the HTML wrapper and stripping tags. Treat these previews as partial sources and mark them "preview only" in the corpus metadata.
- **Pre-formed pastes that enumerate document IDs almost always mix real and fabricated identifiers.** A pasted catalog of N "CIA declassified" or "primary source" references, especially when styled with confident descriptors and grouped under a single topic heading, is a fabrication-risk surface — real document IDs from the same record group coexist with plausible-sounding siblings that resolve to nothing. Verify every cited identifier against the live indexed catalog (e.g. `/readingroom/search/site/<ID>` for CIA FOIA, or `metadata/<item>` for archive.org) before downloading or citing it. A 302 redirect to the catalog home is a fabrication flag, not a "try a different mirror". Track each verified/unverified ID in the corpus provenance record; promote none to load-bearing evidence without an indexed catalog hit.
- **Preview-host sites (pdfroom, vdoc.pub, etc.) wrap downloads behind forms or obfuscated JS.** Their visible page text is often more accessible than their PDF link; capture the preview text with the browser or by saving the HTML wrapper and stripping tags. Treat these previews as partial sources and mark them "preview only" in the corpus metadata.
- **Pre-formed pastes that enumerate document IDs almost always mix real and fabricated identifiers.** A pasted catalog of N "CIA declassified" or "primary source" references, especially when styled with confident descriptors and grouped under a single topic heading, is a fabrication-risk surface — real document IDs from the same record group coexist with plausible-sounding siblings that resolve to nothing. Verify every cited identifier against the live indexed catalog (e.g. `/readingroom/search/site/<ID>` for CIA FOIA, or `metadata/<item>` for archive.org) before downloading or citing it. A 302 redirect to the catalog home is a fabrication flag, not a "try a different mirror". Track each verified/unverified ID in the corpus provenance record; promote none to load-bearing evidence without an indexed catalog hit.
- **A symbol/glossary definition can contradict a body passage by the same author** —
  record both as a textual variant with passage refs; do not flatten one into the other.
- **A claimed key term can have ZERO hits in the primary corpus while the modern group's
  chat uses it 100+ times** — that ratio is the quantified answer to "did the adepts hold
  this doctrine or is the group projecting it." Always dump per-source term counts before
  asserting a term is central to an author's system; co-occurrence with many different
  candidate materials means the term is a relational label, not a fixed referent.
- **Reviewer-driven falsification tests must run mechanically, not rhetorically** — for a
  numeric pattern, preregister transforms (candidate constant vs simpler baselines vs
  random×200), score against ALL extracted values (no cherry-picks), and report the baseline
  comparison. A hypothesis that beats random but loses to a simpler baseline is demoted to
  its simpler frame.
- **Reframe the question away from "is there a hidden process" to "what material phenomena
  recur independently across traditions."** Recurrence-without-symbolic-continuity is the
  falsification-resistant object; a modern replication paper (experimentally reproducing an
  ancient recipe) is the highest-value external witness for it — search for one before
  asserting any recipe physically works.

## Output shape

Chaptered study-log markdown, table-dense, section-numbered, plus the machine corpus files.
End each session with: what shipped, what the data proved, what got downgraded, next
executable step. Aggressive autonomous execution is the standing preference — build, test,
report; don't stop to narrate options. **Before closing, run the verification self-audit
(references/corpus-verification-audit.md) so headline claims re-verify against the files,
not memory.**

For the dossier-series convention (G08, G08B, G08C...): each letter is a self-contained
dossier in a single dated folder, with its own evidence pages subdirectory, its own
patched WORK_LOG entry, and its own patched DATA INDEX entry. Standing-position section
in each dossier lists the FACT / STRONG INTERPRETATION / UNPROVEN claims explicitly
under a "Standing position (final, after [dossier name])" heading, so a reader scanning
the dossier series in order can read the standing position evolve.
