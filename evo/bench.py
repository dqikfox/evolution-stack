"""The acceptance benchmark — objective ground truth for every proposed change.

Without this, "self-improvement" is a vibe. Every candidate patch is applied,
the stack is re-benchmarked, and the change is kept ONLY if the score improves.
Anything that regresses is rolled back automatically.

Score is a weighted percentage (0-100). Weights reflect blast radius:
a dead service hurts more than a stale doc.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, peers, services


@dataclass
class Check:
    name: str
    group: str
    weight: float
    passed: bool
    detail: str = ""
    elapsed: float = 0.0
    scored: bool = True   # False = reported, but not part of the gate score


@dataclass
class Scorecard:
    score: float
    checks: list[Check] = field(default_factory=list)
    gate_score: float = 0.0

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed(self) -> list[Check]:
        return [c for c in self.checks if c.passed]

    @property
    def gate_failures(self) -> list[Check]:
        """Failures the gate can actually act on (scored checks only)."""
        return [c for c in self.checks if not c.passed and c.scored]

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "gate_score": round(self.gate_score, 2),
            "total": len(self.checks),
            "failed": len(self.failures),
            "gate_failed": len(self.gate_failures),
            "checks": [
                {
                    "name": c.name, "group": c.group, "weight": c.weight,
                    "passed": c.passed, "detail": c.detail,
                    "elapsed": round(c.elapsed, 3), "scored": c.scored,
                }
                for c in self.checks
            ],
        }


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_json(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(4_000_000).decode("utf-8", "replace")
            return True, body
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- checks ----
def check_services() -> list[Check]:
    """Registry-driven service checks.

    - retired services are not checked at all (no implementation = no failure)
    - services with a documented start path are gate-actionable (healable)
    - services without one stay on the host score (operator action)
    """
    out: list[Check] = []
    for s in services.load():
        if s.status == "retired":
            continue
        t0 = time.time()
        st = services.status_of(s)
        up = st == "up"
        gate = up or s.healable
        detail = f":{s.port} {st}"
        if not up:
            detail += " — healable (documented start path)" if s.healable else " — operator-level"
        out.append(Check(
            name=f"service:{s.name}", group="services", weight=4.0, passed=up,
            detail=detail, elapsed=time.time() - t0, scored=gate,
        ))
    t0 = time.time()
    gw = _port_open(paths.GATEWAY_PORT)
    out.append(Check(
        name="service:gateway", group="services", weight=4.0, passed=gw,
        detail=f":{paths.GATEWAY_PORT} {'up' if gw else 'DOWN'}",
        elapsed=time.time() - t0,
    ))
    return out


def check_peers() -> list[Check]:
    """Remote peers are part of the estate.

    The distinction that matters is the same one the local check makes:
    a service with a documented start path is GATE-ACTIONABLE, and one
    without is operator-level. A peer service whose peer is reachable
    and whose service is down can be healed (the far side has a start
    path), so it counts against the gate. A peer that is UNREACHABLE
    cannot be healed by anyone - the machine is simply away - so it is
    reported and it lands on the host score, not the gate. A gate that
    fails for a machine that is switched off is a gate that cries wolf.
    """
    out: list[Check] = []
    for row in peers.survey():
        up = row["status"] == "up"
        if row["status"] == "unreachable":
            passed, scored, detail = True, False, row["detail"]
        else:
            gate = up or row["healable"]
            passed, scored = up, gate
            detail = f":{row['port']} {row['status']} on {row['ip']}"
            if not up:
                detail += " — healable on the peer" if row["healable"] else " — operator-level"
        out.append(Check(
            name=f"peer:{row['name']}", group="peers", weight=2.0, passed=passed,
            detail=detail, elapsed=row.get("elapsed", 0.0), scored=scored,
        ))
    return out


def check_nexus_api() -> Check:
    t0 = time.time()
    ok, body = _http_json("http://127.0.0.1:8650/health")
    return Check("nexus:health", "apis", 5.0, ok, body[:120], time.time() - t0)


def check_ollama_api() -> Check:
    t0 = time.time()
    ok, body = _http_json("http://127.0.0.1:11434/api/tags")
    models = 0
    if ok:
        try:
            models = len(json.loads(body).get("models", []))
        except Exception:
            pass
    return Check("ollama:tags", "apis", 4.0, ok and models > 0,
                 f"{models} models" if ok else body[:100], time.time() - t0)

def check_skills() -> list[Check]:
    out: list[Check] = []
    root = paths.SKILLS_DIR
    t0 = time.time()
    if not root.exists():
        return [Check("skills:dir", "surface", 6.0, False, f"missing {root}")]
    dirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    skills = [d for d in dirs if (d / "SKILL.md").exists()]
    nested = [d for d in dirs if not (d / "SKILL.md").exists() and list(d.glob("*/SKILL.md"))]
    broken = [d.name for d in nested if not list(d.glob("*/SKILL.md"))]
    out.append(Check(
        "skills:manifest", "surface", 6.0, not broken,
        f"{len(skills)} skills + {len(nested)} categories, {len(broken)} broken"
        + (f": {', '.join(broken[:5])}" if broken else ""),
        time.time() - t0,
    ))
    return out


def check_scripts_compile() -> Check:
    t0 = time.time()
    root = paths.SCRIPTS_DIR
    if not root.exists():
        return Check("scripts:compile", "surface", 6.0, False, f"missing {root}")
    bad = []
    count = 0
    tmpdir = None
    try:
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="evobench_")
        for p in root.rglob("*.py"):
            if any(x in p.parts for x in (".venv", "venv", "__pycache__", "node_modules")):
                continue
            count += 1
            try:
                py_compile.compile(str(p), doraise=True,
                                   cfile=str(Path(tmpdir) / f"{count}.pyc"))
            except Exception as e:
                bad.append(f"{p.name}: {type(e).__name__}")
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return Check("scripts:compile", "surface", 6.0, not bad,
                 f"{count} scripts, {len(bad)} broken" + (f": {', '.join(bad[:4])}" if bad else ""),
                 time.time() - t0)


def check_cron() -> list[Check]:
    out: list[Check] = []
    t0 = time.time()
    p = paths.CRON_JOBS
    if not p.exists():
        return [Check("cron:jobs", "cron", 6.0, False, f"missing {p}")]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        jobs = data.get("jobs", data) if isinstance(data, dict) else data
        jobs = jobs if isinstance(jobs, list) else list(jobs.values())
    except Exception as e:
        return [Check("cron:jobs", "cron", 6.0, False, f"unparseable: {e}")]

    out.append(Check("cron:parse", "cron", 3.0, True, f"{len(jobs)} jobs", time.time() - t0))

    paid = [j.get("name") or j.get("id") for j in jobs
            if str(j.get("provider") or "") == "nous" or str(j.get("model") or "").startswith("z-ai/")]
    out.append(Check("cron:no-paid-pins", "cron", 4.0, not paid,
                     "none" if not paid else f"paid pins: {paid}", time.time() - t0))

    failing = [(j.get("name") or j.get("id"), int(j.get("failure_streak") or 0))
               for j in jobs if int(j.get("failure_streak") or 0) >= 5]
    out.append(Check("cron:failure-streaks", "cron", 4.0, not failing,
                     "healthy" if not failing else str(failing), time.time() - t0))
    return out


def check_config() -> Check:
    t0 = time.time()
    p = paths.CONFIG_YAML
    if not p.exists():
        return Check("config:present", "config", 4.0, False, f"missing {p}")
    try:
        import yaml  # optional
        yaml.safe_load(p.read_text(encoding="utf-8"))
        return Check("config:yaml", "config", 4.0, True, "parses", time.time() - t0)
    except ImportError:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        return Check("config:yaml", "config", 4.0, len(txt) > 0,
                     f"{len(txt)} bytes (pyyaml absent)", time.time() - t0)
    except Exception as e:
        return Check("config:yaml", "config", 4.0, False, str(e)[:120], time.time() - t0)


def check_memory() -> list[Check]:
    out: list[Check] = []
    t0 = time.time()
    p = paths.MEMORY_MD
    if not p.exists():
        p = paths.HERMES / "MEMORY.md"
    if not p.exists():
        return [Check("memory:present", "memory", 4.0, False, "no MEMORY.md found")]
    txt = p.read_text(encoding="utf-8", errors="ignore")
    out.append(Check("memory:present", "memory", 2.0, len(txt) > 0,
                     f"{len(txt)} chars", time.time() - t0))
    over = len(txt) > 12000
    out.append(Check("memory:budget", "memory", 2.0, not over,
                     "over budget" if over else f"{len(txt)} chars", time.time() - t0))
    return out


def check_repos() -> list[Check]:
    """Informational only: repo cleanliness is an operator concern, not a
    file-level fix, so it is reported but excluded from the gate score."""
    out: list[Check] = []
    for repo in paths.KEY_REPOS:
        t0 = time.time()
        if not repo.exists():
            out.append(Check(f"repo:{repo.name}", "repos", 1.5, False, "missing",
                             time.time() - t0, scored=False))
            continue
        try:
            r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=20)
            dirty = len([l for l in r.stdout.splitlines() if l.strip()])
            out.append(Check(f"repo:{repo.name}", "repos", 1.5, dirty == 0,
                             "clean" if dirty == 0 else f"{dirty} uncommitted",
                             time.time() - t0, scored=False))
        except Exception as e:
            out.append(Check(f"repo:{repo.name}", "repos", 1.5, False,
                             str(e)[:80], time.time() - t0, scored=False))
    return out


def _parse_ts(raw) -> "datetime | None":
    """Parse an ISO timestamp as an aware UTC datetime.

    The scout writes UTC with an offset. Parsing the naive part with
    time.mktime() reads that as LOCAL time, so on a UTC+11 host a
    report written ten minutes ago is reported as eleven hours old. A
    gate that misreports the age of its own input is worse than no
    gate: it hides a fresh report and it invents a stale one.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def check_scout() -> list[Check]:
    out: list[Check] = []
    t0 = time.time()
    out.append(Check("scout:script", "evolution", 3.0, paths.SCOUT.exists(),
                     "present" if paths.SCOUT.exists() else "missing", time.time() - t0))
    t0 = time.time()
    rp = paths.SCOUT_REPORT
    ts = None
    findings = None
    source = None
    # The scout's own copy comes first: the cron engine owns cron/output
    # and its pruning rules are not ours. The cron/output copy is read
    # second for backwards compatibility.
    for candidate, tag in ((getattr(paths, "SCOUT_STATE_REPORT", None), "state report"),
                           (rp, "report")):
        if ts is not None or candidate is None or not candidate.exists():
            continue
        try:
            d = json.loads(candidate.read_text(encoding="utf-8"))
            ts = _parse_ts(d.get("ts"))
            findings = d.get("finding_count")
            source = tag
        except Exception:
            pass
    if ts is None and paths.SCOUT_LOG.exists():
        # The report file lives in a directory another system owns, and a
        # missing file is NOT evidence that the scout did not run - the
        # append-only log carries the same timestamp. Reading it keeps
        # the gate honest about what actually happened.
        try:
            lines = [l for l in paths.SCOUT_LOG.read_text(encoding="utf-8").splitlines()
                     if l.strip()]
            if lines:
                m = re.search(r"\[([^\]]+)\]\s+findings=(\d+)", lines[-1])
                if m:
                    ts = _parse_ts(m.group(1))
                    findings = int(m.group(2))
                    source = "log"
        except Exception:
            pass
    if ts is None:
        out.append(Check("scout:fresh", "evolution", 3.0, False,
                         "no report and no log entry", time.time() - t0))
    else:
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age < -300:
            out.append(Check("scout:fresh", "evolution", 3.0, False,
                             f"report timestamp is {int(-age/60)}m in the future (from {source})",
                             time.time() - t0))
        else:
            fresh = age < 86400 * 3
            out.append(Check("scout:fresh", "evolution", 3.0, fresh,
                             f"{int(age/3600)}h old, {findings} findings (from {source})",
                             time.time() - t0))
    return out


