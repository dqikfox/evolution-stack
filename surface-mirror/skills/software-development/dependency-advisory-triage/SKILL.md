---
name: dependency-advisory-triage
description: Use when clearing dependency security advisories in a repo.
type: skill
version: 1.0.0
author: THRONE
license: private
metadata:
  hermes:
    tags: [security, dependencies, advisories, dependabot, packaging, python]
    related_skills: [python-environment-management, code-review-light]
---

# Dependency Advisory Triage

## When to Use
- A dependency feed (Dependabot, `pip-audit`, an SBOM scan) reports open advisories against a repo.
- The user asks to clear dependency vulnerabilities, or a push/banner reports a vulnerability count.
- You need to raise a pin and be able to PROVE the new pin is safe rather than assume it.

## The rule

The deliverable is a **provable installable floor**, not "the version the advisory names". Three things make an advisory's `first_patched_version` the wrong target:

1. It may be **yanked** on PyPI — published then pulled, so it is not a version anyone should pin.
2. The version **below** it may still sit inside a *different* advisory's range, so "one step down" is not a fallback.
3. An advisory with **no** `patched_version` is cleared by pinning **above** its range. There may never be an upstream fix to wait for.

## Workflow

1. **Enumerate the alerts.**
   `gh api repos/<owner>/<repo>/dependabot/alerts --paginate`
   Note `state` — `fixed` and `open` advisories for the same package usually mean two different manifests.
   The list paginates at 30 per page, so `--paginate` is not optional: an open advisory that lands on page 2 is exactly the one you need to see.

2. **Fetch each advisory's real data.**
   `gh api advisories/<GHSA-ID>` → `vulnerabilities[0].vulnerable_version_range` and `.first_patched_version`.
   - The path needs a **slash**: `advisories/GHSA-...`, not `advisories GHSA-...`.
   - `first_patched_version` is an object in some responses and a **string** in others; a `--jq` expression for `.identifier` then fails with "expected an object but got: string". Parse the JSON in Python rather than in jq.

3. **Read the ranges, not just the patched versions.** Two advisories for one package can be cleared by very different floors. An advisory with no patched version contributes an upper bound you must exceed.

4. **Check the candidate floor for yanks.**
   `https://pypi.org/pypi/<pkg>/json` → `releases[<ver>][i]["yanked"]`. A yanked release is not a floor, and the version below it may still be vulnerable, so walk **up** the release list until a non-yanked version clears every range.

5. **Evaluate ranges as a conjunction.** A comma-separated range is AND, not OR — see `references/version-range-semantics.md`.

6. **Run the negative control.** The same check must FAIL against the old pins. A check that passes on both the old and the new pins is not a check; it will not notice a regression either.

7. **Prove the manifest resolves.**
   `uv pip compile <requirements-file> --python-version 3.11` — individually-safe pins can still conflict, and a set of safe pins can still pull a yanked transitive. A resolution warning about a yanked package is part of the answer, not noise.

8. **Push, then say what the count will do.** The advisory feed re-scans on its **own schedule**; the repo's vulnerability badge will not drop the moment you push. Your verification is the version check you ran, not the badge.

## Script

`scripts/compute_security_floor.py` does steps 1-6 in one call: enumerates the advisories for a repo, computes the installable floor per package honouring yank flags and conjunction ranges, and checks a manifest's pins against every advisory the repo has ever had.

```
python scripts/compute_security_floor.py --repo dqikfox/NEXUS
python scripts/compute_security_floor.py --repo dqikfox/NEXUS --check requirements-optional.txt
```

Exit code 0 = every advisory cleared, 1 = a pin is still inside a vulnerable range, 2 = the advisory feed could not be read (never report a clean result for an unread feed).

A `--check` is evaluated against **every** advisory the repo has ever had, not only the open ones. Checking only the open alerts makes the tool vacuous once the triage is done: with nothing open, ANY manifest passes, including the pins that caused the alerts. A `fixed` alert still describes a real vulnerable range, and a pin inside it is still vulnerable.

## Pitfalls

- **A compound range is a conjunction.** `>= 4.49.0, < 4.51.0` means the version must satisfy BOTH clauses. Evaluated as a disjunction, every version above the lower bound is reported vulnerable — which makes a correct fix look broken and sends you hunting for a nonexistent problem.
- **`first_patched_version` can be null.** Absence of a patched version is not absence of a fix; check the range's upper bound.
- **A yanked version is not a floor.** Read the yank flag from PyPI, and never read the advisory alone and trust it.
- **A pin range is not a fix.** Replacing `==` with `>=` does not clear an advisory and deletes the floor you are trying to establish. Keep exact pins for the packages under advisory.
- **A check that only looks at OPEN alerts is vacuous after triage.** Once Dependabot closes the alerts, an open-only check returns success for any manifest — including the vulnerable pins that caused them. Evaluate a manifest against every advisory the repo has ever had, and always run the negative control against the old pins.
- **The badge is not the verification.** The feed re-scans later. Verify the resolved versions yourself and report the badge as pending.
- **A dependency the service never imports is still worth pinning.** The pin is what a future `pip install -r` will fetch, and the vulnerable version is what a teammate inherits.
- **Do not bump a whole dependency tree to fix one advisory.** Raise the floors the advisories require, and let the resolver pull the rest.
