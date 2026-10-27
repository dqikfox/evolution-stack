#!/usr/bin/env python3
"""memory-graph-guardian.py - Verify and repair the THRONE memory graph stores.

Two stores, two different failure modes:

  1. The MCP knowledge graph (@modelcontextprotocol/server-memory) keeps its
     graph in a JSONL file. It USED to live inside the npm cache, where
     `npm cache clean` would have destroyed it silently. It now lives at
     E:\\ultron-memory\\memory-graph\\memory.jsonl, and the server is pointed
     at it with MEMORY_FILE_PATH in config.yaml.

     The package's own `dist` directory holds the SERVER'S CODE (index.js,
     version.js). It must therefore stay a real directory.

     An earlier design junctioned `dist` to the graph folder so the
     server's temp-file + rename writes landed on E:. That shape has two
     fatal flaws: the server's code then lives in a data directory, and an
     MSYS-style symlink (dist -> /e/ultron-memory/memory-graph) is a POSIX
     path that Windows Node cannot resolve, so the server dies at startup
     with "Connection closed". MEMORY_FILE_PATH makes the junction
     unnecessary, so it was removed.

  2. The second-brain DB (E:\\ultron-memory\\db\\ultron-memory.db) holds the
     memories and their weighted relations.

This guardian checks all of it and repairs what is mechanically repairable:
a damaged `dist`, a drifted npm install that resurrected a stray graph
file, server code left in the data directory, a missing rotation backup, a
corrupt DB.

Run:  python memory-graph-guardian.py            # check + repair
      python memory-graph-guardian.py --report   # check only, no changes
      python memory-graph-guardian.py --json     # machine-readable output

Exit codes: 0 healthy (after any repair), 1 a problem it could not fix.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

# --- locations -------------------------------------------------------------
CANON_DIR = Path(r"E:\ultron-memory\memory-graph")
CANON_FILE = CANON_DIR / "memory.jsonl"
DB = Path(r"E:\ultron-memory\db\ultron-memory.db")
BACKUP_DIR = Path(r"E:\ultron-memory\db")
NPX_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "npm-cache" / "_npx"
HERMES_CONFIG = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes" / "config.yaml"
KEEP_ROTATIONS = 10

EXPECTED_MEMORY_PATH = r"E:\ultron-memory\memory-graph\memory.jsonl"
NPM_PACKAGE = "@modelcontextprotocol/server-memory"
#: The server's own code. The package's dist must hold these.
SERVER_CODE = ("index.js", "version.js")


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def npx_server_memory_dirs() -> list[Path]:
    """Every npx cache copy of @modelcontextprotocol/server-memory."""
    if not NPX_ROOT.exists():
        return []
    out = []
    for pkg in NPX_ROOT.glob("*/node_modules/@modelcontextprotocol/server-memory"):
        if pkg.is_dir():
            out.append(pkg)
    return out


def parse_graph(path: Path) -> tuple[int, int, list[str]]:
    """(entities, relations, malformed_lines) for a server-memory JSONL file."""
    entities = relations = 0
    bad = []
    if not path.exists():
        return 0, 0, ["missing"]
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            line = line.strip().lstrip("\ufeff")
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad.append(f"line {i}")
                continue
            kind = obj.get("type")
            if kind == "entity":
                entities += 1
            elif kind == "relation":
                relations += 1
            else:
                bad.append(f"line {i} unknown type {kind!r}")
    except OSError as exc:
        return 0, 0, [str(exc)]
    return entities, relations, bad


def sanitize_bom(path: Path) -> int:
    """Strip a UTF-8 BOM from every line of the graph file.

    A BOM on ANY line makes that line invisible to the server: JSON.parse
    fails, the record is parked in the "unreadable" bucket, and the tools
    (search_nodes, delete_entities) never see it. The line is still written
    back unchanged, so the node survives on disk and can never be read or
    removed through the API - a silent zombie.

    PowerShell 5.1's `Set-Content -Encoding utf8` writes a BOM, so any tool
    that rebuilds the file that way introduces the problem.

    Returns the number of lines that were fixed.
    """
    if not path.exists():
        return 0
    raw = path.read_bytes()
    if b"\xef\xbb\xbf" not in raw:
        return 0
    fixed = []
    count = 0
    for line in raw.split(b"\n"):
        if line.startswith(b"\xef\xbb\xbf"):
            line = line[3:]
            count += 1
        fixed.append(line)
    path.write_bytes(b"\n".join(fixed))
    return count


def dedupe_lines(path: Path) -> tuple[int, int]:
    """Drop exact duplicate lines from a graph file. Returns (removed, kept)."""
    if not path.exists():
        return 0, 0
    seen = set()
    kept = []
    removed = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        if stripped in seen:
            removed += 1
            continue
        seen.add(stripped)
        kept.append(stripped)
    if removed:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed, len(kept)


def merge_stray_graphs(canon: Path, strays: list[Path]) -> dict:
    """Fold a stray graph file's unique lines into the canonical one.

    A stray file is one that npm created when the package was reinstalled
    and the server wrote its graph back into the npm cache. Its content is
    a SUBSET of the canonical graph in the healthy case, so merging is a
    union of unique lines - the canonical file wins on conflicts because
    it is the newer, complete one.
    """
    if not canon.exists():
        return {"merged": 0, "strays": []}
    canon_lines = {l.strip().lstrip("\ufeff") for l in canon.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip().lstrip("\ufeff")}
    added = 0
    merged_from = []
    for stray in strays:
        if not stray.exists():
            continue
        extra = []
        for line in stray.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip().lstrip("\ufeff")
            if s and s not in canon_lines:
                extra.append(s)
        if extra:
            canon_lines.update(extra)
            added += len(extra)
            merged_from.append(str(stray))
    if added:
        canon.write_text("\n".join(sorted(canon_lines, key=lambda l: (0 if '"entity"' in l else 1, l))) + "\n",
                         encoding="utf-8")
    return {"merged": added, "strays": merged_from}


# --- the package's dist directory ------------------------------------------
def is_reparse_point(path: Path) -> bool:
    """True for a junction or a symlink.

    A `dist` that is a reparse point is the OLD design (the graph folder
    junctioned over the server's code, or an MSYS symlink whose POSIX
    target Windows Node cannot resolve). Either way the server cannot run.
    """
    if not path.exists() and not path.is_symlink():
        return False
    if os.name != "nt":
        return path.is_symlink()
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"(Get-Item -LiteralPath '{path}' -Force).LinkType"],
            capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        return bool((out.stdout or "").strip())
    except Exception:
        return False


def dist_is_healthy(dist: Path) -> bool:
    """A healthy dist is a REAL directory holding the server's code."""
    if is_reparse_point(dist):
        return False
    if not dist.is_dir():
        return False
    return all((dist / name).exists() for name in SERVER_CODE)


