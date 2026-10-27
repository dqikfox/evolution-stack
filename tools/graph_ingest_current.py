#!/usr/bin/env python3
"""Ingest current estate facts into ultron-memory.db and rebuild their relations.

Uses the MemoryStore schema from scripts/store.py. Relation algorithm follows the
house pattern (tag/entity/source overlap; entities > tags > source), with a
seen-pair set to avoid writing both A->B and B->A.

Idempotent: memories are keyed by a stable source_hash, so re-running does not
duplicate rows. Existing relations for a pair are left alone.
"""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import MemoryStore  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "db" / "ultron-memory.db"
SOURCE = "estate-current"

# (content, category, tags, entities, priority)
FACTS = [
    ("THRONE is the sovereign seat of the Ultron ecosystem: memory, authority, execution. It runs as the Hermes profile 'throne' with the persona Megatron and serves as Hitchy's second brain, system admin and network admin.", "identity", ["throne", "identity", "current", "ultron"], ["THRONE", "Ultron", "Hitchy"], 1.0),
    ("Hitchy is Jamie Hitch, born 1988, Australia/Sydney, home base Blackett NSW. Email dqikst@gmail.com, GitHub dqikfox. Biological memory is unreliable so THRONE is the external record.", "person", ["hitchy", "identity", "current"], ["Hitchy", "Jamie Hitch"], 1.0),
    ("THRONE host hardware ground truth: Windows 11, account THRONE\\KING, profile C:\\Users\\KING, Xeon W-2235, 64GB RAM, NVIDIA RTX 3090 24GB. Drives: C OS, D ai, E durable, Q subst to E. Tailscale throne.tail886dbb.ts.net 100.125.242.124.", "hardware", ["throne", "hardware", "current", "tailscale"], ["THRONE host", "RTX 3090", "Tailscale"], 1.0),
    ("TESSERACT is the Personal OS dashboard and base of operations at C:\\Users\\KING\\Projects\\TESSERACT on branch master, serving port 8705. It surfaces telemetry, tool repos, tasks and project coordination.", "project", ["tesseract", "project", "current", "dashboard"], ["TESSERACT", "THRONE"], 0.9),
    ("NEXUS CORE is the primary local knowledge base at E:\\ultron-memory\\nexus-core, serving port 8650, with a FastAPI RAG API (/api/ask, /api/vault-graph, /api/memory) and an OpenAI-compatible bridge. Health is cached 20s; ?deep=1 forces a full check.", "project", ["nexus", "knowledge", "current", "rag"], ["NEXUS CORE", "THRONE"], 0.9),
    ("HERETIK is the local inference service on port 8080 with its backend on 8082 started on demand, reachable through the THRONE MCP heretik_chat and heretik_models tools. KRYSYS is the local service on port 8500.", "service", ["heretik", "krysys", "service", "current", "local-llm"], ["HERETIK", "KRYSYS", "THRONE"], 0.8),
    ("The EVOLUTION STACK at E:\\ultron-memory\\evolution-stack (GitHub dqikfox/evolution-stack) runs the DGM/SICA loop: archive.db lineage, bench, snapshot with auto-rollback, Ollama proposer, learning bridge and surface-mirror. It hosts the house test suite and the estate gate.", "project", ["evolution", "current", "dgm", "sica"], ["EVOLUTION STACK", "THRONE"], 0.9),
    ("The 2026-10-25 secret leak in surface-mirror published N8N_ENCRYPTION_KEY to a public repo. It was rotated into 1Password item N8N_ENCRYPTION_KEY and the git history purged. Guards now in place: evo/secrets.py scanner, mirror refuses to publish secrets, bench gates secrets:*, safe_commit.py refuses to stage one.", "security", ["security", "secret-leak", "current", "evolution"], ["EVOLUTION STACK", "1Password", "N8N_ENCRYPTION_KEY"], 1.0),
    ("ChatGPT Plus is reachable without an API key by riding the Codex CLI OAuth session at ~/.codex/auth.json with auth_mode chatgpt. Raw HTTP fails and every model is refused, so the CLI is the transport. Use plugins/.plugin-appserver/codex.exe 0.162.0, never .sandbox-bin 0.149.0. Registered in provider_router.py as kind=codex, model gpt-6-astra, 300s timeout, $0.", "service", ["chatgpt", "codex", "current", "provider"], ["ChatGPT via Codex CLI", "provider_router.py"], 0.9),
    ("1Password is the vault of record for all secrets, service account at C:\\Users\\KING\\.ultron\\.op_service_account, vault name credentials. Never write secret values into MEMORY.md, USER.md, SOUL.md, Obsidian, Notion, NEXUS or git; index by service, username, vault title and rotation date instead.", "security", ["secrets", "1password", "current", "policy"], ["1Password", "Hitchy"], 1.0),
    ("An unsigned 896-939MB WIservice.exe with logon persistence was found and stopped on 2026-10-25. Persistence was removed and the payload preserved at E:\\quarantine\\WIservice_20261025\\ awaiting a keep, delete or restore decision.", "security", ["security", "quarantine", "current", "malware"], ["WIservice.exe quarantine", "THRONE"], 0.9),
    ("The SERVICE CONTRACT established 2026-10-25: every service has exactly one idempotent launcher under hermes/scripts/, and the Startup shortcut, registry entry and healer all point at that launcher. Launchers clear PYTHONPATH and keep the secret manager out of the process chain.", "convention", ["convention", "service", "current", "launcher"], ["SERVICE CONTRACT", "THRONE"], 0.9),
    ("PORT MAP at E:/ultron-memory/infra/PORT_MAP.json and SERVICES.json is the canonical service registry and must be read before starting any service. Live ports: 11434 Ollama, 8080 HERETIK, 8500 KRYSYS, 8650 NEXUS, 8705 TESSERACT, 18789 gateway. ULTRON on 8666 is retired and must never be health-checked.", "tooling", ["port-map", "infra", "current", "services"], ["PORT MAP", "NEXUS CORE", "HERETIK", "TESSERACT"], 1.0),
    ("The HERMES MCP fleet is 22 configured servers with 18 stdio servers live exposing 197 tools as of 2026-10-25. Stdio servers must use command C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe because bare python lacks mcp.server.mcpserver. The '${VAR}' default syntax '${VAR:-default}' is not supported. Enabled does not mean connected: use mcp_doctor.py and mcp_call.py.", "tooling", ["mcp", "hermes", "current", "tooling"], ["HERMES MCP fleet", "HERMES MCP server v2"], 0.9),
    ("The THRONE MCP server v2 lives at AppData/Local/hermes/mcp/throne/server.py and exposes 32 tools covering health, telemetry, processes, services, firewall, disk, network, events, nmap, ping, port_check, tailnet, adb, op, ollama, heretik, logs, files, mounts and nexus. Skill: throne-sysadmin-network.", "tooling", ["mcp", "throne", "current", "tooling"], ["HERMES MCP server v2", "THRONE"], 0.9),
    ("The MCP memory server knowledge graph is persisted at E:\\ultron-memory\\memory-graph\\memory.jsonl. The npx cache package directory is junctioned to that location so the server's temp-file plus rename writes land on E: instead of the volatile npm cache.", "tooling", ["memory", "mcp", "current", "graph", "persistence"], ["MCP memory graph", "E:\\ultron-memory\\memory-graph"], 0.9),
    ("The S23 Ultra SCG19 is the daily driver Android 16 phone on Vodafone AU, with ADB at C:\\Users\\KING\\platform-tools-latest-windows\\platform-tools\\adb.exe over USB and wireless 192.168.4.241:5555. The Cyclone-C4 device is rooted and carries Simplex Chat v7.0.4 profile xzrw; an elevenlabs.key sits in plaintext on it and is flagged for migration into 1Password and wipe.", "device", ["phone", "adb", "current", "android"], ["S23 Ultra (SCG19)", "Cyclone-C4", "THRONE"], 0.8),
    ("The MSI host is mesh Tier 1: i5-13420H, RTX 3050 4GB, 64GB RAM, Tailscale 100.83.120.56 with Ollama on 11434, SSH as CHANN0$ with key E:/ultron-memory/termius-config/id_ed25519. It has been offline since approximately 2026-10-16.", "hardware", ["msi", "mesh", "current", "hardware"], ["MSI host", "Tailscale"], 0.8),
    ("DEV DIARY is at C:\\Users\\KING\\Projects\\dev diary (GitHub dqikfox/dev-diary) on port 8530 with launcher start_devdiary.cmd. Its estate register covers TODO, DIARY, Calendar, Projects, Secure, Configs and Network, with credentials rendered as #######.", "project", ["dev-diary", "project", "current"], ["DEV DIARY"], 0.8),
    ("GOLD ATLAS is at C:\\Users\\KING\\Documents\\GOLD AU on port 8767 with launcher start_goldatlas.cmd, public at https://throne-1.tail886dbb.ts.net/. Port 8766 is QMS rather than the atlas, and the atlas probe is body-aware.", "project", ["gold-atlas", "project", "current"], ["GOLD ATLAS"], 0.8),
    ("LUMMINGS is published from docs/ at dqikfox.github.io/lummings/. Root-absolute references 404 there, so every reference must keep the /lummings/ prefix. The link audit script is scripts/audit_site_links.py.", "site", ["lummings", "site", "current", "publishing"], ["LUMMINGS"], 0.8),
    ("PIXEL studio runs as a single detached process on port 8520 with no supervisor; its launcher probes /api/state before reclaiming the port.", "service", ["pixel", "service", "current"], ["PIXEL studio"], 0.7),
    ("The 2026-10-27 GitHub identity audit checked 68 repos and 352 branches and found 0 unlinked local identities and 0 errors. The audit used a treeless bare clone plus one git log --all per repo, with the API retained as proof.", "ops", ["github", "audit", "current", "identity"], ["GitHub", "dqikfox"], 0.8),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def build_relations(store, new_mems, all_mems, k=5):
    seen = set()
    rows = []
    for m in new_mems:
        m_tags = set(m["tags"])
        m_ents = set(m["entities"])
        m_src = m.get("source")
        scores = []
        for other in all_mems:
            if other["uuid"] == m["uuid"]:
                continue
            o_tags = set(other["tags"])
            o_ents = set(other["entities"])
            tag_o = len(m_tags & o_tags)
            ent_o = len(m_ents & o_ents)
            same_src = 1 if m_src and m_src == other.get("source") else 0
            score = (tag_o * 0.3) + (ent_o * 0.5) + (same_src * 0.2)
            if score > 0:
                scores.append((other["uuid"], score, tag_o, ent_o))
        scores.sort(key=lambda x: x[1], reverse=True)
        for other_uuid, score, tag_o, ent_o in scores[:k]:
            pair = tuple(sorted([m["uuid"], other_uuid]))
            if pair in seen:
                continue
            seen.add(pair)
            if tag_o > 0 and ent_o > 0:
                rel = "shares_context"
            elif ent_o > 0:
                rel = "shares_entity"
            elif tag_o > 0:
                rel = "shares_tags"
            else:
                rel = "same_source"
            rows.append((m["uuid"], other_uuid, rel, round(score, 4), now_iso()))
    return rows


def main():
    store = MemoryStore(str(DB))
    added, skipped = [], []
    for content, category, tags, entities, priority in FACTS:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if store.get_by_hash(digest):
            skipped.append(content[:60])
            continue
        uuid = store.add(content=content, summary=content[:180], category=category,
                         tags=tags, entities=entities, source=SOURCE,
                         confidence=1.0, priority=priority, source_hash=digest)
        added.append(uuid)

    with sqlite3.connect(str(DB)) as conn:
        conn.row_factory = sqlite3.Row
        raw = conn.execute("SELECT * FROM memories").fetchall()
    all_mems = []
    for r in raw:
        d = dict(r)
        for col in ("tags", "entities"):
            try:
                d[col] = json.loads(d.get(col) or "[]")
            except Exception:
                d[col] = []
        all_mems.append(d)

    by_uuid = {m["uuid"]: m for m in all_mems}
    new_mems = [by_uuid[u] for u in added if u in by_uuid]
    rels = build_relations(store, new_mems, all_mems)

    inserted = 0
    with sqlite3.connect(str(DB)) as conn:
        for src, dst, rel, strength, ts in rels:
            cur = conn.execute(
                "INSERT OR IGNORE INTO memory_relations "
                "(source_uuid, target_uuid, relation, strength, created_at) "
                "VALUES (?,?,?,?,?)", (src, dst, rel, strength, ts))
            inserted += cur.rowcount
        conn.commit()

    total_m = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    total_r = conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
    print(json.dumps({
        "added_memories": len(added),
        "skipped_existing": len(skipped),
        "relations_built": len(rels),
        "relations_inserted": inserted,
        "memories_total": total_m,
        "relations_total": total_r,
    }, indent=2))


if __name__ == "__main__":
    main()
