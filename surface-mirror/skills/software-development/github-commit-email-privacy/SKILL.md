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

**Use the NATIVE git, always.** A bash shell resolves `git` to `/usr/bin/git`
(MSYS, 2.53.0); the native one is `C:\Program Files\Git\cmd\git.exe`
(2.55.0). The MSYS git resolves the repository from `$PWD`, gets an MSYS path,
and fails with `fatal: not a git repository: '/c/Users/.../.git'`. The same
command works from a native parent. So:

    GIT = r"C:\Program Files\Git\cmd\git.exe"     # not "git"
    subprocess.run([GIT, "filter-branch", ...], cwd=repo, env=env_without_PWD)

Three things are needed together: the native git by absolute path, the cwd
already inside the repo, and `PWD`/`OLDPWD` dropped from the environment.

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

## A rewrite must keep the history CONNECTED

`git filter-branch` re-creates every commit it walks, and it cannot re-sign a GPG-signed commit, so it drops the signature - the commit's SHA changes even when the author, committer, tree, dates and message are all identical.

On a signed repository that leaves the rewritten history with NO common ancestor with the original. `git merge-base` between the old and the new tip is empty, git's push negotiation has nothing to negotiate against, and the push has to carry the WHOLE repository. On dqikfox/faraday that was 1,177 MB for a branch that had nothing to fix, and the pack builder crawled for 40 minutes at 0% CPU.

**The rule: a commit whose metadata is unchanged AND whose parent is unchanged IS the same object. Reuse it.** Only a commit that needs a new identity, or that sits below one that does, gets a new object.

With that rule the shared ancestors keep their SHAs, the old and the new history still share a common base, and the push carries a delta. Measured on faraday: 188 commits reused, 85 re-created, and the pack fell from 1,177 MB to 128 MB.

Use `rewrite_keep_history.py`, not `filter-branch`. `rewrite_remote.py` calls it.

**A branch that never had a local identity must not be pushed at all.** faraday's `main` was 94 third-party commits with no local identity in it; rewriting and pushing it was pure waste.

**Diagnose with `git merge-base <old-tip> <new-tip>`.** An empty result means the history is disjoint and the push will be a whole-repository upload. A non-empty result means the push is a delta.

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

**BUT do steps 2-4 AFTER the push, not before.** This is the single most
expensive mistake in this whole procedure, and it cost a 40-minute stall on a
1.28 GB repo.

Git's push negotiation works by the CLIENT offering the server the commits
it already has; the server's current tip is the common base. Steps 2-4 delete
that base, so the client and the server end up with **no common ancestor** -
and then the pack has to carry the ENTIRE repository instead of a small
delta. On `dqikfox/QHYSICS` (1.28 GB of Unity textures and LFS assets) that
turned a 2 MB publish into a 1.28 GB upload, and `git pack-objects` crawled
for 40 minutes at 0% CPU before the run had to be killed.

The order that works:

    rewrite  ->  backup bundle  ->  PUSH  ->  delete refs/original  ->  gc

The same push, with the base restored, took 1m49s and the server resolved
3290 deltas from 69 local objects.

If a push has already been run against a pruned clone, restore the base with a
plain fetch and push again - the fetch is fast, because the server serves
only what is missing:

    git fetch origin "+refs/heads/<branch>:refs/remotes/origin/<branch>"
    git push --force-with-lease=<branch>:<old-sha> origin <branch>:<branch>

## The push

`--force-with-lease` needs a lease to compare against, and after step 1 the
remote-tracking ref is fresh, so it works. If it still fails with
`stale info`, name the SHA you just observed:

    git ls-remote --heads origin main        # -> <sha>
    git push --force-with-lease=main:<sha> origin main:main

**A push must never be able to hang, and never be able to ask a question.**

- `GIT_TERMINAL_PROMPT=0` turns a credential prompt into an immediate
  failure instead of an infinite wait. Git Credential Manager has an
  interactive browser flow that will sit there for hours in a
  non-interactive session.
- `GIT_LFS_SKIP_PUSH=1` skips the `git-lfs` pre-push hook. **A commit-metadata
  rewrite changes no LFS object**, so re-uploading them is pure waste - and
  on a repo with 53 LFS pointers spread over 383 commits it was the thing
  that stalled the publish.
- Give the push a wall-clock timeout. A publish that has not finished in 30
  minutes is not going to finish, and it must fail loudly.

**A stalled push looks like a working one.** The symptom was `git.exe` at
0.03s of CPU for 40 minutes with an ESTABLISHED connection to GitHub - it
reads as "slow" but it was the pack builder grinding through 1.28 GB with no
common ancestor. Check the remote ref before assuming a push is still
working: if the SHA has not moved, nothing has landed.

Push EVERY branch the remote has, not just the default one. A branch that
exists on the remote but not locally fails with "src refspec does not match
any", so fetch each one into `refs/heads/` first:

    git fetch origin "<branch>:refs/heads/<branch>"

A repo with 173 remote branches needs all 173 fetched and pushed, not just
the default branch.

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

## Verify EVERY branch through the API, not the local repo

    gh api "repos/dqikfox/<repo>/commits?per_page=100" \
      --jq ".[].commit.author.email"

Every line must be `dqikfox@users.noreply.github.com`. Page through the WHOLE
history, check every branch, and check the remote - a clean local repo proves
nothing.

**An audit that checks only the default branch is NOT an audit.** Checking
`master` and `main` across 67 repos reported "0 unlinked local identities"
while 29 branches across NEXUS, vision and ultron_agent still carried them on
the remote. vision alone has 173 branches. Use the tool that walks them all:

    python verify_all_branches.py              # every dqikfox repo
    python verify_all_branches.py dqikfox/vision

It names the offending BRANCH, not just the repo.

