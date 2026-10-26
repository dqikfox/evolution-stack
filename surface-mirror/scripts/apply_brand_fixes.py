#!/usr/bin/env python3
"""Apply the verified Lummings brand fixes.

Every replacement here was first confirmed against the real file by a
three-provider review (Anthropic 11 findings, xAI 6, the local 3090 3) and
then re-verified by hand. A replacement that does not find its target
EXACTLY is a hard error: the file is not written, so a drifted source can
never be silently half-fixed.

    python apply_brand_fixes.py
"""
import subprocess
import sys
from pathlib import Path

L = Path("C:/Users/KING/projects/lumming")

# (file, old, new, expected_count)
FIXES = [
    # --- the retired names in visible text -------------------------------
    ("docs/playground/index.html",
     "<small>STORY</small>LILA", "<small>STORY</small>LUNA", 1),
    ("docs/playground/index.html",
     "<small>BRAVE</small>PIP", "<small>BRAVE</small>SPROUT", 1),
    ("docs/playground/index.html",
     "name:'LILA'", "name:'LUNA'", 1),
    ("docs/playground/index.html",
     "name:'PIP'", "name:'SPROUT'", 1),

    ("docs/marketing/character-codex.html",
     "<h2>LILA</h2>", "<h2>LUNA</h2>", 1),
    ("docs/marketing/character-codex.html",
     "<h2>PIP</h2>", "<h2>SPROUT</h2>", 1),
    ("docs/marketing/character-codex.html",
     "THINGS KIDS LOVE ABOUT LILA", "THINGS KIDS LOVE ABOUT LUNA", 1),
    ("docs/marketing/character-codex.html",
     "THINGS KIDS LOVE ABOUT PIP", "THINGS KIDS LOVE ABOUT SPROUT", 1),

    ("docs/marketing/app-store.html",
     '<div class="nm">LILA</div>', '<div class="nm">LUNA</div>', 1),
    ("docs/marketing/app-store.html",
     '<div class="nm">PIP</div>', '<div class="nm">SPROUT</div>', 1),

    # --- the role labels: the canon roles, not a game taxonomy -----------
    ("docs/marketing/character-codex.html",
     "TINKER CLASS", "PLAYER ONE", 1),
    ("docs/marketing/character-codex.html",
     "BARD CLASS", "SPOOKY POET", 1),
    ("docs/marketing/character-codex.html",
     "SOLDIER CLASS", "SPEED DEMON", 1),
    ("docs/marketing/character-codex.html",
     "ORACLE CLASS", "COSMIC WEIRDO", 1),
    ("docs/marketing/character-codex.html",
     "JESTER CLASS", "CHAOS GREMLIN", 1),
    ("docs/marketing/tomorrow-crew.html",
     "<h3>The Sprout Scout</h3>", "<h3>The Speed Demon</h3>", 1),

    # --- the Heartlight is an essence, not a weapon to be earned ----------
    ("docs/marketing/character-codex.html",
     "make good choices. Each Lumming has its own weapon, its own code of honour, its own way of\n"
     "    fighting — and its own way of evolving when it earns enough trust. "
     "<em>Choose your starter.</em>",
     "make good choices. Each Lumming has its own Heartlight, its own way of wondering, and its own way\n"
     "    of growing alongside your child. <em>Choose your companion.</em>", 1),

    # --- the colours, from the canon --------------------------------------
    ("docs/lead-magnet/lummings-5pk/index.html",
     "curious yellow Lummings", "curious ruby-red Lummings", 1),
    ("docs/lead-magnet/lummings-5pk/index.html",
     "spooky purple Lummings", "spooky lilac Lummings", 1),
    ("docs/lead-magnet/lummings-5pk/index.html",
     "mischievous magenta Lummings", "mischievous pink Lummings", 1),

    # --- no dark FOMO ------------------------------------------------------
    ("docs/marketing/app-store.html",
     "1,000 founder units. No second print run at this price.",
     "1,000 founder units. Reserve early to get the founder's price.", 1),

    # --- the tone: warm, patient, quiet ------------------------------------
    ("docs/demo/index.html",
     '"Hey hey hey! Sprout here. Let\'s GO. What\'s the most exciting thing we can do right now?"',
     '"Hey! Sprout here. Ready for a new route? What shall we try first?"', 1),

    # --- Lumo's passion, per the character bible ---------------------------
    ("docs/press-sheet.md",
     "**Lumo** loves science.", "**Lumo** loves co-op games and clever plans.", 1),
]


def main():
    # group the fixes by file, and apply them to the file's text
    by_file = {}
    for rel, old, new, n in FIXES:
        by_file.setdefault(rel, []).append((old, new, n))

    errors = []
    for rel, items in by_file.items():
        p = L / rel
        if not p.is_file():
            errors.append("%s is missing" % rel)
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        file_failed = False
        for old, new, n in items:
            c = text.count(old)
            if c == 0 and text.count(new) >= n:
                # already applied - the script is idempotent, so a re-run
                # after a partial failure is safe
                print("   %-42s %s  (already applied)" % (rel, (old[:44] + "...") if len(old) > 47 else old))
                continue
            if c != n:
                errors.append("%s: %r found %d times, expected %d" % (rel, old[:60], c, n))
                file_failed = True
                continue
            text = text.replace(old, new)
            print("   %-42s %s" % (rel, (old[:44] + "...") if len(old) > 47 else old))
        if file_failed:
            # a file with a drifted target is NOT written: a half-fixed page
            # is worse than an unfixed one, because it looks fixed.
            print("   -> %s NOT written (a target did not match)" % rel)
            continue
        p.write_text(text, encoding="utf-8")
        print("   -> %s written" % rel)

    if errors:
        print("\n=== THE FIXES WERE NOT ALL APPLIED ===")
        for e in errors:
            print("   %s" % e)
        return 1
    print("\n   every fix landed exactly once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
