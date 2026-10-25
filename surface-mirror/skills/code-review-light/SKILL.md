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