def check_learning() -> list[Check]:
    """Is the loop actually learning? These are gate-actionable: `evo learn` fixes them."""
    out: list[Check] = []
    t0 = time.time()

    lessons = paths.HERMES / "memories" / "LESSONS.md"
    if lessons.exists():
        n = sum(1 for l in lessons.read_text(encoding="utf-8", errors="ignore").splitlines()
                if l.strip().startswith("-"))
        out.append(Check("learning:lessons_present", "learning", 3.0, n > 0,
                         f"{n} lessons distilled", time.time() - t0))
    else:
        out.append(Check("learning:lessons_present", "learning", 3.0, False,
                         "no LESSONS.md", time.time() - t0))

    t0 = time.time()
    pp = paths.PROPOSER_PROMPT
    if pp.exists():
        txt = pp.read_text(encoding="utf-8", errors="ignore")
        age_h = (time.time() - pp.stat().st_mtime) / 3600
        fresh = age_h <= 24
        has_ctx = "## LEARNED CONTEXT" in txt
        out.append(Check("learning:proposer_current", "learning", 4.0, fresh and has_ctx,
                         f"proposer {age_h:.1f}h old, learned-context={'yes' if has_ctx else 'no'}",
                         time.time() - t0))
    else:
        out.append(Check("learning:proposer_current", "learning", 4.0, False,
                         "no proposer prompt", time.time() - t0))

    t0 = time.time()
    try:
        from . import archive as _arch
        rejected = [v for v in _arch.history(40) if v.get("status") == "rejected"]
        if rejected:
            txt = pp.read_text(encoding="utf-8", errors="ignore") if pp.exists() else ""
            listed = "## DO NOT REPEAT" in txt
            out.append(Check("learning:no_repeat", "learning", 3.0, listed,
                             f"{len(rejected)} rejected variants"
                             + ("" if listed else " — not carried into the prompt"),
                             time.time() - t0))
        else:
            out.append(Check("learning:no_repeat", "learning", 3.0, True,
                             "no rejected variants to avoid", time.time() - t0))
    except Exception as e:
        out.append(Check("learning:no_repeat", "learning", 3.0, False,
                         str(e)[:80], time.time() - t0))
    return out


