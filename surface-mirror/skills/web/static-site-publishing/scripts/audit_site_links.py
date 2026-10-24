#!/usr/bin/env python3
"""Mount-aware link/asset audit for a static site published from a subtree.

A GitHub project site (``user.github.io/<repo>/``) serves one directory of the
repo at a URL mount. Two failure modes make references 404 there:

1. the target file lives outside the published subtree, so it never ships
2. the reference is root-absolute, so it resolves to the parent host root
   instead of the mount (on a project site the parent root is usually empty)

This script resolves every ``src``/``href`` the way a browser would against the
deployed URL (mount included), then checks the target inside the published tree.

Exit code 0 = clean, 1 = broken references found.

Usage:
    python audit_site_links.py --docs docs --mount /my-repo/
    python audit_site_links.py --docs docs --mount /my-repo/ --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REF_RE = re.compile(r'(?:src|href)\s*=\s*"([^"]+)"')
SKIP_PREFIXES = ("http", "#", "mailto:", "data:", "javascript:", "//", "tel:", "sms:")


def resolve(page_url: str, ref: str) -> str:
    """Resolve `ref` against `page_url` the way a browser would."""
    ref = ref.split("?")[0].split("#")[0]
    if not ref:
        return ""
    if ref.startswith("/"):
        return ref
    joined = page_url.rsplit("/", 1)[0] + "/" + ref
    parts: list[str] = []
    for seg in joined.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/" + "/".join(parts)


def audit(docs: Path, mount: str) -> list[dict]:
    problems: list[dict] = []
    for f in sorted(docs.rglob("*.html")):
        page_url = mount + f.relative_to(docs).as_posix().replace("\\", "/")
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for raw in REF_RE.findall(text):
            ref = raw.strip()
            if not ref or ref.startswith(SKIP_PREFIXES):
                continue
            site_path = resolve(page_url, ref)
            if not site_path:
                continue
            if not site_path.startswith(mount):
                problems.append({
                    "page": page_url[len(mount):], "ref": ref, "resolves_to": site_path,
                    "issue": "escapes the site mount - will 404 in production",
                })
                continue
            rel = site_path[len(mount):]
            target = docs / rel.strip("/")
            ok = target.exists() or (rel.endswith("/") and (target / "index.html").exists())
            if not ok:
                problems.append({
                    "page": page_url[len(mount):], "ref": ref, "resolves_to": site_path,
                    "issue": "target is not in the published tree",
                })
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", default="docs", help="published subtree (default: docs)")
    ap.add_argument("--mount", default="/", help="URL path the site is served from")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    docs = Path(args.docs).resolve()
    mount = args.mount if args.mount.endswith("/") else args.mount + "/"
    if not docs.exists():
        print(f"publish tree not found: {docs}")
        return 2

    problems = audit(docs, mount)
    pages = len(list(docs.rglob("*.html")))

    if args.json:
        print(json.dumps({"mount": mount, "pages": pages, "count": len(problems),
                          "problems": problems}, indent=2))
        return 1 if problems else 0

    if not problems:
        print(f"site link audit: clean ({pages} pages, mount {mount})")
        return 0
    print(f"site link audit: {len(problems)} problem(s) across {pages} pages")
    for p in problems:
        print(f"  {p['page']}: {p['ref']}  ->  {p['resolves_to']}  [{p['issue']}]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
