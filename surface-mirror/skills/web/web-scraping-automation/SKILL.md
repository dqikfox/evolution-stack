---
name: web-scraping-automation
description: Use for scraping protected SPAs via browser interaction.
---

# Web Scraping & Automation Strategy

Use this skill when tasked with extracting data from websites that may employ anti-bot protection or heavy JavaScript rendering.

## Triggers
- Task involves scraping content from a URL where standard `web_extract` fails.
- Need to investigate specific file contents within a remote repository (e.g., GitHub).

## Workflow
1. **Primary Attempt:** Use `web_extract(urls=[...])`. Fastest, no JS execution.
2. **Secondary Attempt (The Bypass):** Use `browser_exec` / Playwright for SPA-rendered content.
   - Use attribute selectors (`a[href*="..."]`) over brittle class names — modern SPAs churn classes.
   - When the target offers an **export** (CSV/XLSX button on a results page), prefer that over scraping the rendered DOM. Wire the click via Playwright `expect_download` and parse the file with pandas/openpyxl. Government and corporate registers almost always expose this.
3. **Tertiary Attempt (Raw Fetch):** `curl -L <URL>` as last resort — no JS, but bypasses browser-driven bot walls.

## Pitfalls & Fixes
- ⚠️ **Sticky/fixed buttons outside the viewport:** Playwright `ElementHandle.click` fails with "Element is outside of the viewport" on sticky headers, fixed toolbars, and off-screen action bars. Bypass with `force=True` on the click, or fall back to a direct JS dispatch: `document.querySelectorAll('button,a').forEach(b => { if (b.innerText.trim() === 'X') b.click(); })`.
- ⚠️ **Chrome Debugger Popups:** Shared desktop environments may block automation with "Allow remote debugging" prompts. If a tool fails immediately after navigation, retry via `browser_exec`.
- ⚠️ **Selector Fragility:** Do not rely on class names like `.react-file-row`; use attribute selectors (`a[href$=".py"]`) — sites update CSS classes constantly.
- ⚠️ **Execution Timeouts:** Large DOM traversals can timeout the turn. Prefer targeted JS injections that return small fragments over full-page dumps. When you need a lot of data, paginate via the site's own API (next-page clicks, export buttons) rather than scraping one giant page.
- ⚠️ **Browser-harness daemon can drop mid-session.** A working `browser_exec` call can start failing with `RuntimeError: no close frame received or sent` or `PermissionError` on `runtime\bu-default.port` — the daemon died, not your code. Recovery: just retry the same call (fresh tab via `new_tab`); if retries also fail, verify the target service is actually healthy with curl before concluding the browser layer is the problem. When repeated browser verification of a WebSocket/server flow keeps dying at the harness layer, fall back to a raw client (e.g. Python `websockets.connect`) for the assertion — it tests the real transport and is immune to harness restarts.
- ⚠️ **Extracting `<script>` blocks from semi-broken HTML:** regex `<script[^>]*>[\s\S]*?</script>` matches blocks the way the browser's HTML parser actually scopes them (content runs to the NEXT `</script>`), which is the correct rule for syntax-checking embedded JS — but on a file with doubled `<script><script>` tags or unbalanced closers, block counts from this method are estimates, not structure. `node --check` each extracted block; if the combined check reports redeclared identifiers, the page has duplicated top-level `const`/`let` blocks (a redeclaration in one block poisons the combined evaluation even when each block alone parses).
- ⚠️ **Akamai / commercial bot walls:** Major commercial sites (Domain.com.au, realestate.com.au, LinkedIn, etc.) block headless Chromium even with a normal user-agent. "Access Denied" + edgesuite.net reference ID is the signature. Pivot to authoritative government/regulatory registers or open-data sources — they have no anti-bot protection and are legally required to publish the data.
- ⚠️ **Government register result caps:** Sites like Verify NSW cap results at 200 per query and the cap is shown as "We only display up to 200 results" in the body text. To collect the full dataset, slice the search by an alphanumeric prefix on the name field (2-letter prefixes = 676 windows, 3-letter = 17,576) until each window returns under the cap. Track done prefixes in a checkpoint file so the job can resume after interruption.

## References
- See `references/government-registers.md` for the Australia NSW Property register workflow (authoritative source for licensed agencies).
- See `references/playwright-pitfalls.md` for sticky-button JS-click patterns and other Windows Playwright quirks.
