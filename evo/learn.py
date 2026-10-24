"""The learning bridge: what Hermes learned becomes what the stack proposes.

Without this, the evolution loop is blind: it knows what broke (bench) but not
what the operator corrected us about (lessons), and it happily re-proposes
things that were already rejected.

Flow:
    sessions -> lessons (LESSONS.md) + cron failures + archive history
             -> lessons brief -> proposer prompt (state/proposer_prompt.txt)
             -> proposer (evo/mutate.py) -> candidate -> GATE -> kept or rolled back

The brief is regenerated from evidence, never hand-written, and the proposer
prompt is stored in the archive so the improver itself is versioned.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import archive, paths

LESSONS_MD = paths.HERMES / "memories" / "LESSONS.md"
RUNS_LOG = paths.HERMES / "logs" / "evolution-runs.jsonl"
PROPOSER_STATE = paths.PROPOSER_PROMPT

LESSON_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*\[([a-zA-Z0-9_-]+)\]\s*(.+?)(?:\s*--\s*evidence:\s*(.*))?$")


def harvest(max_lessons: int = 12) -> dict:
    """Collect learning evidence from the live host. Read-only."""
    lessons: list[dict] = []
    if LESSONS_MD.exists():
        for line in LESSONS_MD.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = LESSON_RE.match(line.strip())
            if m:
                lessons.append({
                    "date": m.group(1), "tag": m.group(2),
                    "lesson": m.group(3).strip()[:300],
                    "evidence": (m.group(4) or "").strip()[:200],
                })
    lessons.sort(key=lambda x: x["date"], reverse=True)

    runs: list[dict] = []
    if RUNS_LOG.exists():
        for line in RUNS_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-40:]:
            try:
                runs.append(json.loads(line))
            except Exception:
                continue

    cron_failures: list[dict] = []
    if paths.CRON_JOBS.exists():
        try:
            data = json.loads(paths.CRON_JOBS.read_text(encoding="utf-8"))
            jobs = data.get("jobs", data) if isinstance(data, dict) else data
            jobs = jobs if isinstance(jobs, list) else list(jobs.values())
            for j in jobs:
                streak = int(j.get("failure_streak") or 0)
                if streak > 0:
                    cron_failures.append({
                        "job": j.get("name"),
                        "streak": streak,
                        "error": str(j.get("last_error") or "")[:200],
                    })
        except Exception:
            pass

    rejected = [v for v in archive.history(60) if v.get("status") == "rejected"]
    accepted = [v for v in archive.history(60) if v.get("status") == "accepted"]

    return {
        "ts": time.time(),
        "lessons": lessons[:max_lessons],
        "lesson_count": len(lessons),
        "runs": runs[-10:],
        "cron_failures": cron_failures,
        "rejected": [{"target": v["target"], "summary": v["summary"][:120],
                      "score": v.get("score_after")} for v in rejected[:8]],
        "accepted": [{"target": v["target"], "summary": v["summary"][:120],
                      "score": v.get("score_after")} for v in accepted[:8]],
    }


def build_prompt(brief: dict) -> str:
    """Compose the proposer prompt from the seed + harvested evidence."""
    parts = [paths.SEED_PROPOSER_PROMPT.rstrip(), "", "## LEARNED CONTEXT (from live sessions, cron failures and past cycles)"]

    if brief["lessons"]:
        for ls in brief["lessons"]:
            ev = f" [evidence: {ls['evidence']}]" if ls["evidence"] else ""
            parts.append(f"- ({ls['date']}, {ls['tag']}) {ls['lesson']}{ev}")
    else:
        parts.append("- (no lessons recorded yet — propose a change that is safe and reversible)")

    if brief["cron_failures"]:
        parts += ["", "## RECENT CRON FAILURES (fix these first if you can)"]
        for f in brief["cron_failures"]:
            parts.append(f"- {f['job']} (streak {f['streak']}): {f['error']}")

    if brief["rejected"]:
        parts += ["", "## DO NOT REPEAT (already proposed and rejected)"]
        for r in brief["rejected"]:
            parts.append(f"- {r['target']}: {r['summary']}")

    if brief["accepted"]:
        parts += ["", "## WHAT WORKED (same shape, keep doing this)"]
        for a in brief["accepted"]:
            parts.append(f"- {a['target']}: {a['summary']}")

    parts += [
        "",
        "## OUTPUT CONTRACT",
        "Reply with ONE JSON object and nothing else:",
        '{"target": "<skills/... or scripts/... .py|.md>", "content": "<complete file content>", "rationale": "<one sentence>"}',
        "",
    ]
    return "\n".join(parts)


def refresh(record: bool = True) -> dict:
    """Regenerate the proposer prompt from current evidence and version it."""
    paths.ensure_dirs()
    brief = harvest()
    prompt = build_prompt(brief)
    PROPOSER_STATE.parent.mkdir(parents=True, exist_ok=True)
    PROPOSER_STATE.write_text(prompt, encoding="utf-8")

    summary = (f"proposer refreshed: {brief['lesson_count']} lessons, "
               f"{len(brief['cron_failures'])} cron failures, "
               f"{len(brief['rejected'])} rejected, {len(brief['accepted'])} accepted")
    vid = None
    if record:
        sc = None
        try:
            from . import bench
            sc = bench.run()
        except Exception:
            sc = None
        vid = archive.add_variant(
            target="proposer_prompt",
            summary=summary,
            diff=prompt,
            kind="proposer",
            score_after=sc.gate_score if sc else None,
            status="accepted",
            lessons=brief["lesson_count"],
            cron_failures=len(brief["cron_failures"]),
            rejected_count=len(brief["rejected"]),
        )
    archive.log_event("learn", summary, variant_id=vid)
    return {"variant_id": vid, "summary": summary, "path": str(PROPOSER_STATE),
            "lessons": brief["lesson_count"], "cron_failures": len(brief["cron_failures"])}


def status() -> dict:
    brief = harvest()
    age_h = None
    if PROPOSER_STATE.exists():
        age_h = round((time.time() - PROPOSER_STATE.stat().st_mtime) / 3600, 2)
    return {
        "lessons": brief["lesson_count"],
        "recent_lessons": brief["lessons"][:5],
        "cron_failures": brief["cron_failures"],
        "rejected_count": len(brief["rejected"]),
        "accepted_count": len(brief["accepted"]),
        "proposer_age_hours": age_h,
        "proposer_path": str(PROPOSER_STATE),
    }


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2, default=str))
