---
name: github-commit-email-privacy
description: Fix GH007 private-email block when pushing a new repo.
---

# GitHub commit email privacy (GH007)

When you `git push` a fresh repo, GitHub rejects commits whose author/committer email is set to a private email that you have not authorized. The error is:

```
remote: error: GH007: Your push would publish a private email address.
 ! [remote rejected] ... (push declined due to email privacy restrictions)
```

## The fix

Always use the GitHub-provided noreply email as the committer email:

```bash
git config user.email "dqikfox@users.noreply.github.com"
git config user.name  "Hitchy"
```

Where `<login>` is your GitHub username.

## If you already committed with the wrong email

Rewrite the author on the existing commit and force-push:

```bash
git filter-branch -f --env-filter "
  GIT_AUTHOR_NAME='Hitchy'
  GIT_AUTHOR_EMAIL='dqikfox@users.noreply.github.com'
  GIT_COMMITTER_NAME='Hitchy'
  GIT_COMMITTER_EMAIL='dqikfox@users.noreply.github.com'
"
git push origin main --force
```

## Why it happens

GitHub's `Keep my email addresses private` setting (Settings → Emails) blocks pushes that would expose your primary email. The fix is the noreply email which is always allowed.

## Pitfalls

- Setting `user.email` only affects future commits. Existing commits still carry the bad email in their metadata.
- `git commit --amend --reset-author --no-edit` only changes the latest commit.
- `filter-branch` rewrites history; only safe on repos that haven't been pushed yet, OR with `--force` on a private repo you own.
- For repos with many commits, `git rebase -i --root` and reword/replay is cleaner than filter-branch.