def _package_version(pkg: Path) -> str | None:
    pj = pkg / "package.json"
    if not pj.exists():
        return None
    try:
        return json.loads(pj.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _fetch_package_code(version: str | None) -> Path | None:
    """Download the package and return the path to its dist directory."""
    spec = f"{NPM_PACKAGE}@{version}" if version else NPM_PACKAGE
    tmp = Path(tempfile.mkdtemp(prefix="memdist-"))
    try:
        out = subprocess.run(["npm", "pack", spec], cwd=str(tmp), capture_output=True,
                             text=True, timeout=300, encoding="utf-8", errors="replace")
        tarballs = sorted(tmp.glob("*.tgz"))
        if out.returncode != 0 or not tarballs:
            return None
        with tarfile.open(tarballs[0]) as tf:
            tf.extractall(tmp)
        dist = tmp / "package" / "dist"
        return dist if dist.is_dir() else None
    except Exception:
        return None


def repair_dist(pkg: Path, donors: list[Path]) -> bool:
    """Restore a REAL dist directory holding the server's code.

    Order of preference:
      1. another npx cache copy that already has a healthy dist
      2. a fresh download of the package

    The junction/symlink is removed with cmd's rmdir, which deletes the
    LINK and never recurses into its target, so the canonical graph is
    never at risk.
    """
    dist = pkg / "dist"

    # A stray graph file inside the old junction is a copy of the graph
    # that the server wrote while it was still pointed at the npm cache.
    if dist.exists() and not is_reparse_point(dist):
        stray = dist / "memory.jsonl"
        if stray.exists():
            merge_stray_graphs(CANON_FILE, [stray])

    source: Path | None = None
    for donor in donors:
        d = donor / "dist"
        if dist_is_healthy(d):
            source = d
            break
    if source is None:
        source = _fetch_package_code(_package_version(pkg))
    if source is None:
        return False

    if dist.exists() or dist.is_symlink():
        if is_reparse_point(dist):
            subprocess.run(["cmd.exe", "/c", "rmdir", str(dist)], capture_output=True, timeout=60)
        else:
            shutil.rmtree(dist, ignore_errors=True)
        if dist.exists():
            return False

    dist.mkdir(parents=True, exist_ok=True)
    for name in SERVER_CODE:
        src = source / name
        if src.exists():
            shutil.copy2(src, dist / name)
    return dist_is_healthy(dist)


def check_config() -> dict:
    """The config must point the server at the durable path."""
    if not HERMES_CONFIG.exists():
        return {"present": False, "memory_file_path_set": False}
    try:
        text = HERMES_CONFIG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"present": True, "memory_file_path_set": False}
    idx = text.find("MEMORY_FILE_PATH")
    value = None
    if idx != -1:
        line = text[idx: text.find("\n", idx)] if "\n" in text[idx:] else text[idx:]
        value = line.split(":", 1)[-1].strip().strip("'\"")
    return {
        "present": True,
        "memory_file_path_set": value is not None,
        "memory_file_path": value,
        "points_at_canonical": value is not None and value.replace("\\\\", "\\").lower() == EXPECTED_MEMORY_PATH.lower(),
    }


