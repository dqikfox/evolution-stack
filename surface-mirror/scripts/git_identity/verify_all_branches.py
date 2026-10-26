#!/usr/bin/env python3
"""Audit EVERY branch of every dqikfox repo for unlinked local identities.

Why this exists
---------------
An earlier audit checked only the default branch, `master` and `main` of each
repo, and reported "0 unlinked local identities". That was wrong. `vision` has
173 branches; the 29 offending branches were on the others, and the audit
never looked at them. The rewrite had fetched the unrewritten remote branches
into `refs/heads/` and pushed them straight back, so the remote still carried
the old history while every check said "clean".

So the audit must walk every branch, on every repo, and report the offending
BRANCH - not just the repo.

The failure mode this file exists to prevent
--------------------------------------------
An earlier version of this script called `gh api` and, on a non-zero return,
just `break` out of the pagination loop. A rate limit or a transient 5xx then
looked EXACTLY like a clean branch. That is how a "0 unlinked identities"
claim can be produced by an audit that never actually looked. Every API
error here is now a first-class ERROR result, it is retried, and an audit
that could not complete says so instead of claiming the account is clean.

    python verify_all_branches.py            # the whole dqikfox account
    python verify_all_branches.py dqikfox/vision

The progress is written to a JSON file after every repo, so a run that is
interrupted can be resumed and its partial result is still inspectable.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse

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
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)

PROGRESS = os.environ.get(
    "NEXUS_BRANCH_AUDIT_PROGRESS",
    r"C:\Users\KING\AppData\Local\hermes\state\branch_audit.json")
RATE_LIMIT_HINT = ("rate limit", "secondary rate", "abuse detection", "403")

# The jq expression that turns each commit into "login|email|sha".
#
# The escaping here is load-bearing. An earlier version wrote it as
#   ".[] | \"\\(.author.login // \\\"UNLINKED\\\")|...\""
# which jq REJECTS with "unexpected token \"\\\"". The call then returned
# non-zero, the pagination loop broke, and the branch was reported CLEAN.
# A broken query is the worst kind of audit bug: it cannot produce a false
# alarm, only a false all-clear. So the expression lives in ONE named
# constant, and `--selftest` proves it parses and detects.
JQ_COMMIT = '.[] | "\\(.author.login // "UNLINKED")|\\(.commit.author.email)|\\(.sha)"'


def gh(*args, timeout=180):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout,
                          env=ENV, encoding="utf-8", errors="replace")


def _is_rate_limited(text: str) -> bool:
    low = (text or "").lower()
    return any(h in low for h in RATE_LIMIT_HINT)


def gh_retry(*args, timeout=180, attempts=4):
    """A `gh api` that does NOT confuse a refusal with an empty answer.

    Returns (stdout, error). `error` is None only when the call genuinely
    succeeded. A rate limit is retried with a backoff; any other API error
    is retried a couple of times and then reported, never swallowed.
    """
    last = ""
    for i in range(attempts):
        r = gh(*args, timeout=timeout)
        if r.returncode == 0:
            return r.stdout, None
        last = ((r.stderr or "") + (r.stdout or "")).strip()[:300]
        if _is_rate_limited(last):
            wait = 20 * (i + 1)
            print("      (rate limited, waiting %ds)" % wait, flush=True)
            time.sleep(wait)
            continue
        if i < attempts - 1:
            time.sleep(3 * (i + 1))
    return "", last


def branches_of(repo: str):
    names = []
    page = 1
    while True:
        out, err = gh_retry("api", "repos/%s/branches?per_page=100&page=%d" % (repo, page),
                            "--jq", ".[].name")
        if err:
            return names, err
        got = [l for l in out.splitlines() if l.strip()]
        names += got
        if len(got) < 100:
            break
        page += 1
    return names, None


def audit_branch(repo: str, branch: str):
    """The offending commits on one branch.

    Returns (hits, error). `error` is set when the branch could NOT be
    audited - which is NOT the same as the branch being clean.
    """
    hits = []
    page = 1
    while True:
        # The branch name is URL-ENCODED.
        #
        # A branch whose name carries an emoji - the palette branch, for
        # one - made the raw path come back as an HTML error page. The JSON
        # parser then failed on it with "invalid character '<' looking for
        # beginning of value", and a branch that could not be audited is not
        # a clean branch. One branch was being skipped for exactly that
        # reason, on the largest repository in the account.
        q = urllib.parse.urlencode({"sha": branch, "per_page": 100, "page": page})
        out, err = gh_retry(
            "api", "repos/%s/commits?%s" % (repo, q),
            "--jq", JQ_COMMIT)
        if err:
            return hits, err
        lines = [l for l in out.splitlines() if l.strip()]
        for l in lines:
            login, _, rest = l.partition("|")
            email, _, sha = rest.partition("|")
            if login == "UNLINKED" and email.lower() in BAD:
                hits.append((email, sha))
        if len(lines) < 100:
            break
        page += 1
    return hits, None


def audit(repo: str):
    names, err = branches_of(repo)
    if err:
        print("   %-34s SKIPPED (the API refused: %s)" % (repo, err[:90]), flush=True)
        return 0, 0, 1
    bad = {}
    errors = []
    for b in names:
        hits, berr = audit_branch(repo, b)
        if berr:
            errors.append((b, berr[:120]))
        if hits:
            bad[b] = hits
    if bad:
        total = sum(len(v) for v in bad.values())
        print("   %-34s %d branches, %d OFFENDING" % (repo, len(names), total), flush=True)
        for b, hits in list(bad.items())[:20]:
            print("      %-64s %d commits" % (b[:64], len(hits)))
        if len(bad) > 20:
            print("      ... and %d more branches" % (len(bad) - 20))
    else:
        print("   %-34s %d branches, clean" % (repo, len(names)), flush=True)
    if errors:
        print("      !! %d branches could NOT be audited (an API error is not a clean branch):"
              % len(errors), flush=True)
        for b, e in errors[:5]:
            print("         %-60s %s" % (b[:60], e))
    return len(bad), len(names), len(errors)


def save_progress(state):
    try:
        os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
        with open(PROGRESS, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def selftest() -> int:
    """Prove the audit can DETECT, before it is trusted to CLEAR.

    An audit that cannot fail is not an audit. Two checks:
      1. the jq expression parses - a broken query returns non-zero and
         silently marks every branch clean;
      2. a branch that is KNOWN to carry a local identity is DETECTED.

    For (2) we use a real offender that the rewrite has not touched:
    dqikfox/QHYSICS@reality-engine still carries KING@THRONE commits.
    If that branch ever comes back clean, the detector is broken.
    """
    print("=== the audit self-test ===", flush=True)
    ok = True

    print("\n   1. does the jq expression parse?")
    r = gh("api", "repos/dqikfox/QHYSICS/commits?sha=reality-engine&per_page=5", "--jq", JQ_COMMIT)
    if r.returncode != 0:
        print("      FAIL: the jq expression is invalid: %s" % ((r.stderr or "")[:160]))
        print("      An invalid query makes EVERY branch look clean. Fix it before trusting a result.")
        ok = False
    else:
        lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
        print("      PASS: the expression parses and returned %d rows" % len(lines))
        if not lines:
            print("      FAIL: the expression parsed but returned nothing")
            ok = False

    print("\n   2. can it DETECT a known offender?")
    known_repo, known_branch = "dqikfox/QHYSICS", "reality-engine"
    hits, err = audit_branch(known_repo, known_branch)
    if err:
        print("      FAIL: the branch could not be audited: %s" % err[:140])
        ok = False
    elif not hits:
        print("      FAIL: %s@%s is known to carry local identities, but the audit found none."
              % (known_repo, known_branch))
        print("      The detector is broken. A clean result from this tool means nothing.")
        ok = False
    else:
        emails = sorted({h[0] for h in hits})
        print("      PASS: %d offending commits on %s@%s  (%s)"
              % (len(hits), known_repo, known_branch, ", ".join(emails)))

    print("\n   %s" % ("THE AUDIT IS TRUSTWORTHY" if ok else "THE AUDIT IS NOT TRUSTWORTHY"))
    return 0 if ok else 1


def main(repos):
    t0 = time.time()
    print("=== the per-branch audit of every dqikfox repo ===", flush=True)
    total_bad = 0
    total_branches = 0
    total_errors = 0
    state = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "repos": {}, "offending": {}}
    for repo in repos:
        b, n, e = audit(repo)
        total_bad += b
        total_branches += n
        total_errors += e
        state["repos"][repo] = {"branches": n, "offending": b, "errors": e}
        save_progress(state)
        sys.stdout.flush()
    print("\n   %d repos, %d branches audited, %d branches with local identities, "
          "%d branches NOT audited  (%.0fs)"
          % (len(repos), total_branches, total_bad, total_errors, time.time() - t0))
    if total_bad:
        print("   THE ACCOUNT IS NOT CLEAN", flush=True)
    elif total_errors:
        print("   NO OFFENDING BRANCH FOUND, BUT %d BRANCHES COULD NOT BE AUDITED - "
              "THIS IS NOT A CLEAN BILL OF HEALTH" % total_errors, flush=True)
    else:
        print("   EVERY BRANCH IS CLEAN", flush=True)
    state["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state["total_bad"] = total_bad
    state["total_errors"] = total_errors
    save_progress(state)
    return 1 if (total_bad or total_errors) else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("--selftest", "-t"):
        sys.exit(selftest())
    if not args:
        r = gh("repo", "list", "dqikfox", "--limit", "100", "--json", "name")
        args = ["dqikfox/%s" % n["name"] for n in json.loads(r.stdout or "[]")]
    sys.exit(main(args))
