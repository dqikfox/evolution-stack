# JS-Gated and Borrow-Walled Archive Extraction

Use this when `requests`/`curl` returns 401/403/404 for a manuscript or book that is readable
in a browser transcription reader.

## Browser capture workflow

1. Open the transcription reader URL with the browser tool.
2. Wait for load, then evaluate:
   ```python
   full_text = js('document.body.innerText')
   ```
3. Save the result as JSON with URL, title, and `total_chars`.
4. Split into pages with a regex that matches the reader's page markers, e.g.:
   ```python
   pages = re.split(r'<(\d+[rv])\u003e\s*Page Image\n+', text)
   ```
5. Score pages chemically by keyword density and extract operation-rich lines, weight strings,
   and dates for the corpus fingerprint.

## URL patterns

- **Chymistry of Isaac Newton (Indiana)**:
  - Normalized: `https://webapp1.dlib.indiana.edu/newton/mss/norm/<ALCH_ID>`
  - Diplomatic: `https://webapp1.dlib.indiana.edu/newton/mss/dipl/<ALCH_ID>`
  - Catalogue: `https://www.newtonproject.ox.ac.uk/catalogue/record/<ALCH_ID>`
- **Internet Archive**:
  - Detail page: `https://archive.org/details/<item>`
  - Metadata API: `https://archive.org/metadata/<item>`
  - Direct file: `https://archive.org/download/<item>/<filename>`
  - Text/OCR streams are sometimes printdisabled (401); use public-domain PDFs or browser
    capture of the BookReader when that happens.

## Pitfalls

- **Page markers are noise, not content.** Strip or split on `<1r> Page Image` before running
  motif counts; otherwise every page header pollutes the fingerprint.
- **`<illeg.>` and `<...>` tags are editorial, not alchemical terms.** Remove or count them
  separately; do not treat them as evidence of a symbol.
- **Blank/copyright pages dominate the page count.** Filter chemically active pages by a
  keyword score threshold before reporting "X operation-rich pages found."
- **Detail-page buttons may point to compressed/encrypted derivatives.** Always verify the
  downloaded bytes start with `%PDF` or plain text; HTML wrappers masquerade as downloads.
