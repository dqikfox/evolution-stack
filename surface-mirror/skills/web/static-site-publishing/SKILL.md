---
name: static-site-publishing
description: "Publish static sites: mount-aware links, verified in prod."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Static Site, GitHub Pages, Publishing, Link Integrity, CI]
    related_skills: [github-repo-management, code-review-light]
---

# Static Site Publishing

Publishing a site is not "push and hope". A site can be live, look correct in the
editor, and still have every navigation link 404ing because the site is served from
a **subpath mount** that the markup does not know about. This skill is the
procedure for getting a static site onto a host and proving, with output, that it
works in production.

## When to Use
- "publish the site", "deploy the page", "the site is live but links are broken"
- Any repo that GitHub Pages serves as a project site (`user.github.io/<repo>/`)
- Before a launch, a handover, or a portfolio/demo review
- When a site "looks fine locally" but assets 404 in the browser

---

## Procedure

### 1. Establish the publish source and the URL mount — before editing anything
A GitHub **project** site serves one subtree of the repo at a path mount.
Everything downstream depends on knowing both.

```bash
gh api repos/OWNER/REPO/pages --jq '{branch:.branch,path:.path,build_type:.build_type}'
gh api repos/OWNER/REPO/pages/builds/latest --jq '{status:.status,commit:.commit[0:7]}'
```

Then prove it by probing both roots (the mount and the parent):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://user.github.io/<mount>/<known-file>
curl -s -o /dev/null -w "%{http_code}\n" https://user.github.io/<known-file>
```

The file that answers only under the mount tells you the publish subtree and the
mount in one shot. Record both: publish dir (e.g. `docs/`) and mount (e.g.
`/lummings/`).

### 2. Move every referenced asset inside the publish subtree
A page inside the published subtree that points at a file stored outside it is a
guaranteed 404 — the host only serves the subtree. Either move the asset in, or
repoint the reference at a copy that lives inside.

### 3. Make every reference mount-aware
- **Root-absolute** refs (`href="/shop/"`, `src="/app/stage.css"`) resolve to the
  *parent* host root, not the project mount. On a project site the parent root is
  usually empty → 404. Carry the mount: `/lummings/shop/`.
- **Relative** refs must not climb above the mount. A page two levels deep may use
  `../`, not `../../`.
- Refs to other hosts, `#anchors`, `mailto:`, `data:` are left alone.

### 4. Audit the way a browser resolves, then prove it is zero
Resolve each `src`/`href` against the page's **deployed URL** (mount included), then
check the target exists **relative to the publish dir**. Filesystem-relative
resolution gives false answers in both directions.

```bash
python scripts/audit_site_links.py --docs docs --mount /lummings/   # exit 1 if broken
```

Use `scripts/audit_site_links.py` from this skill (copy it into the repo). It prints
one line per broken reference with the page, the ref, and where it resolved.

### 5. Wire the audit into CI — a one-shot fix regresses
Add the audit as a CI step next to the existing build steps. The link-integrity
class of bug returns on the next edit otherwise; the gate is what makes the fix
stick.

### 6. Verify in production, after the build completes
A push is not a deploy. Wait for the build, then crawl the live site and follow
every reference it renders:

```bash
gh api repos/OWNER/REPO/pages/builds/latest --jq '.status'   # poll until "built"
```

Then fetch the live entry pages plus every `src`/`href` they contain, and treat any
non-200 as a defect. Report the crawl numbers (pages fetched, references checked,
broken count) — that is the proof, not "looks good to me".

### 7. Clean the repo of scratch before committing
A zip of the repo plus its extraction **inside** the repo is not work — it is a
self-copy that inflates every diff. Verify it is a copy, delete it, and gitignore
the pattern. Same for downloaded tooling, debug screenshots, and probe output.

---

## Pitfalls

- **A live site is not a working site.** The page can return 200 while every link
  inside it 404s. Always crawl the references, never the top page alone.
- **Root-absolute links break project sites.** They resolve to the parent host root,
  which for a project site is usually an empty user site — a 404 that looks like a
  missing file rather than a wrong prefix.
- **Assets outside the publish subtree never ship.** The host serves one directory;
  a perfectly committed file elsewhere on the repo is invisible to the site.
- **Resolve references against the deployed URL, not the filesystem.** Auditing with
  filesystem paths reports false passes (hiding real 404s) and false failures.
- **Audit output must be exactly zero before you claim the site works.** A nonzero
  count is an unfinished job, and a count you did not recompute is not evidence.
- **Wait for `status: built`.** Verifying during a build reads the previous
  deployment and makes a good fix look broken.
- **Check what the build actually shipped.** Legacy/Jekyll builds can skip content
  that the local tree contains; a successful status does not mean every file shipped.
- **A self-copy in the tree is not work.** Verify it, delete it, gitignore it — do
  not commit hundreds of MB of duplicate media.
- **Ship no template placeholders.** Grep the published HTML for `https://[...]`
  before publishing; unresolved placeholders become live broken links.
- **Prefer relative refs for deep pages and mounted refs for top-level links** so
  the site keeps working if the mount changes.

---

## Supporting files
- `scripts/audit_site_links.py` — mount-aware link/asset auditor for the publish
  tree. Copy into the repo, run locally and in CI.
- `references/github-pages-link-integrity.md` — determining publish source and mount,
  URL-resolution rules, live-crawl recipe, and a table of common reference defects.

## Do not
- Claim a site works without a crawl result (pages fetched, refs checked, broken 0)
- Rewrite published history to "fix" the site — publish a fix
- Publish a site whose audit reports a nonzero problem count
- Hand-edit the host's generated output instead of the source tree
