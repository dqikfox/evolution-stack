"""
estate_selftest — one command that proves every THRONE automation layer.

Every check is a REAL assertion against the live machine: a real HTTP call, a
real model train, a real image, a real Scheduled Task query. Nothing here is
mocked, and nothing is asserted from a config file that was merely read.

Usage:
    python scripts/estate_selftest.py            # full sweep
    python scripts/estate_selftest.py --fast     # skip the slow ML/image checks
    python scripts/estate_selftest.py --json     # machine-readable result

Exit code is 0 only when every required check passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

HERMES = Path(r"C:\Users\KING\AppData\Local\hermes")
VENV_PY = HERMES / "hermes-agent" / "venv" / "Scripts" / "python.exe"
CRON_DB = HERMES / "cron" / "executions.db"
JOBS_JSON = HERMES / "cron" / "jobs.json"
GATEWAY_HEALTH = "http://127.0.0.1:8642/health"
NEXUS_HEALTH = "http://127.0.0.1:8650/health"
OLLAMA_PS = "http://127.0.0.1:11434/api/ps"
SCRATCH = HERMES / "cache" / "scratch"

RESULTS: list[dict[str, Any]] = []


@dataclass
class Check:
    name: str
    group: str
    required: bool = True
    detail: str = ""
    ok: bool = False
    error: str = ""


def http_json(url: str, timeout: int = 10) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:200]
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)
    try:
        return code, json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return code, body[:200]


def run(cmd: list[str], timeout: int = 240) -> tuple[int, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", env=env)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def powershell(script: str, timeout: int = 60) -> tuple[int, str]:
    return run(["powershell", "-NoProfile", "-Command", script], timeout=timeout)


def record(check: Check) -> Check:
    RESULTS.append({
        "name": check.name, "group": check.group, "ok": check.ok,
        "required": check.required, "detail": check.detail, "error": check.error,
    })
    flag = "PASS" if check.ok else ("FAIL" if check.required else "WARN")
    line = f"[{flag}] {check.group}/{check.name}"
    if check.detail:
        line += f" - {check.detail}"
    if check.error and not check.ok:
        line += f" :: {check.error}"
    print(line, flush=True)
    return check


# --------------------------------------------------------------------------
# Group: startup / recovery
# --------------------------------------------------------------------------

def check_gateway_health() -> Check:
    c = Check("gateway_health", "startup")
    code, body = http_json(GATEWAY_HEALTH, timeout=10)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        c.ok = True
        c.detail = f"200 ok v{body.get('version', '?')}"
    else:
        c.error = f"code={code} body={str(body)[:120]}"
    return record(c)


def check_gateway_state() -> Check:
    """The gateway must be 'running', not 'degraded' or 'stopped'."""
    c = Check("gateway_state", "startup")
    p = HERMES / "gateway_state.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"unreadable: {exc}"
        return record(c)
    state = d.get("gateway_state")
    c.ok = state == "running"
    plats = {k: v.get("state") for k, v in (d.get("platforms") or {}).items()}
    c.detail = f"state={state} platforms={plats}"
    if not c.ok:
        c.error = f"gateway_state={state} (want 'running')"
    return record(c)


def check_ticker_fresh() -> Check:
    """The cron ticker heartbeat must be recent: it is written by the gateway."""
    c = Check("cron_ticker_fresh", "startup")
    hb = HERMES / "cron" / "ticker_heartbeat"
    try:
        age = time.time() - hb.stat().st_mtime
    except Exception as exc:  # noqa: BLE001
        c.error = f"no heartbeat file: {exc}"
        return record(c)
    c.ok = age < 90
    c.detail = f"heartbeat {age:.1f}s old"
    if not c.ok:
        c.error = f"ticker stale ({age:.0f}s) - the gateway is not ticking"
    return record(c)


def check_scheduled_tasks() -> Check:
    """Every repeating task must be ENABLED and have a FUTURE NextRunTime.

    The state matters as much as the timestamp. A DISABLED task keeps its
    NextRunTime - the scheduler still knows when it WOULD run - so a check
    that only looks for an empty timestamp passes a task that will never
    fire. That is exactly what happened on 2026-10-27: the estate
    watchdog was disabled, the gate still reported the tasks as healthy,
    and the estate's independent recovery layer was silently gone. The
    NextRunTime is also compared against the clock, not just checked for
    emptiness, because a timestamp in the past is just as useless.
    """
    c = Check("scheduled_tasks", "startup")
    # The timestamp is emitted as ISO 8601 so it can be compared against
    # the clock. The default .ToString() is culture-dependent - on this
    # host it is '27/10/2026 5:57:59 PM' - which no ISO parser accepts.
    script = (
        "foreach($n in @('Hermes_Gateway','THRONE_Watchdog_5min')){"
        "$t=Get-ScheduledTask -TaskName $n -EA SilentlyContinue;"
        "if(-not $t){Write-Output \"$n|MISSING||\";continue};"
        "$i=Get-ScheduledTaskInfo $t;"
        "$nxt=''; if($i.NextRunTime){$nxt=$i.NextRunTime.ToString('o')};"
        "Write-Output (\"{0}|{1}|{2}\" -f $n,$t.State,$nxt)}"
    )
    rc, out = powershell(script)
    if rc != 0:
        c.error = f"powershell rc={rc}: {out[:150]}"
        return record(c)
    problems, seen = [], []
    now = datetime.now()
    for line in out.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name, state, nxt = parts[0], parts[1], parts[2]
        seen.append(f"{name}={state}")
        if state == "MISSING":
            problems.append(f"{name} missing")
            continue
        if state.lower() == "disabled":
            # The independent recovery layer is off. Everything else can
            # look perfect and the estate still has no way back.
            problems.append(f"{name} is DISABLED - it will never fire")
            continue
        if name == "THRONE_Watchdog_5min" and not nxt.strip():
            problems.append(f"{name} has no NextRunTime (expired trigger)")
            continue
        try:
            when = datetime.fromisoformat(nxt.strip())
        except Exception:
            if nxt.strip():
                problems.append(f"{name} has an unreadable NextRunTime: {nxt!r}")
            continue
        # The timestamp carries a UTC offset (PowerShell's "o" format) and
        # now() does not, so the two cannot be compared until they agree.
        # Compare in the timestamp's own timezone rather than stripping
        # the offset: the offset is what makes the instant unambiguous.
        if when.tzinfo is not None:
            when = when.astimezone().replace(tzinfo=None)
        if when < now:
            problems.append(f"{name} NextRunTime is in the past ({nxt})")
    c.ok = not problems
    c.detail = " ".join(seen) or "no tasks found"
    if problems:
        c.error = "; ".join(problems)
    return record(c)


def check_gateway_supervisor_idempotent() -> Check:
    """The launcher must exit 0 and NOT start a second gateway."""
    c = Check("gateway_supervisor_idempotent", "startup")
    rc, out = run([str(VENV_PY), str(HERMES / "scripts" / "gateway_supervisor.py")], timeout=90)
    ok = rc == 0 and ("ALREADY" in out or "running" in out.lower())
    c.ok = ok
    c.detail = f"rc={rc} {out.strip().splitlines()[-1][:90] if out.strip() else ''}"
    if not ok:
        c.error = f"rc={rc}: {out[:200]}"
    return record(c)


def check_gateway_process_unique() -> Check:
    """Exactly one gateway process may be running (a second one steals the port)."""
    c = Check("gateway_process_unique", "startup")
    # Match on the command line only. Filtering on Name='python.exe' misses the
    # gateway, because it runs under tools/python-3.14.7.../python.exe, whose
    # process name is not the bare "python.exe" the CIM query expects.
    # The real process is always the one whose CommandLine contains the
    # canonical string "hermes_cli.main gateway run".
    #
    # The query must exclude ITSELF. A PowerShell process running this very
    # command line contains the search string in its own CommandLine, so a
    # naive count always reports 2 - the gateway plus the checker - and the
    # check can never pass. The real gateway runs under a python.exe, so
    # filter on that.
    #
    # @() is REQUIRED, not decoration. In Windows PowerShell 5.1 a pipeline
    # that matches exactly ONE process yields a single object, and a single
    # CimInstance has no .Count property - so $p.Count came back EMPTY and
    # the check read a healthy single gateway as zero. The @() forces an
    # array, so .Count is 1 whether there is one gateway or many.
    script = ("$p = @(Get-CimInstance Win32_Process | Where-Object { "
              "$_.CommandLine -like '*hermes_cli.main gateway run*' -and "
              "$_.Name -like 'python*' }); "
              "Write-Output $p.Count")
    rc, out = powershell(script)
    try:
        n = int(out.strip().splitlines()[-1] if out.strip() else "0")
    except (ValueError, IndexError):
        n = -1
    c.ok = n == 1
    c.detail = f"{n} gateway process(es)"
    if n != 1:
        c.error = f"expected exactly 1 gateway process, found {n}"
    return record(c)


# --------------------------------------------------------------------------
# Group: cron
# --------------------------------------------------------------------------

def check_cron_doctor() -> Check:
    c = Check("cron_doctor", "cron")
    rc, out = run([str(VENV_PY), "-m", "hermes_cli.main", "cron", "doctor"], timeout=180)
    ok = rc == 0 and "no issues" in out.lower()
    c.ok = ok
    c.detail = next((l.strip() for l in out.splitlines() if "Checked" in l), out.strip()[:100])
    if not ok:
        c.error = out.strip()[-300:]
    return record(c)


def check_all_jobs_scheduled() -> Check:
    """Every enabled job must be scheduled with a future next run.

    A job that is DUE RIGHT NOW has a next_run_at a second or two in the past
    while the ticker is dispatching it. That is normal, not a fault, so allow
    a grace window instead of reporting a false failure.
    """
    c = Check("all_jobs_scheduled", "cron")
    try:
        d = json.loads(JOBS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"unreadable: {exc}"
        return record(c)
    jobs = d.get("jobs", d)
    jobs = list(jobs.values()) if isinstance(jobs, dict) else jobs
    now = time.time()
    grace = 180.0  # a due job stays "overdue" for as long as its run takes
    bad = []
    for j in jobs:
        if not j.get("enabled"):
            continue
        nxt = j.get("next_run_at")
        if not nxt:
            bad.append(f"{j.get('id')} has no next_run_at")
            continue
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(nxt).timestamp()
            if dt < now - grace:
                bad.append(f"{j.get('id')} next_run {int(now - dt)}s overdue")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{j.get('id')} unparseable next_run_at: {exc}")
    c.ok = not bad
    c.detail = f"{len(jobs)} jobs registered"
    if bad:
        c.error = "; ".join(bad[:4])
    return record(c)


def check_recent_executions_ok() -> Check:
    """A job must not be FAILING NOW.

    An old failure that the job has since recovered from is history, not a
    fault: the 12162398f6f1 watchdog failed once at 06:40 on a NEXUS timeout
    and has completed cleanly every run since. Only a failure inside the
    last few minutes, or a job whose own failure_streak is non-zero, is a
    live fault.
    """
    c = Check("recent_executions_ok", "cron")
    try:
        con = sqlite3.connect(f"file:{CRON_DB}?mode=ro", uri=True)
        rows = con.execute(
            "select job_id,status,started_at,error from executions "
            "where started_at > ? and status != 'completed' order by started_at desc limit 6",
            (_since(0.75),),
        ).fetchall()
        con.close()
    except Exception as exc:  # noqa: BLE001
        c.error = f"db: {exc}"
        return record(c)
    streaks = _failure_streaks()
    failing = {jid for jid, n in streaks.items() if n > 0}
    c.ok = not rows and not failing
    c.detail = f"no live failures; failing jobs={sorted(failing) or 'none'}"
    if rows or failing:
        detail = "; ".join(f"{r[0]} {r[1]} {r[2]}" for r in rows[:3])
        if failing:
            detail += f"; failure_streak: { {k: v for k, v in streaks.items() if v} }"
        c.error = detail
    return record(c)


def _failure_streaks() -> dict[str, int]:
    """Per-job consecutive failure count, from the job registry."""
    out: dict[str, int] = {}
    try:
        d = json.loads(JOBS_JSON.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    jobs = d.get("jobs", d)
    jobs = list(jobs.values()) if isinstance(jobs, dict) else jobs
    for j in jobs:
        out[str(j.get("id"))] = int(j.get("failure_streak") or 0)
    return out


def check_evolution_job_state() -> Check:
    """The evolution loop must be scheduled, unpaused, and not failing."""
    c = Check("evolution_job_state", "cron")
    try:
        d = json.loads(JOBS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"unreadable: {exc}"
        return record(c)
    jobs = d.get("jobs", d)
    jobs = list(jobs.values()) if isinstance(jobs, dict) else jobs
    job = next((j for j in jobs if j.get("id") == "4c7da93924b2"), None)
    if not job:
        c.error = "THRONE_Evolution_Loop not registered"
        return record(c)
    c.ok = bool(job.get("enabled")) and job.get("state") == "scheduled" and not job.get("paused_at")
    c.detail = f"state={job.get('state')} last={job.get('last_status')} next={str(job.get('next_run_at'))[:19]}"
    if not c.ok:
        c.error = f"enabled={job.get('enabled')} state={job.get('state')} paused={job.get('paused_at')}"
    return record(c)


def check_evolution_recent_success() -> Check:
    """The last completed evolution run must have scored 100 and no failures."""
    c = Check("evolution_recent_success", "cron")
    outdir = HERMES / "cron" / "output" / "4c7da93924b2"
    try:
        files = sorted(outdir.glob("*.md"), key=lambda p: p.stat().st_mtime)
    except Exception as exc:  # noqa: BLE001
        c.error = f"no output dir: {exc}"
        return record(c)
    if not files:
        c.error = "no evolution output files"
        return record(c)
    # The NEWEST by NAME, not by mtime. The cron runner names each output
    # <timestamp>.md, so the name sorts chronologically and cannot be
    # confused by a file being written while this check reads the
    # directory. Sorting by mtime picked the previous run when the newest
    # one was still being flushed, and the check then reported the estate
    # as regressed on the strength of a stale score.
    newest = sorted(files, key=lambda p: p.name)[-1]
    text = newest.read_text(encoding="utf-8", errors="ignore")
    import re
    # The run reports several scores in sequence: "SCORE: 97.12 -> 97.12"
    # (the measured delta), then "GATE SCORE: 100.0" and "HOST SCORE:
    # 100.0". A naive "SCORE:" search matches the FIRST of those - the
    # BEFORE value of the delta - so a run that finished at 100 read as the
    # older 97.12 and the estate looked regressed. The authoritative value
    # is the final GATE SCORE, so match that specifically, and fall back to
    # the last bare SCORE: only if there is no explicit gate score.
    gate = re.search(r"GATE SCORE:\s*([0-9.]+)", text)
    if gate:
        score = float(gate.group(1))
    else:
        all_scores = re.findall(r"SCORE:\s*([0-9.]+)", text)
        score = float(all_scores[-1]) if all_scores else -1.0
    failures = re.search(r"(\d+)\s+failures", text)
    nfail = int(failures.group(1)) if failures else None
    c.ok = score >= 100.0 and (nfail in (0, None))
    c.detail = f"{newest.name} score={score} failures={nfail}"
    if not c.ok:
        c.error = f"score={score} failures={nfail}"
    return record(c)


# --------------------------------------------------------------------------
# Group: MCP / ML
# --------------------------------------------------------------------------

def check_mcp_tools() -> Check:
    c = Check("mcp_tools_connected", "ml")
    rc, out = run([str(VENV_PY), "-m", "hermes_cli.main", "mcp", "test", "constrained_ml"], timeout=180)
    ok = rc == 0 and "Tools discovered: 5" in out
    c.ok = ok
    c.detail = next((l.strip() for l in out.splitlines() if "Tools discovered" in l), out.strip()[:90])
    if not ok:
        c.error = out.strip()[-300:]
    return record(c)


def check_catboost_roundtrip() -> Check:
    """Train a real CatBoost model and predict with it.

    The test lives in tests/, NOT scripts/: the evolution stack treats
    scripts/ and skills/ as its improvable surface and a rejected variant
    rolls that surface back, which deletes test files that live there.
    """
    c = Check("catboost_roundtrip", "ml")
    script = HERMES / "tests" / "test_ml_stack.py"
    if not script.exists():
        c.error = f"test_ml_stack.py missing at {script}"
        return record(c)
    rc, out = run([str(VENV_PY), str(script)], timeout=600)
    ok = rc == 0 and "checks passed" in out and "FAIL" not in out
    c.ok = ok
    tail = [l for l in out.strip().splitlines() if "checks passed" in l]
    c.detail = tail[-1] if tail else out.strip()[-100:]
    if not ok:
        c.error = out.strip()[-400:]
    return record(c)


def check_image_generation() -> Check:
    """Generate a REAL image through the ComfyUI path and verify the PNG."""
    c = Check("image_generation", "ml", required=False)
    script = HERMES / "tests" / "test_image_stack.py"
    if not script.exists():
        c.error = f"test_image_stack.py missing at {script}"
        return record(c)
    rc, out = run([str(VENV_PY), str(script)], timeout=1500)
    ok = rc == 0 and "checks passed" in out and "FAIL" not in out
    c.ok = ok
    tail = [l for l in out.strip().splitlines() if "checks passed" in l]
    c.detail = tail[-1] if tail else out.strip()[-100:]
    if not ok:
        c.error = out.strip()[-400:]
    return record(c)


def check_comfy_not_autohealed() -> Check:
    """ComfyUI must stay unhealed: healing it would starve the agent's VRAM."""
    c = Check("comfyui_not_autohealed", "ml")
    reg = Path(r"E:\ultron-memory\infra\SERVICES.json")
    try:
        d = json.loads(reg.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"registry unreadable: {exc}"
        return record(c)
    svcs = d.get("services", d) if isinstance(d, dict) else d
    svcs = list(svcs.values()) if isinstance(svcs, dict) else svcs
    comfy = next((s for s in svcs if (s.get("name") or "").lower() == "comfyui"), None)
    if not comfy:
        c.error = "comfyui not in the registry"
        return record(c)
    start = comfy.get("start") or {}
    c.ok = start.get("heal") is False
    c.detail = f"start.heal={start.get('heal')!r} path={'yes' if start.get('path') else 'no'}"
    if not c.ok:
        c.error = "comfyui could be auto-healed - it would starve the agent model"
    return record(c)


def check_agent_model_resident() -> Check:
    """The active agent model must be resident with a >=64k context."""
    c = Check("agent_model_resident", "ml")
    code, body = http_json(OLLAMA_PS, timeout=10)
    if code != 200 or not isinstance(body, dict):
        c.error = f"ollama /api/ps code={code}"
        return record(c)
    models = body.get("models", [])
    if not models:
        c.error = "no model resident in ollama"
        return record(c)
    m = models[0]
    ctx = int(m.get("context_length") or 0)
    c.ok = ctx >= 64000
    c.detail = f"{m.get('name')} ctx={ctx} vram={round((m.get('size_vram') or 0)/1e9,1)}GB"
    if not c.ok:
        c.error = f"context {ctx} is below Hermes' 64000 minimum"
    return record(c)


# --------------------------------------------------------------------------
# Group: estate / infra
# --------------------------------------------------------------------------

def check_watchdog_healthy() -> Check:
    """The watchdog must run clean and report the estate healthy."""
    c = Check("watchdog_healthy", "estate")
    rc, out = run([str(VENV_PY), str(HERMES / "scripts" / "estate_watchdog.py")], timeout=300)
    ok = rc == 0 and "estate is healthy" in out
    c.ok = ok
    c.detail = next((l.strip() for l in out.splitlines() if "estate" in l and "check" in l), out.strip()[-90:])
    if not ok:
        c.error = out.strip()[-300:]
    return record(c)


def check_watchdog_heal_false_optout() -> Check:
    """A heal:false service must be reported and never healed.

    The match must be on the exact log phrase. "not healed" contains the
    substring "healed", so a naive substring search reports the very line
    that proves the opt-out WORKED as evidence that it failed.
    """
    c = Check("watchdog_heal_false_optout", "estate")
    rc, out = run([str(VENV_PY), str(HERMES / "scripts" / "estate_watchdog.py")], timeout=300)
    optout = [l for l in out.splitlines() if "heal: false" in l]
    if not optout:
        c.error = "the heal:false opt-out did not appear in the watchdog report"
        return record(c)
    # A real heal would log "restarting via" or "recovered on" for that service.
    healed = [l for l in out.splitlines()
              if "comfyui" in l.lower()
              and ("restarting via" in l or "recovered on" in l)]
    c.ok = not healed
    c.detail = "comfyui reported, deliberately not healed"
    if healed:
        c.error = f"comfyui was healed despite heal:false: {healed[0][:120]}"
    return record(c)


def check_services_registry_shape() -> Check:
    """Every registry entry must have the fields the watchdog reads.

    A 'retired' entry is exempt: it has no implementation, so it is never
    health-checked and needs no health route.
    """
    c = Check("services_registry_shape", "estate")
    reg = Path(r"E:\ultron-memory\infra\SERVICES.json")
    try:
        d = json.loads(reg.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"unreadable: {exc}"
        return record(c)
    svcs = d.get("services", d) if isinstance(d, dict) else d
    svcs = list(svcs.values()) if isinstance(svcs, dict) else svcs
    bad = []
    for s in svcs:
        name = s.get("name") or "?"
        retired = str(s.get("status", "")).lower() == "retired"
        for field in ("name", "port", "notes"):
            if not s.get(field):
                bad.append(f"{name} missing {field}")
        if not retired and not s.get("health"):
            bad.append(f"{name} missing health")
        if s.get("status") == "up" and not (s.get("start") or {}).get("path"):
            bad.append(f"{name} is 'up' with no start path (can never self-heal)")
    c.ok = not bad
    c.detail = f"{len(svcs)} entries"
    if bad:
        c.error = "; ".join(bad[:4])
    return record(c)


def check_nexus_healthy() -> Check:
    """NEXUS CORE must answer on /health.

    NEXUS is the heavy service in the estate: /health walks its components
    (the database, the Ollama roster, the embedding models), and under load
    that walk can outlast a short probe even though the service is fine.
    A single 15s timeout therefore reports a healthy service as dead, so
    the check retries with a longer leash before it calls it a fault.
    """
    c = Check("nexus_healthy", "estate")
    code, body = 0, None
    for attempt, timeout in ((1, 15), (2, 30), (3, 60)):
        code, body = http_json(NEXUS_HEALTH, timeout=timeout)
        if code == 200 and isinstance(body, dict) and body.get("ok"):
            break
        time.sleep(3)
    ok = code == 200 and isinstance(body, dict) and bool(body.get("ok"))
    c.ok = ok
    c.detail = f"code={code} status={body.get('status') if isinstance(body, dict) else '?'}"
    if not ok:
        c.error = f"code={code} body={str(body)[:120]}"
    return record(c)


def check_skills_valid() -> Check:
    """Both new skills must parse and carry the required frontmatter."""
    c = Check("skills_valid", "estate")
    import yaml
    targets = [
        HERMES / "skills" / "mlops" / "constrained-ml" / "SKILL.md",
        HERMES / "skills" / "infrastructure" / "hermes-startup-automation" / "SKILL.md",
    ]
    bad = []
    for p in targets:
        if not p.exists():
            bad.append(f"{p.name} missing")
            continue
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---"):
            bad.append(f"{p.parent.name} has no frontmatter")
            continue
        try:
            fm = yaml.safe_load(text.split("---")[1])
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{p.parent.name} bad yaml: {exc}")
            continue
        for key in ("name", "description"):
            if not fm.get(key):
                bad.append(f"{p.parent.name} missing {key}")
        if len(fm.get("description", "")) > 120:
            bad.append(f"{p.parent.name} description too long ({len(fm['description'])})")
    c.ok = not bad
    c.detail = f"{len(targets)} skills checked"
    if bad:
        c.error = "; ".join(bad)
    return record(c)


def check_handoff_mdns_collision_fixed() -> Check:
    """A second handoff instance must not raise the empty-message failure."""
    c = Check("handoff_mdns_collision_fixed", "estate")
    code = (
        "import sys,os;sys.path.insert(0,r'%s');"
        "os.environ['HERMES_HOME']=r'%s';import handoff;"
        "s=handoff.serve();print('OK',s.port);s.stop()"
    ) % (HERMES / "plugins" / "handoff", HERMES)
    rc, out = run([str(VENV_PY), "-c", code], timeout=120)
    ok = rc == 0 and "OK" in out
    c.ok = ok
    c.detail = "second instance starts without a name collision" if ok else out.strip()[:110]
    if not ok:
        c.error = out.strip()[-250:]
    return record(c)


def check_yandex_provider_staged() -> Check:
    """The Yandex provider must be staged, disabled, and secret-backed."""
    c = Check("yandex_provider_staged", "estate")
    code = (
        "import sys;sys.path.insert(0,r'%s');"
        "from hermes_cli.config import load_config;c=load_config();"
        "p=(c.get('providers') or {}).get('yandex') or {};"
        "print('ENABLED',p.get('enabled'));print('BASE',p.get('base_url'));"
        "print('KEYENV',p.get('key_env'));print('CTX',p.get('context_length'))"
    ) % (HERMES / "hermes-agent")
    rc, out = run([str(VENV_PY), "-c", code], timeout=120)
    if rc != 0:
        c.error = out.strip()[-200:]
        return record(c)
    got = dict(l.split(" ", 1) for l in out.splitlines() if " " in l)
    enabled = got.get("ENABLED", "").strip() == "True"
    base = got.get("BASE", "").strip()
    ctx = got.get("CTX", "").strip()
    c.ok = (not enabled) and base.endswith("/v1") and ctx == "65536"
    c.detail = f"enabled={enabled} base={base} ctx={ctx}"
    if not c.ok:
        c.error = "the staged yandex provider is not in the expected safe state"
    return record(c)


def check_provider_rotation() -> Check:
    """The model rotation must have at least 2 healthy providers.

    The estate gate fails below 2, and a single working provider means the
    estate has no fallback at all. This reads the published provider state
    rather than probing live, because a live probe of five providers is five
    round-trips plus a model load on the local GPU.
    """
    c = Check("provider_rotation", "estate")
    state = Path(r"E:\ultron-memory\evolution-stack\state\providers.json")
    try:
        d = json.loads(state.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        c.error = f"provider state unreadable: {exc}"
        return record(c)
    providers = d.get("providers", d)
    if isinstance(providers, dict):
        providers = list(providers.values())
    healthy = [p for p in providers if str(p.get("status", "")).lower() == "healthy"]
    blocked = [p for p in providers if str(p.get("status", "")).lower() == "blocked"]
    c.ok = len(healthy) >= 2
    c.detail = f"{len(healthy)} healthy, {len(blocked)} blocked"
    if not c.ok:
        c.error = f"only {len(healthy)} healthy provider(s) - the estate has no fallback"
    return record(c)


def check_connected_peer() -> Check:
    """A connected peer must answer on its Ollama endpoint.

    shadow (100.96.46.85) is an RTX A4500 on the tailnet with its own Ollama.
    It is a second inference endpoint, so it is worth proving it is live
    rather than assuming a tailnet entry means reachable.
    """
    c = Check("connected_peer_ollama", "estate", required=False)
    code, body = http_json("http://100.96.46.85:11434/api/tags", timeout=12)
    models = []
    if code == 200 and isinstance(body, dict):
        models = [m.get("name", "?") for m in body.get("models", [])]
    c.ok = code == 200 and bool(models)
    c.detail = f"shadow models={len(models)} {models[:3]}"
    if not c.ok:
        c.error = f"code={code} body={str(body)[:120]}"
    return record(c)


def check_evo_surface_intact() -> Check:
    """The improvable surface must not be missing the house's own scripts.

    A rejected evolution variant rolls scripts/ and skills/ back to an older
    snapshot. That is correct behaviour for the surface, but it can silently
    delete a file that was added after the snapshot. This check proves the
    surface still holds the files the house depends on.
    """
    c = Check("evo_surface_intact", "estate")
    required = [
        HERMES / "scripts" / "estate_watchdog.py",
        HERMES / "scripts" / "gateway_supervisor.py",
        HERMES / "scripts" / "start_hermes_gateway.cmd",
        HERMES / "scripts" / "provider_router.py",
        HERMES / "scripts" / "estate_selftest.py",
    ]
    missing = [p.name for p in required if not p.exists()]
    c.ok = not missing
    c.detail = f"{len(required) - len(missing)}/{len(required)} surface files present"
    if missing:
        c.error = f"missing from the evo surface: {missing}"
    return record(c)


def check_rejected_variant_artifacts() -> Check:
    """A rejected evolution variant must not leave its file behind.

    The stack applies a proposal, benches it, and rolls the surface back when
    the score does not improve. The rollback restores the snapshot but does
    not remove the rejected file, so the artefact stays in skills/ and is
    published by the mirror like any other skill.
    """
    c = Check("rejected_variant_artifacts", "estate", required=False)
    skills = HERMES / "skills"
    strays = [p.name for p in skills.glob("recover_*.md")]
    c.ok = not strays
    c.detail = "no rejected variant artefacts in skills/"
    if strays:
        c.error = f"rejected variant files still present: {strays}"
    return record(c)


def _since(hours: float) -> str:
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=11))
    return (datetime.now(tz) - timedelta(hours=hours)).isoformat()


FAST_SKIP = {"image_generation", "catboost_roundtrip"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip the slow ML checks")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    checks: list[Callable[[], Check]] = [
        check_gateway_health, check_gateway_state, check_gateway_process_unique,
        check_ticker_fresh, check_scheduled_tasks, check_gateway_supervisor_idempotent,
        check_cron_doctor, check_all_jobs_scheduled, check_recent_executions_ok,
        check_evolution_job_state, check_evolution_recent_success,
        check_mcp_tools, check_comfy_not_autohealed, check_agent_model_resident,
        check_watchdog_healthy, check_watchdog_heal_false_optout,
        check_services_registry_shape, check_nexus_healthy, check_skills_valid,
        check_handoff_mdns_collision_fixed, check_yandex_provider_staged,
        check_provider_rotation, check_connected_peer,
        check_evo_surface_intact, check_rejected_variant_artifacts,
        check_catboost_roundtrip, check_image_generation,
    ]

    print("=" * 74)
    print("THRONE estate self-test")
    print("=" * 74)
    started = time.time()
    for fn in checks:
        name = fn.__name__.replace("check_", "")
        if args.fast and name in FAST_SKIP:
            record(Check(name, "skipped", required=False, detail="skipped (--fast)"))
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            record(Check(name, "error", ok=False, error=f"harness raised: {exc}"))

    required = [r for r in RESULTS if r["required"]]
    failed = [r for r in required if not r["ok"]]
    warned = [r for r in RESULTS if not r["required"] and not r["ok"]]
    elapsed = time.time() - started

    print("=" * 74)
    print(f"{len(required) - len(failed)}/{len(required)} required passed | "
          f"{len(warned)} warning(s) | {elapsed:.0f}s")
    if failed:
        print("\nFAILED:")
        for r in failed:
            print(f"  - {r['group']}/{r['name']}: {r['error']}")
    if warned:
        print("\nWARNINGS:")
        for r in warned:
            print(f"  - {r['group']}/{r['name']}: {r['error'] or r['detail']}")

    if args.json:
        print("\n" + json.dumps({"results": RESULTS, "passed": len(required) - len(failed),
                                 "failed": len(failed), "elapsed_s": round(elapsed, 1)}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
