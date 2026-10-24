"""
Dedupe an overgrown HTML file by removing explicit line ranges.

This is the canonical helper for the `bulk-file-surgery` skill. Use it when
you have inventoried duplicate <button>/<script>/<style>/<style-rule>
blocks at known line ranges and want a safe, auditable removal pass.

Usage:
  1. Inventory duplicates with `grep -n "<pattern>" file.html` and note line
     ranges that should go (1-indexed, inclusive).
  2. Edit the `delete_ranges` list below with your ranges.
  3. Run: python dedupe_html_blocks.py file.html
  4. The script prints before/after audit counts of critical markers — verify
     every count matches the baseline you recorded in Phase 1.

Why this script exists: regex over markup is greedy. A naive pattern like
re.sub(r"<script>.*?</script>", ...) will match across unrelated <script>
blocks and silently swallow hundreds of lines of CSS/HTML. Explicit line
ranges delete exactly what you said, no more, no less.

WARNING: Always run the marker audit after. If <body, </body>, </html>,
</head>, or any critical ID count drops, `git checkout HEAD -- file.html`
and rebuild the ranges from scratch. Do NOT try to patch the damage.
"""
from pathlib import Path
import sys


def dedupe_html(path: str, delete_ranges: list[tuple[int, int]],
                protective_markers: tuple[str, ...] = (
                    "</body>", "</html>", "</style>", "<body", "</head>",
                )):
    """Remove the given 1-indexed inclusive line ranges from `path`.

    Args:
        path: HTML file to dedupe.
        delete_ranges: list of (start_line, end_line) tuples, 1-indexed.
        protective_markers: lines whose presence we will not delete even if
            a range covers them. Critical for keeping <body>, </body>,
            </html> intact.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    orig_len = len(lines)

    # Convert to 0-indexed line numbers
    drop = set()
    for start, end in delete_ranges:
        for ln in range(start - 1, end):
            drop.add(ln)

    # Protect critical structural markers
    for marker in protective_markers:
        marker_l = marker.lower()
        for i, ln in enumerate(lines):
            if ln.strip().lower().startswith(marker_l):
                drop.discard(i)

    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    new_len = len(kept)
    p.write_text("".join(kept), encoding="utf-8")

    print(f"Original: {orig_len} lines")
    print(f"Cleaned:  {new_len} lines")
    print(f"Removed:  {orig_len - new_len} lines")
    print(f"Drop set size: {len(drop)}")
    return orig_len, new_len


def audit_markers(path: str, markers: list[str]) -> dict[str, int]:
    """Print count of each marker in the file. Use before/after dedupe to
    detect silent corruption (e.g. <body tag accidentally deleted)."""
    text = Path(path).read_text(encoding="utf-8")
    counts = {m: text.count(m) for m in markers}
    for m, c in counts.items():
        print(f"  {m:25s} count={c}")
    return counts


if __name__ == "__main__":
    # ── EDIT THIS LIST WITH YOUR PHASE 1 INVENTORY ─────────────────────────
    delete_ranges = [
        # (start, end) inclusive, 1-indexed. Example:
        # (1438, 1438),    # duplicate <button>
        # (1440, 1446),    # observer script + orphan fragment line
    ]
    # ──────────────────────────────────────────────────────────────────────

    audit_markers = [
        "<body", "</body>", "</html>", "</head>", "</style>",
        # Add IDs your JS depends on, e.g.:
        # "loadGoals()", "addJournal()", "function showTab",
    ]

    if len(sys.argv) < 2:
        print("Usage: python dedupe_html_blocks.py <file.html>")
        sys.exit(1)

    path = sys.argv[1]

    print("=== BEFORE ===")
    audit_markers(path, audit_markers)
    print()
    print("=== DEDUPE ===")
    dedupe_html(path, delete_ranges)
    print()
    print("=== AFTER ===")
    audit_markers(path, audit_markers)
