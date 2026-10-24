# GitHub Pages Verification + Sync Workflow

Condensed recipe for shipping a static HTML page to GitHub Pages and
proving it went live. Covers the `site/` vs `docs/` dual-source drift
that bites repos where the hand-edited source lives in `site/` but
Pages serves from `docs/`.

## Identify the actual Pages source before editing

```bash
gh api repos/<owner>/<repo>/pages --jq '.source | "\(.branch) : /\(.path)"'
```

Returns e.g. `main : /docs`. If the result is `/docs`, edits to
`site/index.html` do NOT propagate.

## Two ways to keep them in sync

1. **Manual copy** in every commit:
   ```bash
   cp site/index.html docs/index.html
   git add site/index.html docs/index.html
   git commit -m "feat: ..."
   git push
   ```
2. **CI mirror** — one tiny workflow:
   ```yaml
   # .github/workflows/sync-site.yml
   on: { push: { paths: ["site/**"] } }
   jobs:
     sync:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - run: cp site/index.html docs/index.html
         - uses: stefanzweifel/git-auto-commit-action@v5
           with: { file_pattern: docs/index.html }
   ```

Option 2 prevents drift forever. Option 1 is fine if you rarely touch
`site/`.

## Verify the deploy landed

Pages deploys asynchronously — usually 20–40s. Don't re-push to "fix"
what is just a slow build.

```bash
sleep 30 && curl -sI https://<owner>.github.io/<repo>/<path>/ | head -1
```

Status must be `HTTP/1.1 200 OK`. If still 404 after 90s, check the
Actions tab for the Pages build failure.

## Verify the page contains the change

HTTP 200 alone doesn't prove the new content shipped. Grep for a
unique marker that didn't exist before:

```bash
curl -s https://<owner>.github.io/<repo>/<path>/ | grep -c "<marker>"
```

If marker count is 0, the Pages build cached or failed — check
`.github/workflows/` for a `docs.yml` or similar that rebuilds
through `make docs`. If the workflow is destructive (rebuilds /docs
from scratch), the copy in step 1 above gets clobbered and you must
either (a) edit in `docs/` directly, (b) fix the workflow, or
(c) move the source of truth to `docs/`.

## Pitfalls

- **Re-pushing does not speed up Pages.** If the build is in flight,
  wait. Re-pushing just queues another build behind it.
- **The Pages build might not match your `gh-pages` branch.** For
  `build_type: legacy` project pages, the source is whatever branch
  + path the repo settings say, NOT necessarily `gh-pages`.
- **`.nojekyll` matters** if your pages use directories starting with
  `_`. Add `touch docs/.nojekyll` once and commit.
- **`404` on a subpath often means Pages is up but the file is not in
  `/docs`.** Check that you copied (not just edited in `site/`).
