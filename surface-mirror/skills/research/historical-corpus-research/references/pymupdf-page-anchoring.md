# PDF Page-Anchoring When OCR Has Lost the Page Numbers

## When to use

Use this when a target passage's printed-page number is unknown OR when the OCR's
page-anchor numbers don't match the printed page numbers. Typical signals: the OCR has
catchword numbers that look like page numbers, the book has multiple paginations, the
metadata file (e.g. `page_numbers.json`) only covers the first N pages, or you're
about to map OCR line numbers to PDF pages and the math doesn't add up. The technique is
also the right first move when you have a target term (e.g. "Eagle", "Sophick Mercury")
and want to find every page that mentions it without depending on the OCR's
search-and-find.

Skip it when the OCR is reliable and the page anchors are obvious (most modern reprints,
single-section books, well-curated archives).

## Why OCR line numbers are unreliable page anchors

OCR text files often retain *some* numeric markers — but they can be:
- Catchwords (first word of next page) that happen to be short and look like page numbers
- Section numbers, not page numbers (e.g. "4" inside "Gate 4")
- Auto-generated metadata, not the printed page
- Stale from a different edition's page numbering

A 200-DPI PyMuPDF page render with vision_check is the durable ground truth.

## Procedure

### 1. Locate candidate pages by direct text search of the PDF

```python
import pymupdf
pdf = pymupdf.open("path/to/file.pdf")
hits = []
for p in range(len(pdf)):
    text = pdf.load_page(p).get_text()
    if "your_term" in text.lower():
        hits.append((p+1, text.lower().count("your_term")))
print(f"Pages mentioning 'your_term': {len(hits)}")
for p, n in hits[:20]:
    print(f"  p{p} ({n}x term): ...")
```

PDF page numbers (1-indexed) are reliable. They are the page's position in the file,
which is the same thing `pymupdf` returns as the 0-indexed page object index.

### 2. Render the candidate pages at 200 DPI

```python
import pymupdf, os
out_dir = "evidence"
os.makedirs(out_dir, exist_ok=True)
for p, fname in [(133, "pdf133-page-133.png"), (471, "pdf471-page-471.png")]:
    page = pdf.load_page(p - 1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(200/72, 200/72))
    pix.save(os.path.join(out_dir, fname))
```

200 DPI is the sweet spot for vision verification — readable enough to confirm specific
17c spellings, light enough to fit multiple pages in a single vision_analyze call.

### 3. Vision-check each rendered page

Ask for verbatim text including OCR-era spellings and the printed page number visible
on the rendered page. The printed page number on the page is the ground truth
("p. 396", "fol. 22r", etc.); the PDF page number is the positional reference.

### 4. Build the printed-page → PDF-page map from vision checks

| Printed page | PDF page | Eagle content |
|--------------|----------|---------------|
| 50 | 124 | (no Eagle) |
| 58 | 132 | "by seven Eagles, which are seven Cohobations..." |
| 258 | 332 | "7 or 9 most desiredly" |
| 296 | 370 | "I never yet tried it [the 4-Eagle alternative]" |
| 397 | 471 | "EVERY single preparation of the Mercury with its Arsnick is one Eagle" |

## Common pitfalls

- **Do not trust the OCR's single-digit numbers as printed page numbers.** They are usually
  catchwords, line counts, or section markers. A vision check confirms in seconds.
- **Render at 200 DPI minimum.** 150 DPI is too coarse for 17c type; 300 DPI is fine but
  produces 4x the file size. 200 DPI balances clarity and size.
- **A page that vision-renders as mostly ink-bleed or foxing is unreadable.** Mark it
  "unreadable" in the dossier; do not transcribe from the OCR for that page. Other pages
  in the same section may be readable.
- **Page-number recognizers from the PDF metadata (e.g. IA's page_numbers.json) often
  fail on books with multiple paginations.** The visible printed page on the rendered
  image is the source of truth.
- **When a printed page contains a critical passage, render both the recto and verso**
  (the page before and after) — the verso often has the continuation or a related passage
  that the OCR didn't capture.

## When this technique is overkill

- The OCR has reliable printed page numbers (most modern reprints, single-section books).
- The corpus has a vetted metadata file with printed-page → leafNum mappings (e.g. IA's
  `page_numbers.json` for well-OCR'd books).
- The target passage is short and the OCR's surrounding context is enough to disambiguate.

## Install / environment

PyMuPDF is the only dependency. Install into the durable agent venv:

```bash
# Linux/Windows agent venv:
python -m pip install pymupdf
```

`uv run --with pymupdf` and `uv pip install --target /tmp/x` both fail on Windows for
ad-hoc cwds. The durable install is into the agent venv. Once installed, `import pymupdf`
from execute_code works across sessions.
