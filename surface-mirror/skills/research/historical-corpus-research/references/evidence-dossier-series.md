# Evidence Dossier Series — Convention and Patterns

A reusable structure for "KEEP COLLECTING" / "KEEP BUILDING" open-ended evidence
directives. Use when the user signals open-ended continuation of an evidence-collection
program and there is no specific next task. The convention is class-level; it scales
to any topic where evidence comes in waves and tier discipline is required.

## When to use

- The user has asked for "KEEP COLLECTING EVIDENCE", "KEEP BUILDING", or similar.
- The corpus has an existing dossier (e.g. G08) and the next step is to add more.
- A working dossier folder already exists (e.g. `research-20261017-g08/`).
- The user has asked for "FACT vs FICTION" or "separate fact from interpretation" and
  the deliverable should be readable by a non-specialist.

## Folder layout

```
research-YYYYMMDD-<topic>/
├── <topic>_DOSSIER.md          # G08, G08B, G08C... self-contained
├── evidence/                    # rendered page images at 200 DPI
│   ├── pnas-si-p1.png
│   ├── valentine-p7-title.png
│   └── ...
└── ...

project-control/
├── WORK_LOG.md                  # append-only, one entry per dossier
└── DATA INDEX.md (or equivalent) # append-only, one entry per dossier
```

The folder date is the date the dossier series starts; subsequent dossiers in the
series use the same folder. The dossier letter (`B`, `C`, `D`...) is sequential.

## Dossier structure

Each letter-series dossier follows the same skeleton:

1. **Bibliographic data** (visually verified title, author, publisher, date, repo location)
2. **Why this is tier-1 evidence** (one paragraph: what the source adds that was missing)
3. **Key findings** (verbatim quotes from the source, with page references)
4. **Tier discipline** (FACT / STRONG INTERPRETATION / UNPROVEN applied to every claim)
5. **Visual evidence** (paths to rendered page images in `evidence/`)
6. **Updated standing position** ("Standing position (final, after [dossier name])")
7. **Files written this turn** (paths to new files)

## Tier discipline for the user, not just the corpus

Apply the three-tier convention (FACT / STRONG INTERPRETATION / UNPROVEN) as a per-claim
label in plain prose. Each evidence section of the deliverable carries explicit tier
labels so the user can read the document and know what is established vs. what is
interpretation vs. what is unproven.

Example structure:

```markdown
### Tier discipline

- **FACT (documented, not in dispute):** The alchemical recipes are real chemistry
  (Marchini 2022 PNAS reproduces them). The corpus has 22+ named authors across 2,200
  years. The corpus's transmutative claims are unverified.
- **STRONG INTERPRETATION (well-supported but not certain):** The corpus's R01
  Sophick Mercury is a 17c innovation, not a 14c Latin recipe. The corpus's R02
  Mirror is more faithful to the 14c Latin tradition.
- **UNPROVEN (cannot be established from the corpus alone):** Transmutation of base
  metals into gold. The corpus describes it, the alchemists believed in it, but no
  modern analytical verification exists.
```

The internal confidence codes used in the corpus's source-criticism are for the
corpus; the three-tier prose labels are for the reader.

## The plain-English dossier

When the user asks for "translate it into plain English" or "anyone can understand
this mess", produce a dedicated plain-English dossier in addition to the source-critical
technical version. Same evidence, same citations, but:

- Every specialist term is explained inline (what is "the Eagle operation", what is
  "Sulphur-Mercury-Salt theory", what is a "drachm").
- Tier discipline is applied to every claim in the body, not relegated to an appendix.
- The plain-English dossier is not a summary — it is a parallel re-presentation of
  the same evidence at a non-specialist reading level.
- A reader with no prior knowledge of the topic should be able to read it and
  understand what the corpus says and what the standing position is.

The plain-English dossier is the one to send to a non-specialist (a journalist, a
lawyer, a general audience). The source-critical technical version is the one to
send to a specialist (a chemist, a historian of science).

## When the user says "KEEP COLLECTING" with no further direction

1. **Identify the most relevant unmined source class.** Candidates: Latin primary
   in original language, modern institutional witness, non-Western parallel
   tradition, contemporary critic, scholarly edition.
2. **Pick one per turn.** Do not batch multiple sources in one dossier; one source
   class per letter-series dossier.
3. **Extract the headline evidence.** Visually verify the title page, render the
   key passages at 200 DPI, run the keyword counts.
4. **Write the dossier.** Apply tier discipline. Update the standing position.
5. **Patch WORK_LOG and the DATA INDEX.** One entry per dossier, dated.
6. **End the turn with a brief summary** (a few bullets, the new dossier paths,
   the updated standing position).

Do not ask "what next?" — decide and execute. The user has signalled open-ended
continuation; the trust granted is to *use* it, not to surface it back as a question.

## Source-class candidates (worked examples from a real dossier series)

The following source classes repeatedly produced tier-1 evidence in a real
dossier series on historical alchemy. They generalize to any topic with a
historical primary-source corpus:

- **Primary in original language + English translation.** Same case, different
  language, different publisher imprint, different city. Cross-language
  corroboration is a free verification channel.
- **Modern institutional witness.** A current academic project that has
  digitized, transcribed, or experimentally reproduced the corpus's recipes
  (Newton Chymistry Project at Indiana University, Marchini 2022 PNAS at
  Bologna, Wellcome Collection). The institutional witness that has reproduced
  the recipe in a modern lab is the highest-value corroboration short of
  independent analytical verification.
- **Contemporary critic.** The corpus's strongest 17c critic often sits in
  the archive unmapped, tagged by acquisition order rather than by its actual
  role as counter-evidence. Search the existing corpus for the contemporary
  critic; the search is faster than the discovery.
- **Non-Western parallel tradition.** If the topic is European alchemy, the
  Indian *rasayana* tradition is a parallel; if the topic is European medicine,
  the Chinese or Arabic tradition is a parallel. Recurrence-without-symbolic-
  continuity is the falsification-resistant object.
- **19c scholarly edition.** A 19c edition by a modern scholar (Berthelot,
  Waite, Newman, Ray) is a different kind of evidence — modern re-presentation,
  not primary source — but is invaluable for the OCR-corrected text and the
  modern editorial apparatus.

## The standing-position section (always)

Every dossier ends with a "Standing position (final, after [dossier name])" section
that lists FACT / STRONG INTERPRETATION / UNPROVEN explicitly. The section is
cumulative: a later dossier's standing position is built on the previous dossier's
standing position plus the new evidence, not a rewrite. A reader scanning the
dossier series in order can read the standing position evolve.

## Pitfalls

- **Don't let the dossier series grow without bound.** Each dossier should be
  self-contained and add a distinct source class. If the next dossier would only
  add more examples of the same source class as the previous, the series has
  reached a natural stopping point — write a "synthesis dossier" instead that
  reads across the existing dossiers and updates the standing position.
- **Don't skip the visual verification step.** Every primary source in a
  dossier should have at least one rendered page image at 200 DPI that has
  been vision-verified. The render + verify takes seconds and prevents
  catalog errors that propagate through every subsequent citation.
- **Don't mix evidence types in one dossier.** A counter-evidence dossier
  (G08C) and a primary-source dossier (G08D) should be separate letters in
  the series, not combined. Each letter is one source class.
- **Don't rewrite earlier dossiers in the series.** Append, never rewrite. If
  a new dossier contradicts an earlier one, write a correction dossier (e.g.
  G08-CORRECTION) and patch the standing position in the WORK_LOG and DATA
  INDEX. Earlier dossiers in the series are historical record.
