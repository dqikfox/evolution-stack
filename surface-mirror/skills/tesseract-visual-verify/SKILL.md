---
name: tesseract-visual-verify
description: Verify TESSERACT UI via Playwright screenshots.
---

# TESSERACT Frontend Visual Verification

Headless Playwright script that drives the live TESSERACT dashboard (port 8705) and
captures verification screenshots for the main UI surfaces.

## When to Use

Use when verifying TESSERACT dashboard UI changes via headless Playwright
screenshots. Captures all major tabs plus Ctrl+K Seeker and global search
dropdown.

## Workflow

1. Confirm server is up: `curl -fsS http://127.0.0.1:8705/health` returns 200
2. Run the verification script: `python scripts/verify_clean.py`
3. Inspect the resulting screenshots under `docs/`

The reference script at `scripts/verify_clean.py` captures:

- `docs/screen_seeker_default.png` — Seeker overlay (Ctrl+K) before any query
- `docs/screen_seeker_filtered.png` — Seeker filtered by `goal`
- `docs/screen_goals_progress.png` — Goals tab showing progress bars + why lines
- `docs/screen_projects_brief.png` — Projects tab with brief one-liners
- `docs/screen_global_search_notes.png` — Global search dropdown showing Notes group (`tesseract` query)
- `docs/screen_global_search_stack.png` — Global search dropdown showing Stack/Probes group (`ollama` query)

## Pitfalls

- **Dropdown clipping**: `#search-dropdown` has `max-height: min(720px, 80vh)`.
  Use a 1440x1600 viewport for verification screenshots so all groups render.
- **Seeker overlay covers tab content**: must press Escape (or call `closeSeeker()`
  from page context) before clicking tabs/forms or the overlay intercepts pointer events.
- **Hidden forms via `display:none`**: goal/project edit forms use `display:none`
  on the edit div. Call `editGoal(id)` / `editProject(id)` from page evaluate to
  reveal them — clicking the pencil button can be intercepted if other overlays are open.
- **Backspace through typed query**: seeker keeps typed text — when refiltering,
  press Backspace N times to clear, don't use `inp.value = ''` (loses focus).
- **Group label discovery**: `Array.from(document.querySelectorAll('#search-dropdown .search-group-label')).map(el => el.textContent)`
  prints exactly which groups rendered.

## Test bar

Spec says ≥197 tests passing; current baseline is 215 passed + 1 skipped.

```bash
.venv/Scripts/python.exe -m pytest -q
```
