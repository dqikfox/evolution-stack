---
name: bulk-file-surgery
description: "Safely dedupe one overgrown file full of duplicate blocks."
version: 1.0.0
author: Hermes Agent (extracted from TESSERACT templates/index.html dedupe, 2026-09-01)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cleanup, dedupe, refactor, html, css, bulk-edit, file-repair]
    related_skills: [simplify-code, requesting-code-review, systematic-debugging]
---

# Bulk File Surgery — Safe Dedupe of an Overgrown File

When a single file (HTML template, CSS file, JS module, config) has accumulated
many duplicate copies of the same block — typically from iterative patches that
appended the new version without removing the old one — you need a safe way
to remove all duplicates while keeping exactly one canonical instance and
without destroying unrelated markup.

This is **NOT** a parallel review pass (see `simplify-code`). The whole file
is the problem; the diff is already bad. You are removing noise, not
improving recent code.

## When to Use

Trigger this skill when you see any of:

- The same `<button id="...">`, `<script>`, `<style>`, CSS rule, or config block
  appearing 5+ times in one file with near-identical content.
- Stacked positioning (`position:fixed; bottom:20px; right:20px` for multiple
  buttons at once) or multiple `MutationObserver`s on the same target.
- Orphan fragments: lines like `</script> onclick="...>+ NOTE</button>` —
  copy-paste that broke mid-line and was never cleaned up.
- "Same line X appears N times" with N large. `grep -c <pattern> file` shows
  the count.
- Commit history shows many "feat: implement X" or "fix: also implement X"
  commits on the same component.

Do NOT use for: removing a few duplicate lines (just `patch`), refactoring
working code (use `simplify-code`), or fixing logical bugs
(use `systematic-debugging`).

## The Process

### Phase 1 — Inventory (don't edit yet)

Run **before** writing any deletion script. Goal: produce a numbered list of
every duplicate occurrence with enough context that you can target it.

1. **Count the duplicates** with a literal search, not a regex:
   ```bash
   grep -n "<button id='journal-fab'" file.html
   ```
   Note the count. >5 is the trigger; >10 is "this file is a mess."

2. **Map each occurrence** to its line number and a one-line snippet so you
   can see context:
   ```bash
   grep -n "<button id='journal-fab'" file.html | head -20
   ```

3. **Identify the canonical version.** Look for:
   - The one that uses CSS class + JS observer (cleanest)
   - The one positioned at end-of-body or end-of-file
   - The most recent in commit history (`git log --oneline -p file | head`)
   - If none qualifies: pick the cleanest and improve it, then delete all
     others.

4. **Find associated side blocks.** Each duplicate usually pairs with a
   sibling script/style/comment. Examples:
   - A `<button>` sits next to a `<script>` that toggles it via
     `MutationObserver` → both must go.
   - A `<style>` rule sits next to a `</style>` closing tag → both must go
     if the rule is the only thing inside the `<style>` block; otherwise just
     the rule.
   - An orphan fragment (`</script> onclick=...` after a partial copy)
     stands alone → delete the whole line.

5. **List protective markers** you must NOT delete: `<body`, `</body>`,
   `</html>`, `</head>`, `</style>` (count > 1 means multiple style blocks;
   only delete if a whole style block is empty), critical IDs your JS depends
   on. Record baseline counts of each:
   ```bash
   for m in '<body' '</body>' '</html>' '</head>' '</style>' 'loadGoals()' \
            'goal-priority' 'horizon-pick'; do
     echo "$m: $(grep -c "$m" file.html)"
   done
   ```

### Phase 2 — Build a line-exact deletion script

Use a small Python script that works on **explicit 1-indexed line ranges**, not
regex over the file content. Example skeleton:

```python
from pathlib import Path

INDEX = Path(r"C:\path\to\file.html")
text = INDEX.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

# 1-indexed inclusive ranges from Phase 1 inventory
delete_ranges = [
    (1438, 1438),    # duplicate <button>
    (1440, 1446),    # observer script + orphan fragment line
    # ... etc
]

drop = set()
for start, end in delete_ranges:
    for ln in range(start - 1, end):
        drop.add(ln)

# Protect the closing tags
for protected in ("</body>", "</html>", "</style>", "<body"):
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith(protected):
            drop.discard(i)

kept = [ln for i, ln in enumerate(lines) if i not in drop]
Path("file.html").write_text("".join(kept), encoding="utf-8")
```

**Why line-exact, not regex:** regex over markup is greedy. A pattern like
`<script>.*?</script>` will happily match across unrelated `<script>` blocks,
swallowing hundreds of lines of CSS/HTML between them. My first attempt at
the TESSERACT dedupe removed 1,977 lines and destroyed `<body`, `</head>`,
and 3 of 4 `</style>` tags. Line-exact ranges are unambiguous; the script
deletes exactly what you said.

