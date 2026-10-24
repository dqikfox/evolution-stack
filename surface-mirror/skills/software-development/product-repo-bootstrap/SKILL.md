---
name: product-repo-bootstrap
description: Scaffold a product repo via idea-forge.
---

# Product repo bootstrap via idea-forge

Scaffold a publishable product repository from a single idea using idea-forge's manifest + template + starter-pack pattern. Use when the user wants to ship a product (not just a script) and the existing scaffolding fits one of idea-forge's templates.

## What idea-forge gives you

`C:\Users\KING\Projects\idea-forge` (or the user's fork `dqikfox/idea-forge`) is a repo generator with:

- **Templates** under `templates/` — language + domain scaffolds (python-research, rust-workspace, javascript-webapp, static-website, notebook-laboratory, c-library, c-kernel, latex-book, latex-paper, plus user-added `smart-toy`).
- **Manifest** at `manifests/projects.tsv` — TSV of `repo\ttitle\tdescription\ttopics\ttemplates\tstarter_pack\tsummary` rows. One row = one product.
- **Starter packs** at `lib/starter_packs.sh` — bash functions named `starter_pack_<name>()` that take `repo_path` and `package`, and `cat <<EOF2 ... EOF2` heredoc the actual product code into the generated repo. Starter pack listing auto-discovers from function names.
- **Bootstrap CLI** at `bin/forge` — `forge bootstrap <repo> [--root PATH] [--owner ORG] [--no-github] [--dry-run]`.

## Procedure

1. **Pick or extend a template.** Match the product's shape:
   - Python-only product → `python-research`
   - Product with embedded device + Python brain → `smart-toy` (covers Python + Rust + web + notebooks)
   - Pure static landing page → `static-website`
2. **Add a manifest entry** to `manifests/projects.tsv`:
   - `repo` is the directory key (used for `forge bootstrap <repo>` and the `repo_path` it lands at). Plural form is fine.
   - `templates` is a CSV of template names.
   - `starter_pack` names a bash function in `lib/starter_packs.sh` (or empty if no extra content needed).
3. **Add the starter pack** as a `starter_pack_<name>()` function in `lib/starter_packs.sh`. The function writes the product-specific files via `cat <<EOF2 ... EOF2`. Place it BEFORE `apply_starter_pack()` (which references it via name lookup).
4. **Verify with `doctor`:**
   ```bash
   bash bin/forge doctor <repo>
   ```
   Must report "no errors (0 warnings)". Errors typically: missing starter pack function, unknown template name, malformed TSV row.
5. **Bootstrap to a clean directory:**
   ```bash
   bash bin/forge bootstrap <repo> --root "/c/Users/KING/Projects" --owner dqikfox --no-github --dry-run
   bash bin/forge bootstrap <repo> --root "/c/Users/KING/Projects" --owner dqikfox --no-github
   ```
   `--no-github` skips the gh API. Pass `--dry-run` first to preview the file list.
6. **The bootstrap names the directory after the `repo` column**, not after `--root/<repo>`. So a manifest row `repo=lummings` lands at `<root>/lummings/`. If the user asked for `C:\Users\KING\Projects\lumming\` (singular), bootstrap then `mv` to the desired name; the bootstrap will create `<root>/lummings/` even if the singular form was requested.
7. **Initialize git, commit, push:**
   ```bash
   cd <bootstrap_root>/<repo>
   git init -b main
   # create GitHub repo via gh CLI (see github-repo-management skill)
   gh repo create dqikfox/<repo> --private --source . --remote origin --push
   ```
   The bootstrap leaves the repo git-initialized but uncommitted. First push via `gh repo create --push` works because the bootstrap set up a local commit.

## Test the bootstrap

For Python products:
```bash
cd <bootstrap_root>/<repo>
python -m pip install -e .
python -m pytest tests/ -v
```

For products with HTTP servers: launch the server on a non-conflicting port (8511+), `curl` the health/persona endpoints, kill the process.

## Ship a brand, not just code

When the user says "build a product", "create a brand", or "we need something solid to offer", they want the full shippable package — not just working code. Treat the bootstrap as the STARTING point, then deliver:

1. **Brand guidelines** (`BRAND.md`) — voice, tone, visual system, vocabulary, privacy stance, pricing tiers, success metrics. One source of truth every other doc defers to.
2. **Wordmark + character/asset SVGs** — procedurally generated, regeneratable from `scripts/` or `src/`. Ship at least 10x more variations than you think you need (moods × poses × sizes).
3. **Landing page** at `docs/index.html` (NOT `site/` — see GitHub Pages pitfall below). Inline SVG to avoid asset path issues. Dark theme that matches the brand colors.
4. **Per-persona SFT data** for products with characters — 50-100 hand-written turns per persona, formatted as JSONL with the system prompt baked in.
5. **Training pipeline** (`scripts/train_persona.py`) — even if the actual SFT run is deferred, the pipeline file lets a future session execute without re-thinking.
6. **Business model** (`BUSINESS.md`) — pricing, Year-1-5 projections, moats, risks, distribution. Forces you to confront whether the product is actually shippable.
7. **One-page press sheet** (`docs/press-sheet.md`) — at-a-glance table, founder bio, technical specs, contact. Journalists shouldn't have to dig.

### Distribution on $0 marketing budget

Once a product has the brand package above, **distribution is the next 14-day grind**, not a single day. Every "I built a thing, why aren't people buying it" scenario has the same root: the product has features but no audience, and the audience-creation steps (karma build, account age, repeat posts) take longer than the product took to build. Build a 14-day calendar:

1. **Day 1-3: identify channels** that reach the product's buyer. For a privacy-first kids' AI product: Reddit parenting + SideProject + gamedev + StableDiffusion, Hacker News Show HN (Tuesday/Wed 8-10am PT), Product Hunt (needs 2-week prep), itch.io (game devs), Indie Hackers (build-in-public), Substack (one announcement email).
2. **Day 1: create brand accounts** for each channel — same email (e.g. `indieforge@<domain>`), same password via 1Password, brand handles (not the user's personal handle). Verification emails take 5 min each. Do NOT use the user's personal GitHub/Reddit/email for marketing — once a customer's GitHub handle leaks via a marketing page, it can't be un-leaked.
3. **Day 3-9: warm up accounts** with non-promotional help — leave 3-5 GENUINE helpful comments per day on Reddit (no "great post, my product is..."), submit one useful HN comment, post IH "shipping milestone" without a link. Target: 100+ Reddit karma before any link post.
4. **Day 10-14: first real posts** on each channel. ONE link drop per channel per week. Reply to comments for 30+ min after each post (HN ranks by comment quality, Reddit by author responsiveness). Multiple platform posts in one day look spammy.
5. **Don't**. Premature posts on cold accounts get banned and burn the channel. Two weeks of account aging is cheaper than re-creating accounts after bans.

**Building infrastructure for traffic that doesn't exist** is the most common waste in indie launches. A 6-agent swarm building lead-magnet landing pages, ZIP download endpoints, and Telegram bot order flows is wasted when no one sees the link. Diagnose before building: if the launch checklist reads "0 visitors → 6 lead pages → 6 social post drafts → directory submissions" and the visitor count is 0 → fix the visitor count FIRST (post the landing URL somewhere that has traffic, even if it's just r/SideProject), THEN build the funnel. The funnel only matters once there's traffic.

**Honest month-1 ceiling for a $0-marketing-budget launch**: 0-20 visitors week 1, 50-1500 week 2-3 if a post breaks through, $0-$1500 revenue month 1 (median $0-$150). Plan for the median, not the upside.

Tests matter less than the above for brand products. The product IS the brand; brand-validated (brand.md + landing + business model) > test-passing.

## Pitfalls

- **Bootstrap lands in plural form** — `repo=lummings` creates `<root>/lummings/`, not `lumming/`. Bootstrap first, then `mv` if you need the singular. Don't try to pre-create the target directory; forge will refuse.
- **GitHub Pages API only accepts `/` or `/docs` as the source path** — not `/site`, not `/docs-site`. If your landing page lives in `site/`, either (a) rename it to `docs/` before pushing, or (b) symlink/copy `site/` → `docs/` at bootstrap time. The error is `422 Invalid property /source/path` and lists the two valid values. Also add `.nojekyll` to the docs root so inline SVG renders verbatim without Jekyll preprocessing.
- **Hero/section z-index bug**: a decorative absolutely-positioned child (e.g. `bg-glow` radial gradient) inside a section + a CSS rule `.section > * { position: relative; z-index: 1; }` that targets ALL children breaks the absolute positioning. The decorative child gets `position: relative` and pushes all content down by its own size. Fix the selector with `:not(.bg-glow)` or scope the z-index rule to a class instead of a universal child selector. Verify the rendered hero by inspecting a screenshot, not by checking that the HTML is well-formed — the bug is invisible in source.
- **SVG primitive positioning bug**: when generating SVG shapes that should be centered on a body (eyes on a face, features on a glyph), compute absolute coordinates (`body_cx + offset`, not `offset`). Relative offsets passed as `cx` attributes render at the top-left of the viewBox, not on the body. Always render the SVG to PNG and visually inspect after writing the renderer — coordinate math bugs are invisible in the source but obvious in the render.
- **CRLF warnings on Windows** — git prints `LF will be replaced by CRLF` warnings for every file. Harmless; git normalizes line endings. Don't try to silence them.
- **Bash heredocs in starter packs lose UTF-8 chars on the patch boundary** — see qlora-throne-windows SKILL §Pitfalls for the byte-level fix. The starter pack author writes Python + UTF-8 normally; only the `patch` tool's old_string match is unreliable for non-ASCII content.
- **Bash variable substitution inside heredocs is dangerous** — use `<<'EOF2'` (single-quoted EOF marker) to disable interpolation. Every starter-pack heredoc must use `EOF2` (not `EOF`) precisely to prevent `$` in the generated Python from being substituted.
- **Starter pack typos propagate** — every repo bootstrapped carries the same bug. Test the starter pack once on a single bootstrap, fix the bash function, then re-bootstrap. Never fix the bug only in the generated repo.
- **`forge doctor` is fast** — run it after every edit to `manifests/projects.tsv` or `lib/starter_packs.sh`. It catches missing starter packs, malformed TSV rows, and unknown templates in <1 s.
- **The starter pack function name uses underscores** — `starter_pack_my_thing()`, not `starter_pack_my-thing()`. The manifest's `starter_pack` column is what maps to it; the bash function name is the underscore form.
- **If the product needs a launcher script**, write it as a `.cmd` (Windows) and a `.sh` (Unix). The forge templates don't auto-generate launchers.
- **The starter pack function runs once per bootstrap** — `cat <<EOF2` writes the file once. If the file already exists from a previous bootstrap, bash appends/replaces depending on shell redirect (we use `>` which truncates). Re-bootstrapping into a non-empty directory will overwrite; back up first.