def check_stack_self() -> list[Check]:
    t0 = time.time()
    from . import archive
    try:
        archive.init()
        s = archive.stats()
        ok = True
        detail = f"{s['variants']} variants, best={s['best_score']}"
    except Exception as e:
        ok, detail = False, str(e)[:100]
    return [Check("stack:archive", "evolution", 4.0, ok, detail, time.time() - t0)]


def check_no_published_secrets() -> list[Check]:
    """No secret-shaped value may sit in the publishing surfaces.

    The mirror is pushed to a public repository, and so are the managed
    repos. A secret in either is a published secret. This check is
    gate-actionable on purpose: the fix is to move the secret into
    1Password and read it at run time.
    """
    t0 = time.time()
    from .secrets import scan_tree
    from . import paths
    checks: list[Check] = []
    surfaces = {
        "mirror": paths.STACK / "surface-mirror",
        "scripts": paths.SCRIPTS_DIR,
    }
    for label, root in surfaces.items():
        if not root or not Path(root).exists():
            continue
        findings = scan_tree(root, skip_dirs={"logs", "cache", "__pycache__"})
        checks.append(Check(
            f"secrets:{label}", "secrets", 6.0, not findings,
            (f"clean ({root})" if not findings else
             f"{len(findings)} secret-shaped value(s): " +
             "; ".join(sorted({f.name for f in findings})[:4])),
            time.time() - t0))
    return checks


# ------------------------------------------------------------------ runner ---
def run() -> Scorecard:
    checks: list[Check] = []
    for fn in (
        check_services, check_peers, check_nexus_api, check_ollama_api, check_skills,
        check_scripts_compile, check_cron, check_config, check_memory,
        check_repos, check_scout, check_learning, check_stack_self,
        check_no_published_secrets,
    ):
        try:
            res = fn()
        except Exception as e:
            res = [Check(name=fn.__name__, group="error", weight=3.0, passed=False,
                         detail=f"{type(e).__name__}: {e}"[:120])]
        if isinstance(res, Check):
            res = [res]
        checks.extend(res)
    total_w = sum(c.weight for c in checks if c.scored) or 1.0
    got = sum(c.weight for c in checks if c.passed and c.scored)
    gate = 100.0 * got / total_w
    all_w = sum(c.weight for c in checks) or 1.0
    all_got = sum(c.weight for c in checks if c.passed)
    return Scorecard(score=100.0 * all_got / all_w, checks=checks, gate_score=gate)


if __name__ == "__main__":
    sc = run()
    print(json.dumps(sc.to_dict(), indent=2))
