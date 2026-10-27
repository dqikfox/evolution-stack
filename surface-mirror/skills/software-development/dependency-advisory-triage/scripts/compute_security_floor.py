#!/usr/bin/env python3
"""Compute the installable security floor for a repo's dependency advisories.

Enumerates the open Dependabot alerts for a GitHub repo, resolves each
advisory's real vulnerable range, and reports the lowest version of each
package that is BOTH outside every vulnerable range AND not yanked on PyPI.

Optionally checks a requirements file's pins against those advisories.

Usage:
    python compute_security_floor.py --repo owner/name
    python compute_security_floor.py --repo owner/name --check requirements.txt

Exit codes:
    0  every advisory is cleared (or no advisories are open)
    1  a package still sits inside a vulnerable range
    2  the advisory feed could not be read -- never report clean for this
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request

try:
    from packaging.version import Version, InvalidVersion
    HAVE_PACKAGING = True
except ImportError:  # pragma: no cover - fallback for minimal environments
    HAVE_PACKAGING = False
    Version = None
    InvalidVersion = ValueError


def gh(path: str):
    """GET a GitHub API path and return parsed JSON, or None on failure.

    The path may carry gh flags (e.g. 'repos/o/n/alerts --paginate'), so it
    is split on whitespace into separate argv entries - passing it as one
    argument would make gh read the flag as part of the path.
    """
    args = ["gh", "api"] + path.split()
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- ordering

def _numeric_key(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def _parse(v: str):
    if HAVE_PACKAGING:
        try:
            return Version(v)
        except InvalidVersion:
            return None
    return v


def _cmp(a: str, b: str) -> int:
    if HAVE_PACKAGING:
        pa, pb = _parse(a), _parse(b)
        if pa is None or pb is None:
            ka, kb = _numeric_key(a), _numeric_key(b)
            return (ka > kb) - (ka < kb)
        return (pa > pb) - (pa < pb)
    ka, kb = _numeric_key(a), _numeric_key(b)
    return (ka > kb) - (ka < kb)


# ------------------------------------------------------------------ ranges

def _clause_holds(ver: str, op: str, bound: str) -> bool:
    c = _cmp(ver, bound)
    if op == ">=":
        return c >= 0
    if op == "<=":
        return c <= 0
    if op == ">":
        return c > 0
    if op == "<":
        return c < 0
    if op == "==":
        return c == 0
    return False


def in_range(ver: str, rng: str) -> bool:
    """True if ver falls inside the advisory's vulnerable range.

    A comma-separated range is a CONJUNCTION: '>= 4.49.0, < 4.51.0'
    requires BOTH clauses to hold. Treating it as a disjunction reports
    every version above the lower bound as vulnerable, which makes a
    correct fix look broken.
    """
    clauses = [c.strip() for c in rng.split(",") if c.strip()]
    if not clauses:
        return False
    for part in clauses:
        m = re.match(r"^(>=|<=|>|<|==)?\s*(.+)$", part)
        if not m:
            return False
        op = m.group(1) or "=="
        raw = m.group(2).strip()
        if not _clause_holds(ver, op, raw):
            return False
    return True


# ------------------------------------------------------------------- pypi

def pypi_info(package: str):
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{package}/json", timeout=30
        ) as fh:
            return json.load(fh)
    except Exception:
        return None


def is_yanked(package: str, version: str) -> bool:
    info = pypi_info(package)
    if not info:
        return False
    files = info.get("releases", {}).get(version, [])
    if not files:
        return False
    return all(f.get("yanked") for f in files)


def release_versions(package: str) -> list[str]:
    info = pypi_info(package)
    if not info:
        return []
    return list(info.get("releases", {}).keys())


# -------------------------------------------------------------- advisories

def alerts(repo: str, state: str | None = None):
    """Fetch the repo's Dependabot alerts, PAGINATED.

    The alert list defaults to 30 per page. Without --paginate, a repo
    with more alerts than that silently loses the tail - and an open
    advisory on page 2 is exactly the one you need to see.
    """
    out = gh(f"repos/{repo}/dependabot/alerts --paginate")
    if out is None:
        return None
    if isinstance(out, dict):
        out = [out]
    if state:
        out = [a for a in out if a.get("state") == state]
    return out


def _advisories_for(alert_list):
    """Turn a list of alerts into (ghsa, package, severity, range, patched)."""
    ids = sorted({a["security_advisory"]["ghsa_id"] for a in alert_list})
    out = []
    for gid in ids:
        adv = gh(f"advisories/{gid}")
        if not adv:
            continue
        sev = adv.get("severity", "?")
        for v in adv.get("vulnerabilities", []):
            pkg = (v.get("package") or {}).get("name")
            rng = v.get("vulnerable_version_range")
            fpv = v.get("first_patched_version")
            if isinstance(fpv, dict):
                patched = fpv.get("identifier")
            elif isinstance(fpv, str):
                patched = fpv
            else:
                patched = None
            if pkg and rng:
                out.append((gid, pkg, sev, rng, patched))
    return out


def open_advisories(repo: str):
    """Advisories for the repo's OPEN alerts, or None if the feed is unreadable."""
    a = alerts(repo, state="open")
    if a is None:
        return None
    return _advisories_for(a)


