# GitHub Pages: publish source, mount, and link integrity

Depth for the `static-site-publishing` skill. Read this when the site is on
GitHub Pages, when a link 404s but the file "is in the repo", or when you need to
prove a deploy actually happened.

## 1. Finding the publish source and the mount

A GitHub **project** site (`https://USER.github.io/REPO/`) is served from one
directory of the repo at a URL mount. A **user** site (`https://USER.github.io/`)
is served from the repo root with no mount.

```bash
gh api repos/OWNER/REPO/pages --jq '{branch:.branch, path:.path, build_type:.build_type}'
gh api repos/OWNER/REPO/pages/builds/latest --jq '{status:.status, commit:.commit[0:7]}'
```

- `path` = the published subtree (often `/docs`), `branch` = the source branch.
- `build_type: legacy` → the build runs Jekyll over the source tree.
- `build_type: workflow` → a GitHub Actions workflow owns the deploy.

Confirm by probing (pick a file that exists in the candidate subtree):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://USER.github.io/REPO/<file>   # under mount
curl -s -o /dev/null -w "%{http_code}\n" https://USER.github.io/<file>         # parent root
```

A 200 only under the mount proves both the subtree and the mount. A 200 only at the
parent root means the site is a user site (no mount) — root-absolute refs are then
correct and must not be prefixed.

Legacy builds with Jekyll copy static files but process files with front matter,
and can drop or rewrite content. If a file exists in the source tree but 404s on
the site, compare the built tree (`gh api repos/OWNER/REPO/contents?ref=gh-pages`
when a gh-pages branch exists) before assuming a link bug.

## 2. URL resolution rules the audit must implement

Base = the page's deployed URL, including the mount.

| Reference | Resolves to | Correct on a project site? |
|---|---|---|
| `/shop/` | `https://USER.github.io/shop/` | **No** — escapes the mount → prefix the mount |
| `../assets/x.png` from `/mkt/deep/page.html` | `https://USER.github.io/mkt/assets/x.png` | Yes |
| `../../assets/x.png` from `/mkt/deep/page.html` | `https://USER.github.io/assets/x.png` | **No** — one `..` too many |
| `https://other.site/x` | other site | Yes — leave alone |
| `#anchor` | same page | Yes |
| `data:` / `mailto:` | inline / mail | Yes |

Rule of thumb: a page N segments below the mount may use at most N-1 `..`.

## 3. Publishing an asset that lives outside the published subtree

Symptom: the file is committed, `raw.githubusercontent.com/OWNER/REPO/branch/<path>`
returns 200, but the site 404s it.

Cause: the host serves only the published subtree; the file is outside it.

Fix options (pick one, do not leave both copies untracked):
- move the asset into the publish subtree and keep the reference unchanged
- copy it in and gitignore the out-of-tree original
- repoint the reference at an asset already inside the subtree

## 4. Live crawl recipe

Local audits cannot see deployment drops, so verify in production after the build
finishes.

```bash
# 1. wait for the build
until [ "$(gh api repos/OWNER/REPO/pages/builds/latest --jq .status)" = "built" ]; do sleep 20; done

# 2. crawl: fetch every page, then every src/href it renders
python - <<'PY'
import re, urllib.request, urllib.error
from urllib.parse import urljoin
BASE = "https://USER.github.io/REPO/"
def get(u):
    try:
        with urllib.request.urlopen(u, timeout=30) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, b""
    except Exception: return "ERR", b""
seen, bad, checked = set(), [], 0
queue = [BASE]
while queue and len(seen) < 60:
    url = queue.pop(0)
    if url in seen: continue
    seen.add(url)
    st, body = get(url); checked += 1
    if st != 200:
        bad.append((st, url)); continue
    if not url.endswith((".html", "/")): continue
    for m in re.findall(r'(?:src|href)="([^"]+)"', body.decode("utf-8", "ignore")):
        if m.startswith(("http", "#", "mailto:", "data:", "javascript:")): continue
        u = urljoin(url, m)
        s2, _ = get(u); checked += 1
        if s2 != 200: bad.append((s2, u))
        elif u.startswith(BASE) and u not in seen: queue.append(u)
print(f"pages {len(seen)} fetches {checked} broken {len(bad)}")
for s, u in bad: print(" ", s, u)
PY
```

Report the numbers (pages / fetches / broken). A crawl that stops at the first
error proves nothing.

## 5. Common reference defects

| Defect | Symptom | Fix |
|---|---|---|
| Root-absolute ref on a project site | link 404s, file "is in the repo" | prefix the mount |
| Asset outside the publish subtree | image/video 404s | move it into the subtree |
| One `..` too many | link 404s on a deep page | reduce the `..` depth |
| Unresolved template placeholder (`https://[...]`) | visible placeholder text or dead link | replace with the real URL before publishing |
| Link to a page that was never created | 404 on a legal/privacy/support path | write the page (a missing page is still a 404) |
| Nested extraction directory (`media/media/x.jpg`) | ref written for the nested path breaks after flattening | flatten and rewrite the refs, or keep the nesting deliberately |
