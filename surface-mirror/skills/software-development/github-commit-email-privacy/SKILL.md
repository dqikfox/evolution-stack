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
      --env-filter "export GIT_AUTHOR_NAME='dqikfox'; \
                    export GIT_AUTHOR_EMAIL='dqikfox@users.noreply.github.com'; \
                    export GIT_COMMITTER_NAME='dqikfox'; \
                    export GIT_COMMITTER_EMAIL='dqikfox@users.noreply.github.com'" \
      -- --all

**Why not filter-repo:** the installed version (2.47.0, the newest on PyPI)
crashes on this host with `TypeError: %b requires a bytes-like object` in its
vendored fast-export writer, on every repo including a trivial one, and
reinstalling does not help. Core git's filter-branch has no Python dependency
and works. A 69-commit repo rewrites in about 46 seconds.

## After the rewrite - three things filter-branch leaves behind

1. **It removes the `origin` remote.** Re-add it and fetch:
   `git remote add origin <url>` then `git fetch origin --prune`.
2. **It leaves `refs/original/*` behind.** Those refs keep the OLD identity
   reachable and would be pushed as duplicate history. Delete them:
   `git for-each-ref --format='%(refname)' refs/original/ | xargs -n1 git update-ref -d`
3. **Then expire the reflog and gc**, or the old commits stay in the object
   store: `git reflog expire --expire=now --all && git gc --prune=now`.

## The push

`--force-with-lease` needs a lease to compare against, and after step 1 the
remote-tracking ref is fresh, so it works. If it still fails with
`stale info`, name the SHA you just observed:

    git ls-remote --heads origin main        # -> <sha>
    git push --force-with-lease=main:<sha> origin main:main

## Verify through the API, not the local repo

    gh api "repos/dqikfox/<repo>/commits?per_page=100" --jq ".[].commit.author.email"

Every line must be `dqikfox@users.noreply.github.com`. Check the whole history
by paging, and check the remote - a clean local repo proves nothing.

## Before rewriting

Take a bundle and VERIFY it. A backup that cannot be restored is not a backup.

    git bundle create ../<repo>-history.bundle --all
    git bundle verify ../<repo>-history.bundle
