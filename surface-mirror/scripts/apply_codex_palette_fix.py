#!/usr/bin/env python3
"""Align the Lummings codex page with the locked artwork, and fix the subtitle.

Two defects, both found by RENDERING the page and looking at it.

THE CHARACTER COLOURS WERE OFF-CANON. The canon (brand/BRAND_RULES_ONEPAGER.md)
gives Lumo #FF4D6D (ruby red), Luna #C77DFF (lilac), Sprout #52B788 (green),
Nori #4CC9F0 (blue) and Moki #FF85A2 (pink). The locked artwork agrees on the
hues, in its own hexes: #ed4054, #b59aff, #57db91, #75d8ef, #ff83bd - and so
does the app (docs/app/app.js) and the home page's inline SVG. The codex page
alone painted Lumo YELLOW and Nori TEAL, so the same character was red on the
home page and yellow on the codex page, and the codex page's own alt text said
"ruby-red" while the tile beside it was yellow.

The fix introduces five character variables carrying the LOCKED ARTWORK
palette, and points every character-scoped rule at them. The old colour
variables stay for the page's own accents - the hero badge and the footer
call to action - because those are not a character.

The artwork palette is much lighter than the old candy palette, so the white
text on the character tags and nav pills no longer has enough contrast
(white on #b59aff is 2.3:1). Those become the ink colour, which is 7.4:1.

THE SUBTITLE WAS ILLEGIBLE. The h1 paints a gradient clipped to its text and
a 4px ink text-shadow for a comic-sticker look. The .alt span inherited both
and then forced its own fill back to ink, so the subtitle was drawn twice,
offset, on top of itself. The gradient and the shadow now live on the
headline alone, and the subtitle is plain ink.

Every replacement is exact, and the file is only written if every one of them
lands. A half-applied stylesheet is worse than a broken one.
"""
import sys
from pathlib import Path

L = Path("C:/Users/KING/projects/lumming")
PAGE = L / "docs/marketing/character-codex.html"

# the LOCKED ARTWORK palette - the colours the portraits and the inline SVG
# actually use, which the canon's hues agree with
CHARACTER_VARS = """    /* the CHARACTER colours, from the locked artwork and the canon hues:
       Lumo ruby red, Luna lilac, Sprout green, Nori blue, Moki pink.
       The pages used to paint Lumo yellow and Nori teal, so the same
       character was two colours across the site. */
    --lumo: #ed4054;
    --luna: #b59aff;
    --sprout: #57db91;
    --nori: #75d8ef;
    --moki: #ff83bd;
"""

