---
name: github-commit-email-privacy
description: "Use when a git commit is rejected by GH007, or when the commit author must read as dqikfox on GitHub. Rewrites history with a tool that works on this host."
author: Hermes Agent
tags: [git, github, identity, gh007, filter-branch]
---

# GitHub commit identity

Every commit on every repo must be authored by the account, so GitHub attributes
it and links it to the profile.

    name:  dqikfox
    email: dqikfox@users.noreply.github.com

That is the noreply address, so it is always allowed. A private address such as
`ultron@throne.local` pushes fine but GitHub shows the commit as an unlinked
`ultron` with no avatar - it does not count toward the profile.

## A commit has THREE identities, not one

1. the raw author email in the commit object
2. the GitHub account GitHub linked it to
3. whether the work was actually a bot's

Only #1 needs fixing, and only when #2 came out UNLINKED.

    gh api "repos/dqikfox/<repo>/commits?per_page=100" \
      --jq '.[] | "\(.author.login // "UNLINKED")|\(.commit.author.email)"'

- **UNLINKED + a local machine identity** (KING@THRONE, ultron@talking.ai,
  king@throne.local, ultron@throne.local, ultron@hermes.local,
  Shadow@SHADOW-EOKGST4R) - Hitchy's own work, GitHub cannot attribute it.
  **Rewrite these.**
- **Linked to a bot** (Copilot, dependabot, google-labs-jules, Codex, semgrep,
  grok-export, manus-ai) - the bot really did that work. **Leave it alone.**
  Relabelling it as dqikfox is false attribution.
- **Linked to another human** (a third-party contribution) - **leave it alone.**
- `110945741+dqikfox@users.noreply.github.com` is already the account's own
  noreply form (110945741 is the account id) and links correctly. No change
  needed, though normalising it to the short form is harmless.

## The GH007 rejection

    remote: error: GH007: Your push would publish a private email address.

Set the identity and amend the unpushed commit:

    git config user.email "dqikfox@users.noreply.github.com"
    git config user.name  "dqikfox"
    git commit --amend --reset-author --no-edit

## Rewriting the WHOLE history

Use **git filter-branch**, not git filter-repo.

    FILTER_BRANCH_SQUELCH_WARNING=1 \
    git filter-branch -f \
      --env-filter "<filter>" \
      -- --all

**Why not filter-repo:** the installed version (2.47.0, the newest on PyPI)
crashes on this host with `TypeError: %b requires a bytes-like object` in its
vendored fast-export writer, on every repo including a trivial one, and
reinstalling does not help. Core git's filter-branch has no Python dependency
and works. A 69-commit repo rewrites in about 46 seconds.

## A SELECTIVE rewrite (the correct one)

Rewrite only the local identities and leave the bots alone. The env-filter is
a shell conditional:

    --env-filter '
      if printf "%s\n%s\n" "$GIT_AUTHOR_EMAIL" "$GIT_COMMITTER_EMAIL" | \
         grep -qxF -e "KING@THRONE" -e "ultron@talking.ai" -e "king@throne.local" ; then
        export GIT_AUTHOR_NAME="dqikfox"
        export GIT_AUTHOR_EMAIL="dqikfox@users.noreply.github.com"
        export GIT_COMMITTER_NAME="dqikfox"
        export GIT_COMMITTER_EMAIL="dqikfox@users.noreply.github.com"
      fi'

**Two ways to get this silently wrong:**

- joining the patterns with `|` makes a shell PIPE, not a grep alternation
- `printf "%%s"` reaches printf as a literal `%%s` and prints the characters
  `%s` instead of the email

Either mistake makes the filter match nothing, and the rewrite reports
success while changing nothing. **Always verify the count changed**, and
prove the filter on a throwaway repo with one local, one bot and one dqikfox
commit BEFORE touching a real repo.

## After the rewrite - what filter-branch leaves behind

1. **It removes the `origin` remote.** Re-add it and fetch:
   `git remote add origin <url>` then `git fetch origin --prune`.
2. **It leaves `refs/original/*` behind.** Those refs keep the OLD identity
   reachable and would be pushed as duplicate history:
   `git for-each-ref --format='%(refname)' refs/original/ | xargs -n1 git update-ref -d`
3. **The stale `refs/remotes/origin/<branch>` does the same.** Delete it too,
   or the old commits stay reachable and the count looks wrong.
4. **Then expire the reflog and gc**, or the old commits stay in the object
   store: `git reflog expire --expire=now --all && git gc --prune=now`.

## The push

`--force-with-lease` needs a lease to compare against, and after step 1 the
remote-tracking ref is fresh, so it works. If it still fails with
`stale info`, name the SHA you just observed:

    git ls-remote --heads origin main        # -> <sha>
    git push --force-with-lease=main:<sha> origin main:main

Push EVERY branch the remote has, not just the default one - fetch each remote
branch as a local branch first, or the push fails with "src refspec does not
match any".

## Three Windows-specific blockers

- **A stale `.git/index.lock`** left by a killed git blocks every later git
  command. Remove it, but only after confirming no `git.exe` is running.
- **A tracked file whose name contains double quotes** cannot exist on NTFS,
  so git reports it as deleted forever and refuses to rewrite. Fix with
  `git update-index --skip-worktree -- '<path>'`.
- **A live service writing runtime files** makes the tree permanently dirty.
  `git reset --hard` does not help - the service rewrites the files within
  seconds. Fix with `--skip-worktree` on each modified path, and save the
  uncommitted work first (`git diff --binary HEAD > patch`).

## Running it from a bash terminal on Windows

MSYS rewrites `C:/...` into `/c/...` when passing an argument to a native
program, and native git cannot read `/c/...`:

    export MSYS2_ARG_CONV_EXCL='*'
    "C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" script.py "name=C:/path"

The bare `python` on the bash PATH may not exist - use a full native path.

## Verify through the API, not the local repo

    gh api "repos/dqikfox/<repo>/commits?per_page=100" \
      --jq ".[].commit.author.email"

Every line must be `dqikfox@users.noreply.github.com`. Page through the WHOLE
history, check every branch, and check the remote - a clean local repo proves
nothing.

## Before rewriting

Take a bundle and VERIFY it. A backup that cannot be restored is not a backup.

    git bundle create ../<repo>-history.bundle --all
    git bundle verify ../<repo>-history.bundle
