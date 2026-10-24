# Latin and Early-Modern Collation Procedure

When a corpus has both a Latin primary source (e.g. *Speculum Alchemiae*, *Vitulus Aureus* 1667) and one or more English translations (1670 English, *Hermetic Museum* version, Waite 1896, etc.), the **Latin is authoritative**. The English translations are evidence of how the text was *received*; the Latin is evidence of what the text *said*. The two can diverge in ways that change the meaning — and any modern recipe identification that depends on a flawed English reading is built on a wrong foundation.

## When to collate

- A 17c witness case has both a Latin original and an English translation in the corpus (e.g. Helvetius *Vitulus Aureus* Latin 1667 + English 1670).
- The English translation's wording is ambiguous or contested (e.g. "and" vs. "or"; "metals" vs. "minerals").
- A recipe identification depends on a specific English reading and would change if the Latin said something different.
- An external prompt or pasted analysis has flagged a wording question that only the Latin can settle.

## Procedure

### Step 1 — Locate the Latin primary source

Identify the file path of the Latin original. Common corpus locations:

- `research-expansion-20261006-c/sources/P30_*.pdf` (Helvetius Latin 1667, Amsterdam)
- `research-expansion-20261006/sources/P19_*.pdf` (Berthelot Greek Alchemists, Paris 1888)
- `research-expansion-20261006/sources/P20_*.pdf` (Berthelot *Les Origines de l'Alchimie*, Paris 1885)
- `research-expansion-20261006/sources/P24_*.pdf` (Berthelot *Introduction à l'étude de la chimie des anciens*, Paris 1889)

If the Latin original is not in the corpus, **acquire it before collating**. Do not collate against a Latin text not in the corpus.

### Step 2 — Identify the target passage

From the English translation, locate the page/folio and the equivalent Latin passage. The English translation usually has running headers, chapter numbers, or other anchors that pin the passage to a specific leaf. For Helvetius *Vitulus Aureus* 1667, the chapter numbers in the 1670 English map to chapter numbers in the Latin, and within each chapter the leaves are sequential.

### Step 3 — Extract Latin text via PyMuPDF

Use PyMuPDF page-level extraction (not raw `pdftotext`) because:

- PyMuPDF preserves reading order
- `pdftotext` output can scramble line breaks that hide the running text
- Page numbers in PyMuPDF map 1:1 to PDF leaves, which is what the file path's "p<NN>" suffix records

```python
import pymupdf
pdf = pymupdf.open("path/to/LATIN.pdf")
for p in range(len(pdf)):
    text = pdf.load_page(p).get_text()
    # search for the keyword
    if 'targetword' in text.lower():
        # render this page at 200 DPI for visual verification
        pix = pdf.load_page(p).get_pixmap(matrix=pymupdf.Matrix(200/72, 200/72))
        pix.save(f"evidence/latin-p{p+1}-<topic>.png")
```

### Step 4 — Render at 200 DPI for visual verification

`vision_analyze` the rendered page to confirm what the OCR/extract actually says. The visual check catches:

- Long-s `ſ` misread as `f`
- `u/v` interchange (e.g. *Metalla* may appear as *Mctalla* in some lines)
- Ligature expansion errors (`æ` → `ae`, `œ` → `oe`)
- Catchwords (line-isolated integers) misidentified as page anchors
- Ink bleed-through from verso

The visual check is what tells you whether the Latin *says what you think it says*, not just whether the *string is present in the extract*.

### Step 5 — Apply the case-insensitive + Latinized search

Do **not** use exact modern spelling. The corpus's 17c Latin and English vocabulary was modernized over 300 years:

- *Chalybs* (1667) = *Chalybs* (modern) — stable
- *Mercurialis* (1667) = *Mercurialis* (modern) — stable
- *Philosophica* (1667) = *Philosophica* (modern) — stable
- But typesetter-dependent: *Metalla* or *Metalia* or *Metallae* depending on the press

Use `.lower()` and accept partial matches. Use Latin declension patterns (e.g. *Chalybs* may appear as *Chalybe*, *Chalybis*, *Chalybum* depending on case). If a strict `grep` for the nominative returns zero hits, try the oblique cases and visual-verify any candidate.

### Step 6 — Document the conjunction carefully

Latin conjunctions are *semantically loaded*. A wrong reading of a conjunction changes the meaning:

| Latin | Meaning | Common misreading |
|---|---|---|
| *ac* | "and" (cumulative) | read as "or" |
| *vel* | "or" (alternative) | read as "and" |
| *aut* | "or" (exclusive) | read as "and" |
| *atque* | "and also" (emphatic cumulative) | read as "and" |
| *-que* (suffix) | "and" (Latin enclitic) | often missed entirely |

The Helvetius 1667 starting-materials phrase *duo duntaxat Metalla ac Mineralia* is the canonical case: *ac* = "and", not "or". The *Hermetic Museum* English version reads "or" and is wrong. The 1670 English reads "and" and is correct.

### Step 7 — Apply tier discipline to the collation result

- **Documented:** the Latin says X (visually verified, with PDF leaf and screenshot).
- **Strong interpretation:** the 1670 English captures X correctly; the *Hermetic Museum* does not.
- **Unproven:** whether the corpus's recipe identification is consistent with X.

Do not promote "the Latin says X" to "therefore the recipe is Y" without an operational hypothesis linking the two. Per OPUS §0, *"A successful material operation, an author's explanation of it and a promised philosophers' stone are separate propositions requiring separate support."*

## What the Helvetius 1667 collation settled

The G08F Latin collation dossier for Helvetius *Vitulus Aureus* 1667 produced four decisive findings that the English translation could not:

1. **Starting materials:** *duo duntaxat Metalla ac Mineralia* — the Latin *ac* = "and" (cumulative), not "or". The 1670 English "two Metals and Minerals" is correct. The *Hermetic Museum* "or" is an error.

2. **The salt is "celestial":** *Sal quoddam caeleste, sive caelestis virtutis* — the salt is explicitly described as "celestial, or of celestial virtue", a specific alchemical concept, not table salt.

3. **The operation is in an open crucible:** *In crucibulo autem a principio ad finem usque in Igne aperto perficitur operatio* — the Latin explicitly says the operation is in an *open* fire and *open* crucible, not a sealed vessel. The corpus's R01 dossier (sealed-vessel Sophick Mercury) is operationally distinct from the Helvetius 1666 case.

4. **Sendivogius's Chalybs:** *SENDIVOGII Chalybs sit vera Mercurialis humiditas Metallica* — Helvetius defines Sendivogius's *Chalybs* as "the true Mercurial metallic humidity", a specific alchemical concept, not raw steel.

5. **Helvetius's epistemic admission:** *nullus tamen putarim à me Philosophicam Materiam ... agnoscere posse* — Helvetius explicitly states in Latin that he had read the prior alchemical authorities (Paracelsus, Helmont, Basil Valentine, Sendivogius) but could not, even in person, have recognized the Philosophic Matter. The 1666 transmutation was a piece of luck, not a recipe he possessed.

The 1670 English translation is faithful to the Latin on points 1, 3, 4, and 5; only point 2 (the "celestial" qualifier) is more emphatic in the Latin than in the English.

## Common pitfalls

- **Do not rely on `pdftotext` output alone.** It scrambles line breaks and can hide running text. Use PyMuPDF page-level extraction.
- **Do not assume OCR of old-Latin PDFs is correct.** Visual verification at 200 DPI is the only way to confirm a critical passage. `vision_analyze` is the right tool.
- **Do not use exact modern spelling in searches.** Latin and 17c English vocabulary was modernized; use case-insensitive partial matches.
- **Do not skip the conjunction.** A wrong reading of *ac/vel/aut/-que/atque* can change the meaning. The conjunction is the most load-bearing word in a Latin technical phrase.
- **Do not promote a Latin reading to a recipe claim.** "The Latin says X" is a *textual* finding; "therefore the recipe is Y" is an *operational* claim requiring a separate chain of inference.
- **Do not silently select between competing English translations.** When two English translations disagree, the Latin is the tiebreaker. Document the disagreement, then settle it.
- **The Latin is authoritative but not the only evidence.** The author's epistemic admission (point 5 above) is in the Latin, but the operational description (open crucible, open fire) is also in the Latin. Both readings matter. Treat the Latin as the source of truth *and* as evidence of the author's own limits.
