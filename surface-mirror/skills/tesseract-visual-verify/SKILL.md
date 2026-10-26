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
- **Two functions can fetch the same endpoint — patch the one the tab actually calls.**
  A panel that stays empty while its API returns data is usually the wrong render
  function, not a broken response. Diagnose in the browser: confirm the container
  exists, confirm the fetch returns the payload, then confirm which function the
  tab invokes (`page.on("pageerror")` plus a read of the container's `innerHTML`).
- **`inner_text()` returns an empty string for a hidden element.** When diagnosing a
  panel that "does not render", read `inner_html()` instead — it is not subject to
  visibility.
- **Element screenshots need the element scrolled into view**:
  `element.scroll_into_view_if_needed()` then `element.screenshot(path=...)`. A
  full-page screenshot of a long dashboard puts the panel below the fold and the
  verification image proves nothing.
- **Run the script with the interpreter that has Playwright** — the Hermes venv
  (`%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`), not the project's
  venv, which does not carry it.
- **Restart the service through the canonical launcher after changing server code.**
  The launcher deliberately leaves a healthy supervised service alone, so an edited
  server keeps serving the old code until it is stopped and relaunched through
  `hermes/scripts/start_tesseract.cmd`.

## Test bar

Spec says ≥197 tests passing; current baseline is 339 passed + 1 skipped.

```bash
.venv/Scripts/python.exe -m pytest -q
```

- **Run the TESSERACT suite with the ABSOLUTE venv path**, not `.venv/Scripts/python.exe`.
  A relative path resolves to `C:\Users\KING\.venv` under MSYS, which has no
  `fastapi`, and the whole suite errors at collection with 21 import errors.
  The project venv is `C:\Users\KING\Projects\TESSERACT\.venv\Scripts\python.exe`.
  The suite is 339 passed + 1 skipped.
- **A panel can render correctly and still be on a hidden tab.** The MODEL
  PROVIDERS panel lives in `tab-network`; a screenshot attempt times out with
  "element is not visible" until the tab is opened. Open it with
  `page.evaluate("showTab('network')")` rather than clicking a label - the
  labels are also used for other navigation and a click can land wrong.
- **Measure overflow, do not eyeball it.** `scrollWidth > clientWidth` on every
  descendant of the panel catches text that runs past a card edge; a
  screenshot at dashboard scale can hide it. `scripts/check_provider_overflow.py`
  in the TESSERACT repo does this.
