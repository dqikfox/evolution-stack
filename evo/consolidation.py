"""Consolidation audit — find the systems that overlap, and say what to do with them.

The complaint this answers: "100 systems that don't connect".
This module inventories every automation surface on THRONE, detects
duplicates/near-duplicates, and emits a KEEP / MERGE / RETIRE / ARCHIVE verdict
with reasons, so the stack stops growing and starts converging.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from . import paths


def _hash(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# --------------------------------------------------------------- inventory ---
def inventory_skills() -> list[dict]:
    out = []
    root = paths.SKILLS_DIR
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_md = d / "SKILL.md"
        nested = list(d.glob("*/SKILL.md"))
        desc = ""
        if skill_md.exists():
            m = re.search(r"description:\s*(.+)", _read(skill_md))
            desc = (m.group(1) if m else "").strip()[:160]
        out.append({
            "id": d.name,
            "kind": "skill",
            "has_manifest": bool(skill_md.exists() or nested),
            "is_category": bool(nested) and not skill_md.exists(),
            "manifest_path": str(skill_md) if skill_md.exists() else (
                str(nested[0]) if nested else ""),
            "description": desc,
            "files": sum(1 for _ in d.rglob("*") if _.is_file()),
        })
    return out


def profile_duplicates() -> list[dict]:
    """Skills that exist in more than one profile — real duplication."""
    prof_root = paths.HERMES / "profiles"
    if not prof_root.exists():
        return []
    seen: dict[str, list[str]] = defaultdict(list)
    for prof in prof_root.iterdir():
        if not prof.is_dir():
            continue
        sdir = prof / "skills"
        if not sdir.exists():
            continue
        for s in sdir.iterdir():
            if s.is_dir():
                seen[s.name].append(prof.name)
    return [
        {"skill": name, "profiles": profs}
        for name, profs in sorted(seen.items())
        if len(profs) > 1
    ]


def inventory_cron() -> list[dict]:
    p = paths.CRON_JOBS
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        jobs = data.get("jobs", data) if isinstance(data, dict) else data
        jobs = jobs if isinstance(jobs, list) else list(jobs.values())
    except Exception:
        return []
    out = []
    for j in jobs:
        out.append({
            "id": j.get("id") or j.get("name"),
            "kind": "cron",
            "name": j.get("name"),
            "enabled": j.get("enabled", True),
            "schedule": j.get("schedule") or j.get("cron") or j.get("interval"),
            "model": j.get("model"),
            "provider": j.get("provider"),
            "failure_streak": int(j.get("failure_streak") or 0),
            "last_error": (str(j.get("last_error"))[:120] if j.get("last_error") else ""),
            "no_agent": bool(j.get("no_agent")),
        })
    return out


def inventory_scripts() -> list[dict]:
    out = []
    root = paths.SCRIPTS_DIR
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.py")):
        if any(x in p.parts for x in ("__pycache__", ".venv", "node_modules")):
            continue
        txt = _read(p)
        out.append({
            "id": p.name,
            "kind": "script",
            "path": str(p),
            "lines": txt.count("\n") + 1 if txt else 0,
            "hash": _hash(p),
            "purpose": _classify(txt),
        })
    return out


def _classify(txt: str) -> str:
    t = txt.lower()
    if "watchdog" in t or "health" in t:
        return "health"
    if "evolution" in t or "evolve" in t:
        return "evolution"
    if "memory" in t or "mem0" in t:
        return "memory"
    if "throttle" in t:
        return "throttle"
    if "network" in t or "tailscale" in t or "discovery" in t:
        return "network"
    if "backup" in t or "sync" in t:
        return "backup"
    if "ollama" in t:
        return "inference"
    return "utility"


def inventory_mcp() -> list[dict]:
    out = []
    root = paths.HERMES / "mcp"
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if d.is_dir():
            out.append({"id": d.name, "kind": "mcp-server", "path": str(d)})
    return out


def inventory_prior_attempts() -> list[dict]:
    out = []
    for label, p, note in (
        ("darwinian_evolver", paths.DARWINIAN_EVOLVER,
         "population/mutation engine (imbue-ai), git-tracked"),
        ("legacy_prompt_evolution", paths.LEGACY_EVOLVE,
         "prompt evolution vs LM Studio :1234 (endpoint retired)"),
    ):
        exists = p.exists()
        entry = {
            "id": label, "kind": "prior-attempt", "path": str(p),
            "exists": exists, "note": note,
        }
        if exists:
            entry["files"] = sum(1 for x in p.rglob("*") if x.is_file())
        out.append(entry)
    return out


# ------------------------------------------------------------- duplicate ----
def find_duplicates(scripts: list[dict]) -> list[dict]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for s in scripts:
        if s.get("hash"):
            by_hash[s["hash"]].append(s["id"])
    exact = [{"hash": h, "files": f} for h, f in by_hash.items() if len(f) > 1]

    by_purpose: dict[str, list[str]] = defaultdict(list)
    for s in scripts:
        by_purpose[s["purpose"]].append(s["id"])
    clusters = [
        {"purpose": p, "files": f, "count": len(f)}
        for p, f in by_purpose.items() if len(f) > 1
    ]
    clusters.sort(key=lambda c: -c["count"])
    return [{"exact_duplicates": exact, "purpose_clusters": clusters}]


# -------------------------------------------------------------- verdicts ----
def _verdict(items: list[dict], kind: str) -> list[dict]:
    verdicts = []
    for it in items:
        v, why = "KEEP", ""
        if kind == "skill":
            if it.get("is_category"):
                v, why = "KEEP", "category container"
            elif not it["has_manifest"]:
                v, why = "REPAIR", "no SKILL.md — cannot be loaded"
            elif not it.get("description"):
                v, why = "REPAIR", "SKILL.md missing description frontmatter — not auto-discoverable"
        elif kind == "script":
            if it["purpose"] == "evolution" and it["id"] not in ("evolution_scout.py",):
                v, why = "MERGE", "overlaps the evolution stack — fold into evo/"
            if it["purpose"] == "health" and it["id"] in ("throne_evolution.py",):
                v, why = "RETIRE", "placeholder stub superseded by evo/loop.py"
        elif kind == "cron":
            if it.get("failure_streak", 0) >= 5:
                v, why = "REPAIR", f"failure streak {it['failure_streak']}"
            elif it.get("provider") == "nous" or str(it.get("model") or "").startswith("z-ai/"):
                v, why = "RETARGET", "paid model pin — move to ollama/no_agent"
        verdicts.append({"id": it["id"], "verdict": v, "reason": why})
    return verdicts


def audit() -> dict:
    skills = inventory_skills()
    crons = inventory_cron()
    scripts = inventory_scripts()
    mcps = inventory_mcp()
    priors = inventory_prior_attempts()
    dups = find_duplicates(scripts)
    prof_dups = profile_duplicates()

    verdicts = (
        _verdict(skills, "skill")
        + _verdict(crons, "cron")
        + _verdict(scripts, "script")
    )
    for d in prof_dups:
        verdicts.append({
            "id": d["skill"], "verdict": "DUPLICATE",
            "reason": f"present in profiles: {', '.join(d['profiles'])}",
        })
    counts: dict[str, int] = defaultdict(int)
    for v in verdicts:
        counts[v["verdict"]] += 1

    return {
        "ts": time.time(),
        "totals": {
            "skills": len(skills),
            "cron_jobs": len(crons),
            "scripts": len(scripts),
            "mcp_servers": len(mcps),
            "prior_attempts": len(priors),
            "profile_duplicates": len(prof_dups),
            "verdicts": dict(counts),
        },
        "skills": skills,
        "cron_jobs": crons,
        "scripts": scripts,
        "mcp_servers": mcps,
        "prior_attempts": priors,
        "duplicates": dups,
        "profile_duplicates": prof_dups,
        "verdicts": verdicts,
    }


def to_markdown(a: dict) -> str:
    t = a["totals"]
    lines = [
        "# THRONE Consolidation Audit",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Totals",
        "",
        "| Surface | Count |",
        "|---|---|",
        f"| Skills | {t['skills']} |",
        f"| Cron jobs | {t['cron_jobs']} |",
        f"| Scripts | {t['scripts']} |",
        f"| MCP servers | {t['mcp_servers']} |",
        f"| Prior evolution attempts | {t['prior_attempts']} |",
        "",
        "## Verdicts",
        "",
        "| Verdict | Count |",
        "|---|---|",
    ]
    for k, v in sorted(t["verdicts"].items()):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Duplicate / overlap clusters", ""]
    for c in a["duplicates"][0]["purpose_clusters"][:12]:
        lines.append(f"- **{c['purpose']}** ({c['count']}): " + ", ".join(c["files"][:10]))
    lines += ["", "## Non-KEEP verdicts", "",
              "| Surface | Item | Verdict | Reason |", "|---|---|---|---|"]
    kind_of = {s["id"]: "skill" for s in a["skills"]}
    kind_of.update({c["id"]: "cron" for c in a["cron_jobs"]})
    kind_of.update({s["id"]: "script" for s in a["scripts"]})
    for v in a["verdicts"]:
        if v["verdict"] != "KEEP":
            lines.append(f"| {kind_of.get(v['id'],'?')} | `{v['id']}` | {v['verdict']} | {v['reason']} |")
    lines += ["", "## Prior attempts (do not build a 4th)", ""]
    for p in a["prior_attempts"]:
        lines.append(f"- **{p['id']}** — `{p['path']}` — {p['note']} (exists={p['exists']})")
    return "\n".join(lines)


def write_report() -> tuple[str, str]:
    paths.ensure_dirs()
    a = audit()
    ts = time.strftime("%Y%m%d-%H%M%S")
    js = paths.REPORTS / f"consolidation-{ts}.json"
    md = paths.REPORTS / f"consolidation-{ts}.md"
    js.write_text(json.dumps(a, indent=2), encoding="utf-8")
    md.write_text(to_markdown(a), encoding="utf-8")
    (paths.REPORTS / "latest-consolidation.json").write_text(
        json.dumps(a, indent=2), encoding="utf-8")
    (paths.REPORTS / "latest-consolidation.md").write_text(to_markdown(a), encoding="utf-8")
    return str(js), str(md)


if __name__ == "__main__":
    j, m = write_report()
    print(j)
    print(m)