FIXES = [
    # --- the character variables ------------------------------------------
    ("    --pink:    #FF5CA7;\n",
     "    --pink:    #FF5CA7;\n" + CHARACTER_VARS),

    # --- the nav pills: the character, in the character's colour ------------
    ("""  nav.codex-nav a.y { background: var(--yellow); }
  nav.codex-nav a.p { background: var(--purple); color: #fff; }
  nav.codex-nav a.g { background: var(--green); color: #fff; }
  nav.codex-nav a.t { background: var(--teal);  color: #fff; }
  nav.codex-nav a.k { background: var(--pink);  color: #fff; }""",
     """  nav.codex-nav a.y { background: var(--lumo);   color: var(--ink); }
  nav.codex-nav a.p { background: var(--luna);   color: var(--ink); }
  nav.codex-nav a.g { background: var(--sprout); color: var(--ink); }
  nav.codex-nav a.t { background: var(--nori);   color: var(--ink); }
  nav.codex-nav a.k { background: var(--moki);   color: var(--ink); }"""),

    # --- the card accent stripe --------------------------------------------
    ("""  .char-card.lumo::before  { background: var(--yellow); }
  .char-card.lila::before  { background: var(--purple); }
  .char-card.pip::before   { background: var(--green); }
  .char-card.nori::before  { background: var(--teal); }
  .char-card.moki::before  { background: var(--pink); }""",
     """  .char-card.lumo::before  { background: var(--lumo); }
  .char-card.lila::before  { background: var(--luna); }
  .char-card.pip::before   { background: var(--sprout); }
  .char-card.nori::before  { background: var(--nori); }
  .char-card.moki::before  { background: var(--moki); }"""),

    # --- the avatar tile -----------------------------------------------------
    ("""  .lumo .avatar  { background: linear-gradient(135deg, #FFE17A, var(--yellow)); }
  .lila .avatar  { background: linear-gradient(135deg, #B8A8FF, var(--purple)); color: #fff; }
  .pip  .avatar  { background: linear-gradient(135deg, #6FE89E, var(--green)); color: #fff; }
  .nori .avatar  { background: linear-gradient(135deg, #5BD9C5, var(--teal)); color: #fff; }
  .moki .avatar  { background: linear-gradient(135deg, #FF8FC4, var(--pink)); color: #fff; }""",
     """  .lumo .avatar  { background: linear-gradient(135deg, #F2607A, var(--lumo)); }
  .lila .avatar  { background: linear-gradient(135deg, #C7B4FF, var(--luna)); }
  .pip  .avatar  { background: linear-gradient(135deg, #8BEBB4, var(--sprout)); }
  .nori .avatar  { background: linear-gradient(135deg, #A6E6F7, var(--nori)); }
  .moki .avatar  { background: linear-gradient(135deg, #FFB0D3, var(--moki)); }"""),

    # --- the personality tags ------------------------------------------------
    ("""  .tag.type-curious { background: var(--yellow); }
  .tag.type-story   { background: var(--purple); color: #fff; border-color: var(--ink); }
  .tag.type-brave   { background: var(--green);  color: #fff; border-color: var(--ink); }
  .tag.type-wise    { background: var(--teal);   color: #fff; border-color: var(--ink); }
  .tag.type-funny   { background: var(--pink);   color: #fff; border-color: var(--ink); }""",
     """  .tag.type-curious { background: var(--lumo);   color: var(--ink); border-color: var(--ink); }
  .tag.type-story   { background: var(--luna);   color: var(--ink); border-color: var(--ink); }
  .tag.type-brave   { background: var(--sprout); color: var(--ink); border-color: var(--ink); }
  .tag.type-wise    { background: var(--nori);   color: var(--ink); border-color: var(--ink); }
  .tag.type-funny   { background: var(--moki);   color: var(--ink); border-color: var(--ink); }"""),

    # --- the stat bars -------------------------------------------------------
    ("""  .lumo  .stat .bar > span { background: var(--yellow); }
  .lila  .stat .bar > span { background: var(--purple); }
  .pip   .stat .bar > span { background: var(--green); }
  .nori  .stat .bar > span { background: var(--teal); }
  .moki  .stat .bar > span { background: var(--pink); }""",
     """  .lumo  .stat .bar > span { background: var(--lumo); }
  .lila  .stat .bar > span { background: var(--luna); }
  .pip   .stat .bar > span { background: var(--sprout); }
  .nori  .stat .bar > span { background: var(--nori); }
  .moki  .stat .bar > span { background: var(--moki); }"""),

    # --- the headline: the gradient belongs to the headline alone -------------
    ("""  .hero h1 {
    font-size: clamp(40px, 7vw, 84px);
    line-height: .95;
    background: linear-gradient(135deg, #FFD23F 0%, #FF5CA7 45%, #7B5CFF 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-shadow: 4px 4px 0 var(--ink);
    letter-spacing: -1px;
    transform: rotate(-2deg);
  }
  .hero h1 .alt {
    display: block;
    transform: rotate(3deg);
    font-size: .5em;
    margin-top: 8px;
    color: var(--ink);
    -webkit-text-fill-color: var(--ink);
  }""",
     """  .hero h1 {
    font-size: clamp(40px, 7vw, 84px);
    line-height: .95;
    letter-spacing: -1px;
    transform: rotate(-2deg);
  }
  /* The gradient and the comic shadow belong to the HEADLINE. They used to
     sit on the h1 itself, and the .alt span inherited both while forcing
     its own fill back to ink - so the subtitle was drawn twice, offset, on
     top of itself, and could not be read. */
  .hero h1 .ttl {
    background: linear-gradient(135deg, #FFD23F 0%, #FF5CA7 45%, #7B5CFF 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-shadow: 4px 4px 0 var(--ink);
  }
  .hero h1 .alt {
    display: block;
    transform: rotate(3deg);
    font-size: .5em;
    margin-top: 8px;
    color: var(--ink);
    -webkit-text-fill-color: var(--ink);
    text-shadow: none;
  }"""),

    # --- the markup: give the headline its own element -----------------------
    ("""  <h1>
    MEET THE LUMMINGS
    <span class="alt">Five tiny creatures. Big personalities. From a brighter tomorrow.</span>
  </h1>""",
     """  <h1>
    <span class="ttl">MEET THE LUMMINGS</span>
    <span class="alt">Five tiny creatures. Big personalities. From a brighter tomorrow.</span>
  </h1>"""),
]


def main() -> int:
    text = PAGE.read_text(encoding="utf-8", errors="replace")
    problems = []
    for old, new in FIXES:
        c = text.count(old)
        if c != 1:
            problems.append("found %d times, expected 1: %r" % (c, old[:70]))
            continue
        text = text.replace(old, new)
        print("   ok: %s" % (old.splitlines()[0].strip()[:64]))

    if problems:
        print("\n=== NOT WRITTEN ===")
        for p in problems:
            print("   %s" % p)
        return 1

    PAGE.write_text(text, encoding="utf-8")
    print("\n   every fix landed exactly once, and the page is written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
