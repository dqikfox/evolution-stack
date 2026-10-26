"""Snapshot / rollback of the improvable surface.

The surface is deliberately narrow:
  - %LOCALAPPDATA%/hermes/skills      (the skills the agent can rewrite)
  - %LOCALAPPDATA%/hermes/scripts     (the automation scripts)
  - %LOCALAPPDATA%/hermes/config.yaml
  - %LOCALAPPDATA%/hermes/cron/jobs.json
  - the proposer prompt

A change that regresses the benchmark is rolled back from here, automatically.
"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

from . import paths

SURFACE_FILES = [paths.CONFIG_YAML, paths.CRON_JOBS, paths.PROPOSER_PROMPT]


def _surface_members() -> list[Path]:
    members: list[Path] = [p for p in SURFACE_FILES if p.exists()]
    for root in (paths.SKILLS_DIR, paths.SCRIPTS_DIR):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and not any(x in p.parts for x in ("__pycache__", ".venv", "node_modules")):
                members.append(p)
    return members


def create(label: str = "") -> str:
    """Create a zip snapshot of the surface. Returns snapshot id."""
    paths.ensure_dirs()
    sid = f"snap-{time.strftime('%Y%m%d-%H%M%S')}"
    dest = paths.SNAPSHOTS / f"{sid}.zip"
    manifest = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in _surface_members():
            try:
                arc = p.relative_to(paths.HERMES).as_posix()
            except ValueError:
                arc = f"__external__/{p.name}"
            z.write(p, arc)
            manifest.append(arc)
        z.writestr("__manifest__", json.dumps({"label": label, "files": manifest, "ts": time.time()}))
    return sid


def list_snapshots() -> list[dict]:
    out = []
    for z in sorted(paths.SNAPSHOTS.glob("snap-*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(z) as f:
                meta = json.loads(f.read("__manifest__"))
        except Exception:
            meta = {}
        out.append({
            "id": z.stem,
            "file": str(z),
            "size_kb": round(z.stat().st_size / 1024, 1),
            "files": len(meta.get("files", [])),
            "label": meta.get("label", ""),
            "ts": meta.get("ts"),
        })
    return out


def restore(snapshot_id: str) -> dict:
    """Restore the surface from a snapshot. Destructive by design — it is a rollback.

    The restore is ADDITIVE: it copies the snapshot's files over the live
    surface but never deletes anything. That is deliberate for the files the
    snapshot holds, and it is why a file that was ADDED to the surface after
    the snapshot was taken survives a rollback — the snapshot simply does not
    mention it.

    The one file that must not survive is the rejected variant's own target.
    That is removed by the caller (evo.loop._remove_rejected_target) before
    this runs, because the restore cannot know which file it was.
    """
    z = paths.SNAPSHOTS / f"{snapshot_id}.zip"
    if not z.exists():
        raise FileNotFoundError(f"no snapshot {snapshot_id}")
    restored = 0
    with zipfile.ZipFile(z) as f:
        for name in f.namelist():
            if name == "__manifest__":
                continue
            if name.startswith("__external__/"):
                dest = Path(paths.HERMES) / "__external__" / Path(name).name
            else:
                dest = paths.HERMES / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with f.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            restored += 1
    return {"restored": restored, "snapshot": snapshot_id}


def diff_summary(snapshot_id: str) -> dict:
    """Compare current surface to a snapshot (file-level)."""
    z = paths.SNAPSHOTS / f"{snapshot_id}.zip"
    if not z.exists():
        raise FileNotFoundError(snapshot_id)
    with zipfile.ZipFile(z) as f:
        old = {n for n in f.namelist() if n != "__manifest__"}
    cur = set()
    for p in _surface_members():
        try:
            cur.add(p.relative_to(paths.HERMES).as_posix())
        except ValueError:
            cur.add(f"__external__/{p.name}")
    return {
        "changed": sorted(cur - old),
        "removed": sorted(old - cur),
        "snapshot": snapshot_id,
    }