def all_advisories(repo: str):
    """Advisories for EVERY alert the repo has ever had, in any state.

    A 'fixed' alert still describes a real vulnerable range. A pin inside
    that range is still vulnerable, whether or not Dependabot has closed
    the ticket - so this is what a --check must be evaluated against.
    """
    a = alerts(repo)
    if a is None:
        return None
    return _advisories_for(a)


def compute_floor(advs):
    """Lowest non-yanked version per package outside every one of its ranges."""
    by_pkg = {}
    for gid, pkg, sev, rng, patched in advs:
        by_pkg.setdefault(pkg, []).append((gid, sev, rng, patched))

    floors = {}
    for pkg, items in sorted(by_pkg.items()):
        # Start above the highest patched version, and above any range that
        # has no patched version (those are cleared by exceeding the bound).
        lower = "0"
        for _gid, _sev, _rng, patched in items:
            if patched and _cmp(patched, lower) > 0:
                lower = patched
        versions = release_versions(pkg)
        if not versions:
            floors[pkg] = (None, "no PyPI release list available")
            continue
        versions.sort(key=_numeric_key)
        start = next((i for i, v in enumerate(versions)
                      if _cmp(v, lower) >= 0), len(versions) - 1)
        chosen, why = None, None
        for v in versions[start:]:
            if any(in_range(v, rng) for _g, _s, rng, _p in items):
                continue
            if is_yanked(pkg, v):
                why = f"{v} is yanked"
                continue
            chosen = v
            break
        floors[pkg] = (chosen, why)
    return floors


# ------------------------------------------------------------ requirements

def parse_pins(path: str):
    pins = {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-+]+)", line)
            if m:
                pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def check_pins(advs, pins):
    """Return a list of (package, version, ghsa, severity, range) still vulnerable."""
    bad = []
    for gid, pkg, sev, rng, _patched in advs:
        key = pkg.lower().replace("_", "-")
        ver = pins.get(key)
        if not ver:
            continue
        if in_range(ver, rng):
            bad.append((pkg, ver, gid, sev, rng))
    return bad


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--check", help="requirements file to check against the advisories")
    args = ap.parse_args()

    open_advs = open_advisories(args.repo)
    if open_advs is None:
        print(f"could not read advisories for {args.repo} "
              f"(is gh authenticated?)", file=sys.stderr)
        return 2

    if args.check:
        # A --check is evaluated against EVERY advisory the repo has ever
        # had, not only the open ones. Checking against open alerts alone
        # hands out a false green once the triage is done: with no open
        # alerts, ANY manifest passes - including the pins that caused the
        # alerts. A 'fixed' alert still describes a real vulnerable range.
        advs = all_advisories(args.repo)
        if advs is None:
            print(f"could not read advisories for {args.repo} "
                  f"(is gh authenticated?)", file=sys.stderr)
            return 2
        if not advs:
            print(f"no advisories have ever been filed for {args.repo} - "
                  f"there is nothing to verify against")
            return 0
        pins = parse_pins(args.check)
        bad = check_pins(advs, pins)
        print(f"checked {args.check} against {len(advs)} advisories "
              f"({len(open_advs)} currently open)\n")
        if bad:
            print("STILL VULNERABLE:")
            for pkg, ver, gid, sev, rng in bad:
                print(f"  {pkg}=={ver}  {gid} ({sev})  range {rng}")
            return 1
        print(f"every pinned package clears every advisory ({args.check})")
        return 0

    if not open_advs:
        print("no open advisories")
        return 0

    print(f"open advisories: {len(open_advs)}\n")
    floors = compute_floor(open_advs)
    print("installable floor per package:")
    for pkg, (ver, why) in floors.items():
        if ver:
            print(f"  {pkg:<24} {ver}")
        else:
            print(f"  {pkg:<24} UNRESOLVED ({why})")
    print()
    print("advisory floor computed; pass --check <requirements> to verify pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