### Phase 3 — Run and audit (mandatory)

After every deletion pass, run the same marker audit from Phase 1 step 5:

```bash
for m in '<body' '</body>' '</html>' '</head>' '</style>' 'loadGoals()' \
         'goal-priority' 'horizon-pick' 'function showTab'; do
  echo "$m: $(grep -c "$m" file.html)  (baseline was <expected>)"
done
```

If any count drops, **revert immediately** (`git checkout HEAD -- file`) and
rebuild the delete-ranges from scratch — your regex was too greedy or your
line numbers shifted. Don't try to "patch up" the damage; the audit caught
silent corruption, and you cannot trust partial fixes.

Only proceed if every count matches baseline (or improved, e.g. you wanted
to drop the duplicate `</style>`).

### Phase 4 — Insert the canonical block

After deletion, prepend or append the canonical instance in the right
position. Common placements:

- A floating action button → right before `</body>` (so it stacks above
  modals).
- A MutationObserver for tab visibility → right before `</body>` (only runs
  once; duplicates waste cycles).
- A `<style>` rule → inside the existing `<style>` block, not as a new block.

Verify the canonical insertion appears exactly once:

```bash
grep -c "your-canonical-marker" file.html   # expect 1
```

### Phase 5 — Functional verification

Before declaring victory:

1. **Restart the server / reload the page** so cached templates clear.
2. **Curl the endpoint** and inspect the served HTML:
   ```bash
   curl -s http://127.0.0.1:8705/ | grep -c "+ NOTE</button>"   # expect 1
   curl -s http://127.0.0.1:8705/ | grep -c "MutationObserver" # expect 1
   ```
3. **Open the page in a browser** if possible — JS console errors from
   duplicate IDs (`getElementById` returning the first match) only show at
   runtime, not in grep.
4. **Run the project's test suite** — bulk surgery shouldn't change behavior,
   so existing tests should all still pass.

### Phase 6 — Commit + push

Single focused commit with the diff stat:

```
fix(<area>): remove N duplicate <thing> blocks, single source of truth

<file>:
- Removed N duplicate <element> + M duplicate <sibling> blocks that piled
  up across <M> automated commits
- Inserted one canonical <element> at <location> with <behavior>
- Net: K lines removed

Verified:
- <endpoint> serves HTTP 200
- <grep audit> shows expected counts
- N tests pass
```

## Escape hatch: rebuild from a clean ancestor

Line-exact surgery assumes the file is still structurally mappable. Decide BETWEEN regex surgery, line-exact surgery, and rebuild with this gate — check it in order BEFORE writing any deletion code:

1. **Script tag balance:** `count(<script...) == count(</script>)`? If not, or doubled tags like `<script><script>` appear, block content is UNRELIABLE — regex block matching will mis-map (the parser eats to next `</script>`, which may belong to an unrelated block).
2. **Duplicate-ID count per block:** a single `grep -c` on the duplicate signature tells you how many automated passes appended blocks.
3. **Orphan JS as visible text:** lines of raw JavaScript sitting in HTML context (`observer.observe(document.body...)` outside any `<script>`) mean broken tag nesting already corrupted the file's structure.

- Line-exact surgery: duplicates exist but tag balance holds and blocks are mappable.
- Rebuild: balance broken, orphans present, or blocks nest/interleave so neither regex nor line ranges can map them safely. Stop deleting and rebuild instead:

1. **Find the first corrupt commit**: `git log --oneline -- <file>`, then inspect the blob at each candidate: `git show <rev>:<file>`.
2. **Pick the newest clean ancestor and verify it mechanically**, not by eyeball: balanced `<script>`/`</script>` counts, zero occurrences of the duplicate signature, and `node --check` passing on every extracted script block (extract with the browser-faithful rule: content runs to the NEXT `</script>`, since that is how the HTML parser actually behaves). Check candidates in REVERSE chronological order from the corruption point — the release-tagged commit is usually the last clean one; later "fix/dedupe" attempts on top of it may still carry some damage (check the duplicate-signature count in each candidate, not just the tag name).
3. **Harvest legit features from the corrupt file.** Blocks containing none of the duplicate-signature strings are usually intact. Extract them verbatim and replay them onto the clean base. When a replayed feature must inject into a SPECIFIC location of the clean base (a tab panel, a header row), locate the structural anchor in the CLEAN base (its element id / container div) rather than trying to reproduce the corrupt file's layout.
4. **Rebuild = clean blob + replayed features + exactly one canonical instance** of the thing the loop kept duplicating, with a single CSS class / observer driving it.
5. **Verify**: `node --check` on the combined script blocks (concatenate with `;` separators — top-level `const` collisions between blocks throw at COMBINED level, not per-block), then browser-load and assert the corruption signature is gone (no raw JS as visible text) and each replayed feature still works. Drive the feature end-to-end in the browser (click the chip/button, assert the state variable changed and the rendered list changed) — a defined-but-never-executed function returns no error on load.
6. **Kill the cause before committing.** If the duplication came from an automation loop (a cron/scout job re-attempting the same edit every interval), find that job in `cron/jobs.json` and disable it FIRST — repairing while the writer is live means it re-corrupts the file between your write and your commit. Back up the job config before editing.
7. **Commit the rebuild as one focused commit** (rebuild + replayed features + cron-kill note), then immediately commit any small follow-up fixes separately — a rebuild commit that's followed by unrelated feature tweaks gets blamed for regressions it didn't cause.

