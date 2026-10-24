#!/usr/bin/env python
"""learning_review.py - read-only digest for the Hermes continuous-learning loop.
Reads recent non-cron sessions from state.db (read-only), failing cron jobs from
jobs.json, and memory sizes. Prints a compact digest (injected into the
Hermes_Learning_Review cron agent) and saves it under cron/output/learning/.
Never kills processes, never writes to state.db, never touches secrets.
"""
import sqlite3, json, os, sys, time, datetime as dt
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\KING\AppData\Local\hermes"))
HOURS = float(os.environ.get("LEARN_HOURS", "26"))
MAX_SESS = 25
OUT = HOME / "cron" / "output" / "learning"
LOG = HOME / "logs" / "evolution-runs.jsonl"
ERR_WORDS = ("Traceback", "Error:", "error:", "failed", "denied", "not found", "timed out")

def clip(s, n):
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "..."

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    since = time.time() - HOURS * 3600
    lines = [f"# Hermes learning digest - {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} (last {HOURS:g}h)", ""]
    stats = {"sessions": 0, "user_msgs": 0, "tool_errors": 0, "cron_failing": 0}
    try:
        c = sqlite3.connect(f"file:{(HOME/'state.db').as_posix()}?mode=ro", uri=True, timeout=10)
        rows = c.execute(
            "select id, source, coalesce(title,''), message_count, tool_call_count, coalesce(end_reason,''), started_at "
            "from sessions where source != 'cron' and coalesce(last_activity_at, started_at) >= ? "
            "order by started_at desc limit ?", (since, MAX_SESS)).fetchall()
        lines.append(f"## Interactive sessions ({len(rows)})")
        for sid, src, title, mc, tc, er, st in rows:
            stats["sessions"] += 1
            users = c.execute("select content from messages where session_id=? and role='user' order by id limit 4", (sid,)).fetchall()
            errs = c.execute("select tool_name, content from messages where session_id=? and role='tool' order by id", (sid,)).fetchall()
            errs = [(n, x) for n, x in errs if x and any(w in x[:600] for w in ERR_WORDS)]
            stats["user_msgs"] += len(users); stats["tool_errors"] += len(errs)
            when = dt.datetime.fromtimestamp(st).strftime('%m-%d %H:%M') if st else "?"
            lines.append(f"- [{when}] {src} '{clip(title,80)}' msgs={mc} tools={tc} end={er or 'open'} tool_errors={len(errs)}")
            for (u,) in users:
                lines.append(f"    user: {clip(u, 220)}")
            for n, x in errs[:3]:
                lines.append(f"    ERR {n}: {clip(x, 200)}")
        c.close()
    except Exception as e:
        lines.append(f"!! state.db read failed: {e!r}")
    try:
        jobs = json.loads((HOME/"cron"/"jobs.json").read_text(encoding="utf-8")).get("jobs", [])
        bad = [j for j in jobs if j.get("last_status") == "error" or (j.get("failure_streak") or 0) > 0]
        stats["cron_failing"] = len(bad)
        lines += ["", f"## Cron jobs failing ({len(bad)}/{len(jobs)})"]
        for j in bad:
            lines.append(f"- {j.get('name')} streak={j.get('failure_streak')} err={clip(j.get('last_error') or (j.get('last_failure') or {}).get('detail'), 240)}")
    except Exception as e:
        lines.append(f"!! jobs.json read failed: {e!r}")
    lines += ["", "## Memory files"]
    for f in ("memories/MEMORY.md", "memories/USER.md", "memories/LESSONS.md", "soul.md", "SOUL_PROPOSALS.md"):
        p = HOME / f
        lines.append(f"- {f}: {p.stat().st_size if p.exists() else 'missing'} bytes")
    lp = HOME / "memories" / "LESSONS.md"
    if lp.exists():
        tail = lp.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        lines += ["", "## Recent LESSONS.md (tail)"] + tail
    text = "\n".join(lines)[:14000]
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    (OUT / f"digest_{stamp}.md").write_text(text, encoding="utf-8")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": dt.datetime.now().astimezone().isoformat(), "phase": "digest", "file": f"digest_{stamp}.md", **stats}) + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)

if __name__ == "__main__":
    main()
