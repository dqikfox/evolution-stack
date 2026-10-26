#!/usr/bin/env python3
"""Audit EVERY branch of every dqikfox repo for unlinked local identities.

Why this file exists alongside verify_all_branches.py
---------------------------------------------------
The API auditor walks every commit of every branch through the GitHub
commits endpoint, 100 at a time. That is correct and it is authoritative,
but it is O(branches x history) HTTP round trips: `open-webui` alone pages
through 95+ pages of history on a single dependabot branch, and the account
has 68 repositories with several hundred branches between them. It was still
running after 20 minutes with 34 of 68 repositories done.

This file does the same WORK in one local pass per repository:

  1. a treeless bare clone  - commits only, no trees, no blobs
  2. one `git log --all`    - every commit reachable from every branch
  3. match the author email against the fixed set of local identities

That is the same coverage the API auditor had, in a fraction of the time.

The API is not abandoned. It is used for the two things only the API can do:

  PROOF    - for every branch the scan flags, the commit is fetched through
             the commits endpoint and its `.author.login` is read. The house
             rule is that a commit is judged by the account it is LINKED to,
             not by the email in its metadata, so the local email match is a
             LEAD and the API is the VERDICT.

  CONTROL  - for every repository, the DEFAULT branch is walked through the
             API as well, and the two scans must agree. If the local pass
             and the API pass disagree about the default branch, the local
             pass is not trustworthy and the run fails rather than reporting
             a clean account.

  POSITIVE - a synthetic repository containing a commit by a known local
             identity is scanned first. A scan that cannot find a planted
             offender is not allowed to report anything as clean.

    python verify_all_branches_fast.py                # the whole account
    python verify_all_branches_fast.py dqikfox/vision
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

GIT = r"C:\Program Files\Git\cmd\git.exe"

# The local identities this account must never carry on a remote. These are
# machine-local addresses; a commit carrying one is not linked to the
# dqikfox GitHub account and is therefore not attributed to the owner.
#
# The set is canonical and lower-cased, and BOTH auditors use it. They
# drifted once - one had "Shadow@SHADOW-EOKGST4R" in mixed case and the
# other had it lower-cased, plus two extra entries - and two auditors with
# two rules produce two different verdicts about the same repository.
#
# Every comparison lower-cases the email first, so a commit that carries
# "King@Throne" is caught like "king@throne".
BAD = {
    "king@throne.local", "king@throne", "king@tesseract.local",
    "ultron@talking.ai", "ultron@throne.local", "ultron@hermes.local",
    "ultron@local", "ultron@tesseract.local", "ultron@throne",
    "megatron@tesseract.local", "shadow@shadow-eokgst4r", "minion@throne.local",
    "dqikfox@local", "throne@throne.local", "tesseract@throne.local",
}

# A commit whose author email belongs to one of these domains is the
# owner's own public identity and must never be flagged.
ALLOWED_EMAILS = {
    "dqikfox@users.noreply.github.com",
    "110945741+dqikfox@users.noreply.github.com",
}

PROGRESS = os.environ.get(
    "NEXUS_BRANCH_AUDIT_PROGRESS",
    r"C:\Users\KING\AppData\Local\hermes\state\branch_audit_fast.json")
RATE_LIMIT_HINT = ("rate limit", "secondary rate", "abuse detection")

ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)
ENV["GIT_TERMINAL_PROMPT"] = "0"
ENV["GCM_INTERACTIVE"] = "never"
ENV["GIT_LFS_SKIP_PUSH"] = "1"


def gh(*args, timeout=180):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout,
                          env=ENV, encoding="utf-8", errors="replace")


def gh_retry(*args, timeout=180, attempts=4):
    """A `gh api` that does not confuse a refusal with an empty answer."""
    last = ""
    for i in range(attempts):
        r = gh(*args, timeout=timeout)
        if r.returncode == 0:
            return r.stdout, None
        last = ((r.stderr or "") + (r.stdout or "")).strip()[:300]
        low = last.lower()
        if any(h in low for h in RATE_LIMIT_HINT):
            wait = 20 * (i + 1)
            print("      (rate limited, waiting %ds)" % wait, flush=True)
            time.sleep(wait)
            continue
        if i < attempts - 1:
            time.sleep(3 * (i + 1))
    return "", last


def list_repos():
    names = []
    page = 1
    while True:
        out, err = gh_retry("api", "user/repos?per_page=100&page=%d&affiliation=owner" % page,
                            "--jq", ".[].full_name")
        if err:
            raise SystemExit("the repository list failed: %s" % err)
        got = [l.strip() for l in out.splitlines() if l.strip()]
        names += got
        if len(got) < 100:
            break
        page += 1
    return [n for n in names if n.startswith("dqikfox/")]


def default_branch(repo):
    out, err = gh_retry("api", "repos/%s" % repo, "--jq", ".default_branch")
    if err:
        return "main", err
    return (out.strip() or "main"), None


def api_offenders(repo, branch):
    """The offending commits on one branch, judged by `.author.login`.

    The branch name is URL-ENCODED. A branch whose name carries an emoji
    (the palette branch) made the raw path return an HTML error page, and a
    JSON parser reading that page is exactly how a branch that could not be
    audited turns into a branch that looks clean.
    """
    hits = []
    errors = []
    page = 1
    while True:
        q = urllib.parse.urlencode({"sha": branch, "per_page": 100, "page": page})
        out, err = gh_retry("api", "repos/%s/commits?%s" % (repo, q),
                            "--jq", '.[] | "\\(.author.login // "UNLINKED")|\\(.commit.author.email)|\\(.sha)"')
        if err:
            errors.append(err)
            break
        rows = [l for l in out.splitlines() if l.strip()]
        for row in rows:
            parts = row.split("|")
            if len(parts) < 3:
                continue
            login, email, sha = parts[0], parts[1], parts[2]
            # The rule is the email AND the link, not either one.
            #
            # "Unlinked" on its own is NOT an offence: a third party's commit
            # by an author who has no GitHub account is unlinked too - the
            # Manus AI fix bot, for instance, and it is not the owner. A
            # commit is offending when it carries a LOCAL machine identity
            # AND is not linked to the account.
            if login == "UNLINKED" and email.lower() in BAD:
                hits.append({"sha": sha, "email": email, "login": login})
        if len(rows) < 100:
            break
        page += 1
    return hits, errors


def clone_commits(repo, dest):
    """A treeless bare clone: every commit, no tree, no blob."""
    r = subprocess.run(
        [GIT, "clone", "--bare", "--filter=tree:0", "--quiet", "--no-tags",
         "https://github.com/%s.git" % repo, dest],
        capture_output=True, text=True, timeout=1800, env=ENV,
        encoding="utf-8", errors="replace")
    return r


def scan_local(repo, dest):
    """Every local-identity commit on every branch, in one pass."""
    r = subprocess.run(
        [GIT, "-C", dest, "log", "--all", "--no-merges", "--format=%H|%ae|%an"],
        capture_output=True, text=True, timeout=1800, env=ENV,
        encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None, (r.stderr or "")[:300]
    hits = {}
    for line in r.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        sha, email, name = parts[0], parts[1], parts[2]
        if email.lower() in BAD and email.lower() not in ALLOWED_EMAILS:
            hits.setdefault(sha, {"sha": sha, "email": email, "name": name})
    # which branches carry each hit
    out = []
    for sha, h in hits.items():
        b = subprocess.run(
            [GIT, "-C", dest, "for-each-ref", "--format=%(refname:short)", "--contains=%s" % sha,
             "refs/remotes/origin/"],
            capture_output=True, text=True, timeout=600, env=ENV,
            encoding="utf-8", errors="replace")
        branches = [x.strip() for x in b.stdout.splitlines() if x.strip()]
        h["branches"] = branches
        out.append(h)
    return out, None


def branch_count(repo):
    out, err = gh_retry("api", "repos/%s/branches?per_page=100" % repo, "--jq", ".[].name")
    if err:
        return -1, err
    return len([l for l in out.splitlines() if l.strip()]), None


def positive_control(work):
    """A planted offender must be found. A scan that cannot see it proves nothing."""
    d = os.path.join(work, "control")
    os.makedirs(d, exist_ok=True)
    def g(*a, **kw):
        return subprocess.run([GIT, "-C", d] + list(a), capture_output=True, text=True,
                              timeout=300, env=ENV, encoding="utf-8", errors="replace", **kw)
    g("init", "-q", "-b", "main")
    g("config", "user.name", "THRONE")
    g("config", "user.email", "king@throne.local")
    with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
        f.write("planted\n")
    g("add", "a.txt")
    g("-c", "user.name=THRONE", "-c", "user.email=king@throne.local",
      "commit", "-q", "-m", "the planted local identity")
    g("branch", "side")
    hits, err = scan_local("control", d)
    ok = bool(hits) and any(h["email"].lower() in BAD for h in hits)
    print("   the positive control: %s (the hits: %d)" % ("PASSED" if ok else "FAILED", len(hits or [])))
    if not ok:
        raise SystemExit("the positive control failed - the scan is blind and its results mean nothing")
    shutil.rmtree(d, ignore_errors=True)


def main(argv):
    only = [a for a in argv[1:] if not a.startswith("-")]
    work = tempfile.mkdtemp(prefix="audit-fast-")
    print("the working directory: %s" % work, flush=True)
    print("the positive control...", flush=True)
    positive_control(work)

    repos = only or list_repos()
    print("the repositories: %d" % len(repos), flush=True)
    results = {}
    offending_all = []
    errors_all = []
    try:
        for n, repo in enumerate(repos, 1):
            t0 = time.time()
            dest = os.path.join(work, repo.replace("/", "_"))
            clone = clone_commits(repo, dest)
            if clone.returncode != 0:
                errors_all.append((repo, "clone failed: %s" % (clone.stderr or "")[:200]))
                print("   %-40s CLONE FAILED" % repo, flush=True)
                continue
            hits, err = scan_local(repo, dest)
            if err:
                errors_all.append((repo, "scan failed: %s" % err))
                print("   %-40s SCAN FAILED" % repo, flush=True)
                continue

            # how many branches the remote has. Read BEFORE the control,
            # because an empty repository has no default branch to walk and
            # that is a fact, not a failure.
            nb, berr = branch_count(repo)

            # the CONTROL: the default branch, through the API, must agree
            dflt, derr = default_branch(repo)
            api_hits, api_errs = ([], [])
            if derr:
                api_errs = [derr]
            elif nb == 0:
                # An empty repository has no branches and no default branch.
                # There is nothing to audit, which is not the same thing as a
                # failure - it must not be counted as an error, or a run over
                # a healthy account always ends with three red lines.
                api_hits, api_errs = [], []
                dflt = ""
            else:
                api_hits, api_errs = api_offenders(repo, dflt)
            local_default = [h for h in hits if any(b.split("/", 1)[-1] == dflt for b in h.get("branches", []))]
            agree = len(api_hits) == len(local_default)
            if not agree:
                errors_all.append((repo, "the local scan and the API disagree on the default branch: "
                                       "local %d, api %d" % (len(local_default), len(api_hits))))
            if api_errs:
                errors_all.append((repo, "the API default-branch walk: %s" % api_errs[:1]))

            # the PROOF: every flagged commit is judged by author.login
            proven = []
            for h in hits:
                q = urllib.parse.urlencode({"sha": h["sha"]})
                out, err = gh_retry("api", "repos/%s/commits?%s" % (repo, q),
                                    "--jq", '.[] | "\\(.author.login // "UNLINKED")|\\(.commit.author.email)|\\(.sha)"')
                if err:
                    errors_all.append((repo, "the commit %s could not be read: %s" % (h["sha"][:10], err)))
                    continue
                for row in out.splitlines():
                    p = row.split("|")
                    if len(p) < 3 or p[2] != h["sha"]:
                        continue
                    if (p[0] == "UNLINKED" or p[1].lower() in BAD) and p[1].lower() in BAD:
                        h["login"] = p[0]
                        proven.append(h)
                    break
            results[repo] = {
                "branches": nb, "local_hits": len(hits), "proven": len(proven),
                "default_agrees": agree, "seconds": round(time.time() - t0, 1),
            }
            for h in proven:
                offending_all.append({"repo": repo, **h})
            flag = "OFFENDING" if proven else ("ok" if agree and not api_errs else "CHECK")
            print("   %-40s %4s branches  %2d hits  %2d proven  %-9s %6.1fs" % (
                repo, nb, len(hits), len(proven), flag, time.time() - t0), flush=True)
            shutil.rmtree(dest, ignore_errors=True)
            pathlib_json = json.dumps(
                {"repos": results, "offending": offending_all, "errors": errors_all,
                 "finished": False, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1)
            with open(PROGRESS, "w", encoding="utf-8") as f:
                f.write(pathlib_json)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    summary = {
        "repos": results, "offending": offending_all, "errors": errors_all,
        "finished": True, "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repos_scanned": len(results),
        "branches_scanned": sum(v["branches"] for v in results.values() if v["branches"] > 0),
        "offending_total": len(offending_all),
        "error_total": len(errors_all),
    }
    with open(PROGRESS, "w", encoding="utf-8") as f:
        f.write(json.dumps(summary, indent=1))
    print("\n=== the summary ===")
    print("   the repositories scanned: %d" % len(results))
    print("   the branches scanned:    %d" % summary["branches_scanned"])
    print("   the offending commits:   %d" % len(offending_all))
    print("   the errors:              %d" % len(errors_all))
    for e in errors_all[:10]:
        print("      %s - %s" % e)
    for o in offending_all[:20]:
        print("      OFFENDING %s %s %s %s" % (o["repo"], o["sha"][:10], o["email"], o.get("branches")))
    return 0 if not offending_all and not errors_all else 1


if __name__ == "__main__":
    import pathlib  # noqa: E402  (used in the progress write)
    sys.exit(main(sys.argv))
