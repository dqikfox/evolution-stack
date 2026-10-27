---
name: code-review-light
description: Pre-commit review for secrets, syntax, and bulk payload.
---

# Lightweight Code Review

## When to Use
- "review this PR"
- "check this code before commit"
- Before any auto-merge to main
- Standing pre-commit hook

## Review pipeline (6 steps, run in order)
1. **git status + diff size**: `git diff --stat HEAD`. If >1000 lines, stop and ask user — likely too big for one PR.
2. **Payload check (untracked bulk)**: list untracked files with sizes. A zip of the repo, its extraction directory, downloaded tooling, debug screenshots, and probe output are scratch, not work — verify the copy, delete it, and gitignore the pattern. Flag any single untracked file >10 MB and any directory that mirrors the repo root.
3. **Secrets scan**: use the real scanner, not a grep. A grep for `(api[_-]?key|password|token|secret|bearer)\s*[:=]\s*['"]` only matches an assignment with a secret-sounding NAME, so it misses a credential pasted into prose, a README, a note or a chat transcript, and it misses a webhook URL because the name ends in `_URL`. Run `python -m evo sweep <paths>` (or `from evo.secrets import scan_file`), which applies the name-independent rules too. Fail if any match outside `*.example` files.
   - **Prove the negative.** A clean result is only meaningful if the scanner has been shown to detect something. Plant a synthetic key in a scratch file, run the scanner, and confirm it fires. A scanner that reports 0 because its rules are broken is indistinguishable from a scanner that reports 0 because the code is clean.
   - **Never trust a sweep that has not scanned anything.** Confirm the commit count the sweep reports matches `git rev-list --all --count` for each repository. "0 findings across 0 commits" is not a pass.
   - **Surface every refusal.** If the scanner or the mirror refuses a file, that refusal must appear in the output. A refusal nobody sees looks exactly like a clean run, and the credential stays in the clear in the working tree.
4. **Syntax check**: for each modified `.py`, run `python -m py_compile`. Fail on exit≠0.
5. **Import sanity**: `python -c "import <changed_module>"` for each top-level change.
6. **Test smoke**: if `tests/` exists, run `python -m pytest tests/ -x --timeout=10 -q`.

## Secret guards (pre-commit and pre-push)

A guard is a scanner, and a scanner that cries wolf gets switched off — a switched-off scanner is worse than none. Two rules govern how to write one and how to fix one.

**Judge the VALUE's shape, not the assignment's length.** A check of the form `(API_KEY|SECRET|TOKEN|PASSWORD)\s*=\s*['\"]?[A-Za-z0-9_/+=.-]{30,}` is a NAME plus a LENGTH: it cannot tell a credential from a synthetic fixture, so it blocks every push as soon as a test file with a deliberately redacted token lands. Delegate the assignment check to the estate scanner (`evo.secrets`, wrapped by `evolution-stack/tools/scan_tracked_secrets.py` for tracked files) and keep a literal vendor-prefix check (`ghp_`, `sk-`, `ops_eyJ`, `A3-...`) alongside it — a match on a published token format IS the credential.

**Never widen a secret guard to unblock a push.** Relaxing a rule to get past a block removes the protection the guard exists to provide. Fix the matcher instead.

**An opt-out marker belongs to the gate, not to the shared scanner.** `# secret-guard: allow` is honoured per line by the pre-push tool only. If the shared scanner honoured it, a marker set beside a real key would let that key be published by the surface mirror, which publishes to a PUBLIC repository. The marker relaxes the local gate only, and the vendor-prefix check still fires on the same line.

**Prove the guard both ways.** After changing a guard, run it against four cases: the real repo (allow), a planted real token (block), the same token with the allow marker (still block), and a clean repo (allow). A guard that blocks everything is broken, and so is one that blocks nothing.

**Beware the redacted display.** Tool output may mask or truncate a secret-shaped value. Never conclude a value's length or content from rendered text — dump the raw bytes and count them, or you will misdiagnose a matcher that is working correctly.

## Soft checks (warn, don't block)
- Files touched > 20
- New > 200 lines without a test
- Hardcoded localhost IPs that aren't 127.0.0.1
- print() statements in non-script files
- Untracked bulk (archives, extractions, downloaded binaries) staged for commit
- A repo copy inside the repo (self-copy) — verify, delete, gitignore

## Output format
```
REVIEW: PASS|WARN|FAIL
SECRETS: clean|FOUND (file:line)
SYNTAX: N files ok, M failed
TESTS: X passed, Y failed
PAYLOAD: clean|N scratch items removed (list)
NOTES: ...
```

## Do not
- Push commits without user approval
- Auto-merge to main
- Run destructive git ops (reset, force-push)
- Open PRs to repos not in the user's `dqikfox/*` namespace