**An audit that cannot DETECT is not an audit.** The first version of
`verify_all_branches.py` had a jq expression that escaped its inner quotes:

    ".[] | \"\\(.author.login // \\\"UNLINKED\\\")|\\(.commit.author.email)|\\(.sha)\""

jq rejects that with `unexpected token "\"`. `gh` exits non-zero, the
pagination loop `break`s, and the branch is recorded as **CLEAN**. A broken
query can only ever produce a false all-clear - the most dangerous possible
failure for the tool that certifies the account.

Three rules that came out of it:

- **An API error is a first-class ERROR, never an empty hit list.** A
  refusal and a clean branch must never look the same.
- **The expression lives in one named constant** (`JQ_COMMIT`), so the
  escaping cannot be got wrong twice.
- **The tool must prove it can still find a known offender.** It has a
  `--selftest` that checks the query parses AND that it detects the
  real offender on `dqikfox/QHYSICS@reality-engine`. Run it before trusting
  a clean result.

    python verify_all_branches.py --selftest

An audit that reports "every branch clean" after a rate limit has told you
nothing about the account. It has told you the tool was not working.

**Why the remote kept the old history:** the rewrite fetched the UNREWRITTEN
remote branches into `refs/heads/` and pushed them straight back. A branch
that only ever existed on the remote was never in the local ref set, so
filter-branch never rewrote it, and the push silently republished it. The
rewrite has to happen against the REMOTE state - see `rewrite_remote.py`.

## Before rewriting

Take a bundle and VERIFY it. A backup that cannot be restored is not a backup.

    git bundle create ../<repo>-history.bundle --all
    git bundle verify ../<repo>-history.bundle

## Audit the whole account in ONE local pass, not one API page at a time

Walking every commit of every branch through the commits endpoint is authoritative but it is O(branches x history) round trips. A repository with 173 branches, where one dependabot branch has 95 pages of history, will not finish in a useful time - and the account had 68 repositories. The API auditor was still running after twenty minutes with 34 of 68 done.

What works is a **treeless bare clone** and ONE local pass:

    git clone --bare --filter=tree:0 --no-tags https://github.com/dqikfox/<repo>.git <dir>
    git -C <dir> log --all --no-merges --format='%H|%ae|%an'

That is the same coverage in one pass per repository: 12 seconds for the 173-branch repository, against 884 seconds for the API version. Keep the API for the three things only it can do:

- **PROOF** - for every commit the local scan flags, fetch it through the commits endpoint and read `.author.login`. The local email match is a LEAD; the API is the VERDICT.
- **CONTROL** - walk the default branch of every repository through the API as well, and require the two scans to agree. A local pass that disagrees FAILS the run instead of reporting a clean account.
- **POSITIVE CONTROL** - scan a synthetic repository carrying a planted local identity first. A scan that cannot see a known offender proves nothing about the ones it did not see.

    python verify_all_branches_fast.py              # every dqikfox repo
    python verify_all_branches_fast.py dqikfox/vision

Three defects fell out of writing it, and all three are traps in any identity audit:

- **The offence is the email AND the link, not either one.** An author with no GitHub account has a null `author.login`, so the expression substitutes `UNLINKED` - and a third party's bot commit (the Manus AI fix bot) is unlinked too. Flagging `UNLINKED` on its own produced four false positives on the largest repository in the account. The rule is `login == "UNLINKED" AND email in BAD`.
- **URL-ENCODE the branch name before it goes into an API path.** A branch carrying an emoji came back as an HTML error page, the JSON parser failed with `invalid character '<' looking for beginning of value`, and that branch was silently skipped on the largest repository. A branch that could not be audited is not a clean branch.
- **One identity set, shared, lower-cased, compared case-insensitively.** Two auditors with two sets produce two verdicts about the same repository - the API one held `Shadow@SHADOW-EOKGST4R` in mixed case and the other did not.

## The tools

They live at `C:/Users/KING/AppData/Local/hermes/scripts/git_identity/`:

- `rewrite_local_identities.py` - the selective rewrite (the env-filter, the
  native git, the lease push). Import and call `rewrite(name, repo)`.
- `rewrite_remote.py` - the CORRECT one when the remote is the thing that
  must change. It clones the remote into a BARE clone, rewrites every ref
  there, pushes every branch with an explicit lease, then re-clones the
  remote and verifies the result. A bare clone has no working tree, so a
  dirty tree or a filename NTFS cannot recreate cannot block it.

      python rewrite_remote.py vision=https://github.com/dqikfox/vision.git

  Do NOT use a `--mirror` clone for this: it sets `remote.origin.mirror`, and
  every push then fails with `--mirror can't be combined with refspecs`.
- `verify_all_branches.py` - audits EVERY branch of EVERY repo and names the
  offending branch, through the API.
- `verify_all_branches_fast.py` - the same coverage in one local pass per
  repository, with the API for the proof, the control and the positive
  control. Use this for a whole-account audit.
- `rewrite_queue.py` - runs a list of repos from a JSON file. The paths live
  in the FILE, because argv goes through the MSYS argument conversion.
- `push_all_branches.py` - fetch every remote branch, then push each one
  with an explicit lease. **Careful:** fetching first can republish the
  UNREWRITTEN remote branches. Use `rewrite_remote.py` instead.

    python rewrite_queue.py queue.json

A `queue.json` is:

    {"repos": [{"name": "lummings", "path": "C:/Users/KING/projects/lumming"}]}

**Always prove the filter on a throwaway repo first** - one local-identity
commit, one bot commit, one dqikfox commit - and confirm the local identities
changed while the bot's did not. A filter that matches nothing reports success
and changes nothing.

**And verify the count changed.** The script prints
`local-identity commits N -> M`. If N == M, the filter did not fire.
