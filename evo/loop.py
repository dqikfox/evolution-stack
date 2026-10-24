"""Single entry point for the THRONE Evolution Stack.

    python -m evo bench        # objective scorecard of the whole stack
    python -m evo audit        # consolidation audit (KEEP/MERGE/RETIRE/ARCHIVE)
    python -m evo status       # one-screen summary
    python -m evo propose      # ask the local model for one benchmark-improving change
    python -m evo apply <id>   # snapshot -> apply -> bench -> keep OR auto-rollback
    python -m evo rollback <snap>
    python -m evo history
    python -m evo cycle        # cron-safe: bench + scout + status file
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import archive, bench, consolidation, mutate, paths, snapshot


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ------------------------------------------------------------------ bench ---
def cmd_bench(args) -> int:
    sc = bench.run()
    d = sc.to_dict()
    archive.record_benchmark(sc.gate_score, len(sc.checks), len(sc.gate_failures), d)
    archive.log_event("bench", f"gate_score={sc.gate_score:.2f} host_score={sc.score:.2f}",
                      gate_failed=len(sc.gate_failures))
    if args.json:
        _print(d)
    else:
        print(f"GATE SCORE {sc.gate_score:.2f}/100   HOST SCORE {sc.score:.2f}/100")
        print(f"  ({len(sc.passed)}/{len(sc.checks)} checks passed, "
              f"{len(sc.gate_failures)} gate-actionable)")
        for c in sc.checks:
            mark = "PASS" if c.passed else "FAIL"
            scope = "gate" if c.scored else "info"
            print(f"  [{mark}] {c.name:<28} w={c.weight:<4} ({scope}) {c.detail[:70]}")
    return 0 if not sc.gate_failures else 1


def cmd_mirror(args) -> int:
    """Mirror the improvable surface into this repo (git-tracked history)."""
    from . import mirror
    if args.diff:
        _print({"drift": mirror.diff_targets()})
        return 0
    if args.all:
        files = mirror.record_all()
        _print({"mirrored": len(files)})
        return 0
    _print({"drift": mirror.diff_targets()})
    return 0


# ------------------------------------------------------------------ learn ---
def cmd_learn(args) -> int:
    """Refresh the proposer prompt from live learning evidence."""
    from . import learn
    if args.status:
        _print(learn.status())
        return 0
    res = learn.refresh()
    _print(res)
    return 0


# ------------------------------------------------------------------ audit ---
def cmd_audit(args) -> int:
    js, md = consolidation.write_report()
    a = consolidation.audit()
    if args.json:
        _print(a["totals"])
    else:
        print(f"skills={a['totals']['skills']} cron={a['totals']['cron_jobs']} "
              f"scripts={a['totals']['scripts']} mcp={a['totals']['mcp_servers']}")
        print(f"verdicts: {a['totals']['verdicts']}")
        print(f"report: {md}")
    archive.log_event("audit", "consolidation audit written", report=md)
    return 0


# ----------------------------------------------------------------- status ---
def cmd_status(args) -> int:
    s = archive.stats()
    lb = archive.latest_benchmark()
    best = archive.best_variant()
    snaps = snapshot.list_snapshots()
    out = {
        "stack": str(paths.STACK),
        "archive": s,
        "latest_benchmark": {
            "score": lb["score"] if lb else None,
            "ts": lb["ts"] if lb else None,
            "failed": lb["failures"] if lb else None,
        },
        "benchmark_trend": archive.benchmark_history(10),
        "best_variant": {k: best[k] for k in ("id", "target", "summary", "score_after")} if best else None,
        "snapshots": len(snaps),
        "last_snapshot": snaps[0]["id"] if snaps else None,
    }
    _print(out)
    return 0


# ---------------------------------------------------------------- propose ---
def cmd_propose(args) -> int:
    lb = archive.latest_benchmark()
    failures = []
    if lb and isinstance(lb.get("detail"), dict):
        failures = [c for c in lb["detail"].get("checks", [])
                    if not c.get("passed") and c.get("scored", True)]
    if not failures:
        sc = bench.run()
        archive.record_benchmark(sc.gate_score, len(sc.checks), len(sc.gate_failures), sc.to_dict())
        failures = [{"name": c.name, "detail": c.detail} for c in sc.gate_failures]

    prop = mutate.propose(failures, model=args.model)
    if not prop.get("ok"):
        print(f"PROPOSAL FAILED: {prop.get('error')}")
        archive.log_event("propose", "failed", error=prop.get("error"))
        return 1

    parent = archive.best_variant()
    vid = archive.add_variant(
        target=prop["target"],
        summary=prop.get("rationale", "")[:200] or f"proposal for {prop['target']}",
        diff=prop["content"],
        parent_id=parent["id"] if parent else None,
        kind="file",
        score_before=lb["score"] if lb else None,
        meta={"proposer": "ollama", "model": args.model or paths.DEFAULT_MODEL},
    )
    print(f"PROPOSED variant #{vid} -> {prop['target']}")
    print(f"  rationale: {prop.get('rationale','')}")
    if args.apply:
        return cmd_apply(argparse.Namespace(variant_id=vid))
    return 0


# ------------------------------------------------------------------ apply ---
def cmd_apply(args) -> int:
    v = archive.get_variant(args.variant_id)
    if not v:
        print(f"no variant #{args.variant_id}")
        return 1
    if v["status"] not in ("proposed", "proposed_by_agent"):
        print(f"variant #{v['id']} is {v['status']}, not applicable")
        return 1

    before = bench.run()
    archive.record_benchmark(before.gate_score, len(before.checks), len(before.gate_failures), before.to_dict())
    print(f"baseline gate score {before.gate_score:.2f}")

    snap = snapshot.create(label=f"pre-apply #{v['id']}")
    print(f"snapshot {snap} created")

    try:
        dest = mutate.apply_content(v["target"], v["diff"] or "")
    except Exception as e:
        archive.set_status(v["id"], "rejected")
        print(f"apply failed: {e}")
        return 1
    print(f"applied -> {dest}")

    after = bench.run()
    archive.record_benchmark(after.gate_score, len(after.checks), len(after.gate_failures), after.to_dict())
    print(f"post-apply gate score {after.gate_score:.2f}")

    if after.gate_score > before.gate_score:
        archive.set_status(v["id"], "accepted", after.gate_score)
        archive.log_event("apply", f"accepted #{v['id']}",
                          before=before.gate_score, after=after.gate_score)
        mirrored = ""
        try:
            from . import mirror
            mirrored = mirror.record(v["target"]) or ""
        except Exception as e:
            mirrored = f"mirror failed: {e}"
        print(f"ACCEPTED (+{after.gate_score - before.gate_score:.2f}) — kept, snapshot {snap} retained")
        if mirrored and not mirrored.startswith("mirror failed"):
            print(f"mirrored -> {mirrored}")
        return 0

    archive.set_status(v["id"], "rejected", after.gate_score)
    print(f"REJECTED ({after.gate_score - before.gate_score:+.2f}) — rolling back {snap}")
    try:
        r = snapshot.restore(snap)
        confirm = bench.run()
        archive.record_benchmark(confirm.gate_score, len(confirm.checks), len(confirm.gate_failures), confirm.to_dict())
        print(f"rolled back {r['restored']} files; gate score now {confirm.gate_score:.2f}")
    except Exception as e:
        print(f"ROLLBACK FAILED: {e} — manual restore required from {snap}")
        return 2
    return 1


# --------------------------------------------------------------- rollback ---
def cmd_rollback(args) -> int:
    r = snapshot.restore(args.snapshot)
    sc = bench.run()
    archive.record_benchmark(sc.score, len(sc.checks), len(sc.failures), sc.to_dict())
    _print({**r, "score": sc.score})
    return 0


# ---------------------------------------------------------------- history ---
def cmd_history(args) -> int:
    _print({
        "variants": archive.history(args.limit),
        "benchmarks": archive.benchmark_history(args.limit),
    })
    return 0


# ------------------------------------------------------------------ cycle ---
def cmd_cycle(args) -> int:
    """Cron-safe: refresh scout, benchmark, publish status. No agent required."""
    paths.ensure_dirs()
    archive.init()

    scout_out = ""
    if paths.SCOUT.exists():
        try:
            r = subprocess.run([sys.executable, str(paths.SCOUT)],
                               capture_output=True, text=True, timeout=180)
            scout_out = (r.stdout or "")[-2000:]
        except Exception as e:
            scout_out = f"scout error: {e}"

    # LEARN FIRST: the proposer prompt is rebuilt from lessons + cron failures
    # + archive history, so every cycle starts from current evidence.
    learn_info = {}
    try:
        from . import learn
        learn_info = learn.refresh()
    except Exception as e:
        learn_info = {"error": str(e)[:160]}

    sc = bench.run()
    archive.record_benchmark(sc.gate_score, len(sc.checks), len(sc.gate_failures), sc.to_dict())

    findings = []
    if paths.SCOUT_REPORT.exists():
        try:
            findings = json.loads(paths.SCOUT_REPORT.read_text(encoding="utf-8")).get("findings", [])
        except Exception:
            findings = []

    status = {
        "ts": time.time(),
        "gate_score": sc.gate_score,
        "host_score": sc.score,
        "checks": len(sc.checks),
        "failed": len(sc.failures),
        "gate_failed": len(sc.gate_failures),
        "failures": [{"name": c.name, "detail": c.detail} for c in sc.failures],
        "scout_findings": len(findings),
        "learning": learn_info,
        "archive": archive.stats(),
        "stack": str(paths.STACK),
    }
    out = paths.HERMES / "cron" / "output" / "evolution_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"gate {sc.gate_score:.2f}  host {sc.score:.2f}  gate-failures {len(sc.gate_failures)}  "
          f"scout findings {len(findings)}")
    print(f"status -> {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evo", description="THRONE Evolution Stack")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bench"); b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_bench)

    ln = sub.add_parser("learn"); ln.add_argument("--status", action="store_true")
    ln.set_defaults(func=cmd_learn)

    mi = sub.add_parser("mirror"); mi.add_argument("--all", action="store_true")
    mi.add_argument("--diff", action="store_true")
    mi.set_defaults(func=cmd_mirror)

    a = sub.add_parser("audit"); a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_audit)

    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("propose"); p.add_argument("--model", default=None)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_propose)

    ap2 = sub.add_parser("apply"); ap2.add_argument("variant_id", type=int)
    ap2.set_defaults(func=cmd_apply)

    r = sub.add_parser("rollback"); r.add_argument("snapshot")
    r.set_defaults(func=cmd_rollback)

    h = sub.add_parser("history"); h.add_argument("--limit", type=int, default=30)
    h.set_defaults(func=cmd_history)

    sub.add_parser("cycle").set_defaults(func=cmd_cycle)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
