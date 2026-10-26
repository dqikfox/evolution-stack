#!/usr/bin/env python3
"""Extract the VISIBLE copy from the Lummings public site, for a brand review.

The retired-name scan finds 179 hits across the public tree, and almost all
of them are internal identifiers: a CSS class `.lila`, a filename
`lila-portrait.png`, a JS key `Lila: {`. The canon EXPLICITLY permits those
("Internal code and some legacy filenames still use lila / pip as IDs").

So a raw grep cannot answer the question the canon asks. The question is:
does the retired name appear in text a READER SEES? So this script strips
the code and keeps the prose: no CSS, no JS, no attributes, no comments.

    python extract_public_copy.py > public_copy.txt
"""
import html
import re
import sys
from pathlib import Path

L = Path("C:/Users/KING/projects/lumming")
OUT = Path("C:/Users/KING/AppData/Local/hermes/cache/scratch/lummings_public_copy.txt")

# the public-facing pages, in the order a reader meets them
PAGES = [
    "docs/index.html",
    "docs/marketing/character-codex.html",
    "docs/marketing/app-store.html",
    "docs/marketing/tomorrow-crew.html",
    "docs/marketing/heartlight-adventures.html",
    "docs/marketing/artwork-gallery.html",
    "docs/shop/index.html",
    "docs/companion/index.html",
    "docs/playground/index.html",
    "docs/demo/index.html",
    "docs/lead-magnet/free-samples/index.html",
    "docs/lead-magnet/lummings-5pk/index.html",
    "docs/lead-magnet/shiney-sampler/index.html",
    "docs/kickstarter-campaign.md",
    "docs/pre-order-campaign.md",
    "docs/press-sheet.md",
    "docs/PARENT_QUICKSTART.md",
    "docs/PRODUCT_SUCCESS_PLAN.md",
    "docs/brand-use-guidelines.md",
]

# the strings a reader actually sees
#
# `div` matters: the character cards in app-store.html put the visible name
# in `<div class="nm">LILA</div>`, and an extractor that skips `div` misses
# a retired name that is on the page, in plain sight.
VISIBLE_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
                "figcaption", "title", "span", "a", "button", "label", "td", "th",
                "dt", "dd", "strong", "em", "small", "summary", "option", "div",
                "section", "article", "hgroup", "b", "i", "u", "s", "caption",
                "hgroup", "nav", "footer", "header", "main", "aside", "bdi")

VISIBLE_RE = re.compile(
    r"<\s*(%s)\b[^>]*>(.*?)<\s*/\s*\1\s*>" % "|".join(VISIBLE_TAGS),
    re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<\s*(script|style|svg|head)\b.*?<\s*/\s*\1\s*>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
WS_RE = re.compile(r"[ \t ]+")
NL_RE = re.compile(r"\n{3,}")


def visible_text(raw: str) -> str:
    """The prose a reader sees, with the code removed."""
    t = SCRIPT_RE.sub(" ", raw)
    t = COMMENT_RE.sub(" ", t)
    parts = []
    for m in VISIBLE_RE.finditer(t):
        s = TAG_RE.sub(" ", m.group(2))
        s = html.unescape(s)
        s = WS_RE.sub(" ", s).strip()
        if s:
            parts.append(s)
    # the attribute values that ARE reader-facing
    for attr in ("alt", "title", "aria-label", "placeholder", "content"):
        for m in re.finditer(r'\b%s\s*=\s*"([^"]{3,200})"' % attr, t, re.I):
            s = html.unescape(m.group(1)).strip()
            if s and not s.startswith("http") and "{{" not in s:
                parts.append(s)
    # and the body text of a markdown file
    if not parts:
        body = TAG_RE.sub(" ", t)
        parts = [l.strip() for l in body.splitlines()
                 if l.strip() and not l.strip().startswith(("|", "#", "```", "-", "*", ">"))]
    seen = set()
    out = []
    for p in parts:
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(p)
    return NL_RE.sub("\n\n", "\n".join(out))


def main():
    blocks = []
    for rel in PAGES:
        p = L / rel
        if not p.is_file():
            blocks.append("## %s\n\n(the file is missing)\n" % rel)
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        txt = visible_text(raw)
        blocks.append("## %s\n\n%s\n" % (rel, txt if txt.strip() else "(no visible prose)"))

    body = "\n".join(blocks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    sys.stderr.write("wrote %s (%d chars, %d pages)\n"
                     % (OUT, len(body), len(PAGES)))
    print(body)


if __name__ == "__main__":
    main()