A useful sanity metric during triage: if `<script>` opens and `</script>` closes disagree AND the duplicate signature appears dozens of times across hundreds of spam commits, no in-place repair will be cheaper than the rebuild.

## Pitfalls

- **Don't start with a broad regex.** `re.sub(r"<button[^>]*id=.fab.[^>]*>.*?</button>", "", src, flags=re.DOTALL)` will match across nested elements and swallow unrelated content. Always do Phase 1 inventory first.
- **Don't trust "obviously safe" deletions.** `<body` and `</html>` look like nothing — but if your regex swallows them, every browser that loads the page will silently render the head's CSS as the body. The marker audit catches this; never skip it.
- **Don't reuse line numbers from a previous run.** After your first deletion pass, every subsequent line number shifts. Recompute ranges from the *current* file, not the original.
- **Don't ship if the duplicate pattern still appears more than once.** The marker audit verifies structural integrity (`<body`, `</body>`, `</html>`), but it doesn't catch a *surviving duplicate of the thing you were trying to dedupe*. Always end your verification with `grep -c "<canonical-or-duplicate-pattern>" file` and assert the count equals your target (1 for keep-one, 0 for remove-all). If you see N>1 after the dedupe pass, the deletion ranges didn't cover one of the duplicates — go back to Phase 1 and find the survivor, then re-run. This is how an orphan block at the very end of `<body>` survives a "perfect" dedupe: the line-exact ranges computed against the original file don't account for partial deletions, and the orphan was sitting *below* the last range you planned.
- **Don't orphan `<script>` opening tags.** If you delete a `<script>` block but leave a `</script>` further down, every JS between them becomes text. Audit by counting `<script>` vs `</script>` — they must match.
- **Don't forget to clear template caches.** Jinja2 in production FastAPI often caches templates; restart the server, don't just reload the page.
- **Don't ship without runtime verification.** grep audits prove file-level correctness but not browser behavior. Always curl + (when possible) Playwright screenshot.
- **Don't combine this with refactoring.** If you find yourself wanting to "while I'm here, also fix X" — stop. This pass removes duplicates only. Refactor with `simplify-code` separately.
- **Don't re-commit the same fix in a loop.** If after your surgery, `git log` shows 10 commits titled "feat: implement journal-fab visibility," that's a sign the previous automated sessions kept appending the same code. The fix is the dedupe + a guard (linter / pre-commit / clear ownership) so the duplication can't re-accumulate. Mention this in the commit message.

- **Verify an anchor line is top-level before injecting top-level code after it.** A unique string like `window._x = {}` can sit inside a function's try-block rather than at module scope; code injected after it inherits that scope, never executes, and the feature dies silently while every syntax check still passes. Read the surrounding lines (or check brace depth) before anchoring an injection to a matched string.
- **When feature code injected after an anchor doesn't run, suspect anchor scope before suspecting syntax.** Symptom: the defining statement exists in the served file, the browser reports the symbol as undefined, and the block parses clean. Move the injected code to a genuine top-level anchor (e.g. a known module-level declaration) and re-test.

## Verification Heuristics

Quick smoke test before declaring done:

```bash
# 1. File shrunk or stayed same size (lines ↓)
wc -l file.html

# 2. Canonical marker count is exactly 1
grep -c "<canonical-marker>" file.html

# 3. Duplicate count is 0
grep -c "<old-duplicate-pattern>" file.html

# 4. Critical structure intact
grep -cE "<body|</body>|</html>" file.html   # expect >= 1 of each

# 5. Runtime still works
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:PORT/path
```

If any of those fail, revert and rebuild from scratch — partial surgery on
a half-corrupted file is worse than the original mess.

## Related

- `simplify-code` — for cleaning up recent *changes* across many files via
  parallel review. Different scope (recent diff vs. accumulated rot), different
  technique.
- `systematic-debugging` — when the duplicates aren't visible symptoms but the
  underlying logic is broken; this skill is for visible accumulation only.
- `python-environment-management/references/pythonpath-leakage-fix.md` — same
  "audit before edit" mindset, applied to sys.path.
