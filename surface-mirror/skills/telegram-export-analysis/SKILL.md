---
name: telegram-export-analysis
description: Use when analyzing Telegram HTML chat exports.
---

# Telegram HTML Export Analysis

Telegram Desktop exports render one HTML file per ~1,000 messages: `messages.html`, `messages2.html`, `messages3.html`, ... plus `files/`, `photos/`, `images/`, `stickers/`, `video_files/`. Always glob `messages*.html` and aggregate across all of them — content is split across files.

## Procedure

1. **Inspect layout first**: `ls` the export dir; count messages per file with `grep -c 'class="message default clearfix"' messages*.html`.
2. **Inventory attachments**: `ls files/` etc. directly — PDFs/docs shared in-chat reveal what the group actually studies (often the real payload).
3. **Extract the date range**: `grep -oE 'title="[0-9]{2}\.[0-9]{2}\.[0-9]{4}' messages*.html | sort -u` (first/last). Dates are `DD.MM.YYYY`.
4. **Identify key voices**: sender names live in `<div class="from_name">` with the name on the NEXT line, so single-line grep misses them. Use Python:
   ```python
   import re, collections
   names = re.findall(r'from_name">\s*([^<]+?)\s*<', open(path, encoding='utf-8', errors='ignore').read())
   collections.Counter(names).most_common(15)
   ```
5. **Topical extraction**: `grep -ioE '[^<]{0,150}(term1|term2)[^<]{0,250}' messages*.html` — character-window context around matches (not `-C` line context): message bodies are single lines inside `<div class="text">`, so line-context returns entire mangled bodies.
6. **Follow-up passes**: one theme per pass (members, process steps, quantities/proportions, warnings, quoted sources), rarer terms each pass.
7. **Deliverable**: write a structured markdown study log INTO the export folder (user convention: named after the work, e.g. `Documents/alchemy/HITCHYZ OPUS.md`) — sections: archive overview (dates, cast, library), decoded core content, operation/process reconstruction, reading protocol, withheld/unknown items, open-threads checklist.

## Pitfalls

- Never rely on `grep from_name` single-line — names sit on the next line; use the Python regex or you'll wrongly conclude the export is anonymized.
- HTML files are 1MB+; grep/python-extract first, never read whole exports into context.
- When the user asks to "decode" a coded/esoteric corpus, separate the corpus's own teaching (what its voices claim) from verified external fact, and label which is which — do not merge lore and fact.