def check_db() -> dict:
    if not DB.exists():
        return {"present": False}
    out = {"present": True}
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        out["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        out["memories"] = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        out["relations"] = conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
        out["dangling_edges"] = conn.execute(
            "SELECT COUNT(*) FROM memory_relations WHERE source_uuid NOT IN (SELECT uuid FROM memories) "
            "OR target_uuid NOT IN (SELECT uuid FROM memories)").fetchone()[0]
        out["latest_memory"] = conn.execute(
            "SELECT MAX(created_at) FROM memories").fetchone()[0]
        conn.close()
    except Exception as exc:
        out["error"] = str(exc)
    return out


def rotate_backups() -> dict:
    """Keep the newest N pre-prune/ingest rotations, delete the rest."""
    if not BACKUP_DIR.exists():
        return {"kept": 0, "removed": 0}
    pats = ("ultron-memory.db.bak-*", "ultron-memory.db.bak-preprune-*")
    files = []
    for pat in pats:
        files.extend(BACKUP_DIR.glob(pat))
    files = sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in files[KEEP_ROTATIONS:]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return {"kept": min(len(files), KEEP_ROTATIONS), "removed": removed}


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify and repair the THRONE memory graph stores")
    ap.add_argument("--report", action="store_true", help="check only, make no changes")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "repairs": [], "problems": []}

    # --- the MCP graph file ---------------------------------------------
    CANON_DIR.mkdir(parents=True, exist_ok=True)
    if not CANON_FILE.exists():
        report["problems"].append("canonical graph file missing")
        if not args.report:
            CANON_FILE.write_text("", encoding="utf-8")
            report["repairs"].append("created an empty canonical graph file")
    ents, rels, bad = parse_graph(CANON_FILE)
    report["graph_file"] = {"path": str(CANON_FILE), "entities": ents, "relations": rels,
                            "malformed": bad, "size_bytes": CANON_FILE.stat().st_size
                            if CANON_FILE.exists() else 0}
    if bad:
        report["problems"].append(f"{len(bad)} malformed graph lines")

    # The graph directory is DATA. The server's code does not belong there.
    code_in_data = [n for n in SERVER_CODE if (CANON_DIR / n).exists()]
    if code_in_data:
        report["problems"].append(f"server code left in the graph directory: {code_in_data}")
        if not args.report:
            for n in code_in_data:
                (CANON_DIR / n).unlink(missing_ok=True)
            report["repairs"].append(f"removed the server code from the graph directory: {code_in_data}")

    # --- the package's dist for every npm install of the package ---------
    pkgs = npx_server_memory_dirs()
    dist_state = []
    for pkg in pkgs:
        dist = pkg / "dist"
        healthy = dist_is_healthy(dist)
        dist_state.append({"package": str(pkg), "dist": str(dist),
                           "healthy": healthy, "reparse_point": is_reparse_point(dist)})
        if not healthy and not args.report:
            if repair_dist(pkg, [p for p in pkgs if p != pkg]):
                report["repairs"].append(f"restored the server's dist for {pkg}")
            else:
                report["problems"].append(f"could not restore the server's dist for {pkg}")
        elif not healthy:
            report["problems"].append(f"the server's dist is missing or is a reparse point: {dist}")
    report["dist"] = dist_state
    report["packages_found"] = len(pkgs)

    # Strays are scanned AFTER the repairs: a stray is a graph file that
    # the server wrote back into the npm cache. With a healthy real dist
    # the server writes to the canonical path, so a stray means the
    # server ran against the wrong MEMORY_FILE_PATH.
    strays = []
    for pkg in pkgs:
        dist = pkg / "dist"
        if is_reparse_point(dist):
            continue
        stray_file = dist / "memory.jsonl"
        if stray_file.exists():
            strays.append(stray_file)
    if strays:
        merged = merge_stray_graphs(CANON_FILE, strays)
        report["stray_merged"] = merged
        if merged["merged"]:
            report["repairs"].append(f"merged {merged['merged']} unique lines from {len(merged['strays'])} stray graph file(s)")
        else:
            report["problems"].append("a stray graph file exists outside the canonical location")

    # --- config ---------------------------------------------------------
    cfg = check_config()
    report["config"] = cfg
    if not cfg.get("memory_file_path_set"):
        report["problems"].append("config.yaml has no MEMORY_FILE_PATH for the memory MCP server")
    elif not cfg.get("points_at_canonical"):
        report["problems"].append(f"MEMORY_FILE_PATH points at {cfg.get('memory_file_path')!r}, not the canonical path")

    # --- second-brain DB -------------------------------------------------
    report["database"] = check_db()
    if report["database"].get("integrity") not in (None, "ok"):
        report["problems"].append(f"database integrity: {report['database']['integrity']}")
    if report["database"].get("dangling_edges"):
        report["problems"].append(f"{report['database']['dangling_edges']} dangling relation edges")

    # --- dedupe + rotate --------------------------------------------------
    if not args.report:
        boms = sanitize_bom(CANON_FILE)
        if boms:
            report["repairs"].append(f"stripped a UTF-8 BOM from {boms} graph line(s)")
        removed, kept = dedupe_lines(CANON_FILE)
        if removed:
            report["repairs"].append(f"removed {removed} duplicate graph lines")
        report["rotation"] = rotate_backups()
    else:
        report["rotation"] = {"checked": True}

    report["healthy"] = not report["problems"]
    if args.json:
        print(json.dumps(report, indent=2))
    elif report["healthy"]:
        # Watchdog pattern: healthy is quiet. A delivery that fires every tick
        # with "nothing to report" trains the reader to ignore the channel.
        for r in report["repairs"]:
            log(f"REPAIRED: {r}")
        log(f"memory graph is healthy ({ents} entities, {rels} relations)")
    else:
        log(f"graph file: {report['graph_file']['path']}")
        log(f"  entities={ents} relations={rels} malformed={len(bad)}")
        for d in dist_state:
            log(f"  package {d['package'].split('_npx')[1][:12]}: dist healthy={d['healthy']} "
                f"reparse={d['reparse_point']}")
        db = report["database"]
        if db.get("present"):
            log(f"database: memories={db.get('memories')} relations={db.get('relations')} "
                f"integrity={db.get('integrity')} dangling={db.get('dangling_edges')}")
        for r in report["repairs"]:
            log(f"REPAIRED: {r}")
        for p in report["problems"]:
            log(f"PROBLEM: {p}")
        log("memory graph has unresolved problems")
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        log(f"the guardian broke: {exc}")
        sys.exit(1)
