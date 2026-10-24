# THRONE Stack Analysis — TESSERACT & NEXUS CORE

**Date:** 2026-10-25
**Scope:** `C:\Users\KING\Projects\TESSERACT` (:8705) and `E:\ultron-memory\nexus-core` (:8650), plus the contract that binds them to the rest of THRONE.

This is an analysis of what already existed, followed by the fixes that came out of it. Everything below was verified against the live machine.

---

## 1. What these two systems actually are

### TESSERACT — the control plane
FastAPI service on **:8705**. 3,619-line `server.py` + `core/` modules. It is the dashboard and the operator console for the whole stack:

- **Service census** — 10 registered services, refreshed every 15s, pushed to browsers over WebSocket, with alert flips on healthy↔unhealthy transitions.
- **Ollama control** — load / unload / pull / delete models, running-process map.
- **Session + graph** — 238 sessions, 288 nodes / 1,592 edges, a vault graph view.
- **Mail** — Fastmail unread-count push.
- **Agents** — agent router with a second router mounted.
- **Buttons** — start/stop services from the UI, with `running_locally` derived from process state.

### NEXUS CORE — the knowledge plane
FastAPI service on **:8650**, 2,458 indexed notes. It is the retrieval and answer layer:

- **Chroma vector store** — collection `nexus`, 2,087 vectors, 384-dim (ONNX all-MiniLM-L6-v2).
- **Hybrid search** — vector + FTS, with source boosting (`core/search.py`).
- **RAG** — `/api/ask` retrieves context and generates an answer via Ollama (`core/rag.py`).
- **Hive bus** — agent-to-agent messaging channel, each post also written as a note and embedded.
- **Importers** — Obsidian, Notion, Mem0, markdown trees (`importers/markdown.py`).
- **MCP server** — `mcp_server.py` exposes NEXUS to MCP clients.

### The contract between them
TESSERACT's census probes `http://127.0.0.1:8650/health` every 15 seconds. That is the whole integration: TESSERACT watches NEXUS. Everything else was disconnected.

---

## 2. What was actually broken

| # | Defect | Impact | Severity |
|---|---|---|---|
| 1 | **NEXUS had no working vector store.** No interpreter on the host had `numpy`+`chromadb` together: the running instance was a uv base python without numpy; the repo `.venv` had a broken numpy (DLL load failed). | `/health` said `chroma: not_ready`. Search fell back to keyword only. | **Critical** |
| 2 | **The ONNX model cache was ACL-locked.** The extracted `onnx/` directory was unreadable even to its owner; `icacls` could not read its ACL and `takeown` was denied. chromadb re-extracted the tarball on every query and failed with `PermissionError`. | `/api/ask` returned HTTP 500. The flagship endpoint was dead. | **Critical** |
| 3 | **The answer model was not installed.** `OLLAMA_MODEL = granite4.1:8b`; that model is not on this host. | `/api/ask` returned `"Ollama call failed"` plus raw context. | **High** |
| 4 | **NEXUS was functionally blind to its own subject.** 2,454 notes, **zero** mentioning Lummings or Lumo. The flagship product was absent from the knowledge core. | RAG could not answer a single question about the product. | **High** |
| 5 | **Test artefacts were in the live index.** 58 notes from `hive-tests-*` / `tests-verify-*` runs polluted every search. | Search results included pytest output. | **Medium** |
| 6 | **NEXUS had no supervisor.** It died with `OSError: [WinError 64]` on socket accept and stayed dead. | The knowledge core was gone until a human noticed. | **High** |
| 7 | **TESSERACT's service registry pointed at a dead address.** Four entries used `192.168.4.230` for MSI — a stale DHCP lease. | Those services were permanently "offline" regardless of reality. | **Medium** |
| 8 | **Local services were classified as remote.** n8n (verified running on :5678) and the Hermes API server (:8642, per `hermes/config.yaml`) were listed as MSI services. | Both always reported offline; n8n was not healable. | **Medium** |
| 9 | **The health endpoint was structurally wrong.** It probed NEXUS live, and the census that includes TESSERACT calls `/health` → self-recursion; the nested request timed out and the dashboard reported TESSERACT as offline. | A healthy instance reported itself down. | **Medium** |
| 10 | **A failing test and a missing test.** The route-registration test broke on a FastAPI upgrade (`app.routes` no longer flat). No test covered startup. | 1 failing test; a real startup crash (`NameError` in the banner) reached production undetected. | **Medium** |
| 11 | **Neither repo had CI.** | Every defect above was findable only by running the thing by hand. | **Process** |

---

## 3. What was fixed

### NEXUS CORE → `1178261`
- **Canonical interpreter rebuilt** — `C:\Users\KING\.cache\nexus-venv` (the path `start.ps1` already documented): Python 3.12.14, numpy 2.5.4, chromadb 1.5.9, fastapi 0.162, uvicorn 0.54, jinja2, pytest. The repo `.venv_broken` was deleted.
- **ONNX cache relocated** to `E:\ultron-memory\.cache\chroma-models\all-MiniLM-L6-v2` (writable, `onnx.tar.gz` copied locally so nothing re-downloads), exposed as `config.ONNX_MODEL_CACHE` / `NEXUS_ONNX_CACHE`.
- **Answer model** → `starscream-64k` (stack default, resident, 64K context floor), overridable via `NEXUS_OLLAMA_MODEL`.
- **Knowledge base repaired** — 58 test-artifact notes purged (with their vectors), 71 project notes ingested (Lummings docs + brand canon, TESSERACT docs). `tools/maintain_knowledge.py` makes both repeatable.
- **Supervisor** — `run_nexus.py`: restarts uvicorn with capped backoff, takes :8650 back from an orphaned previous instance, uses the Windows selector event loop policy, writes `logs/supervisor_status.json`.
- **Version unified** in `core.config.VERSION` (was hardcoded in three places).
- **Tests** — startup-lifespan regression test added; hive timeout 5s → 30s (a cold ONNX load, not a slow endpoint). 27/27 pass.
- **CI** — import smoke test, config/dependency contract (ONNX cache writable, answer model installed), knowledge-base contract (no test artefacts).

**Verified:** `/health` → `chroma: ok, vectors: 2087`, 2,458 notes. `/api/ask?q=What is the Lummings project?` returns a cited answer naming the app, the studio, the entity and the campaign.

### TESSERACT → `71459fd`
- **Service registry corrected** — MSI addressed by Tailscale (`100.83.120.56`), n8n and the Hermes API server reclassified as local, `SSH_TARGETS` updated to the same stable address.
- **`/health` rebuilt** as a true liveness probe: local-only, **~5 ms**, reports uptime, database state and a service summary from the background loop's cache. Original `ok`/`service`/`version` contract preserved.
- **Test suite** — the version-fragile route test rewritten to walk the router tree; the "hermes is remote" assumption corrected; 312 pass, 1 skip.
- **CI** — `scripts/audit_assets.py` (every `src`/`href` in templates and static must resolve; unresolved placeholders reported) + full pytest + a `/health` contract test.
- **Repo hygiene** — 68 loose PNGs archived to `docs/screenshots/`, a crash dump removed, `templates/index.html.pre-purge.bak` untracked.

### The contract between them
- `E:\ultron-memory\infra\SERVICES.json` now carries the truth: nexus → `run_nexus.py` under the canonical venv, tesseract → `/health`, n8n → its existing idempotent launcher, ULTRON :8666 → retired and never checked.
- `evo/services.py` honours a declared `interpreter`, so the healer can start NEXUS correctly instead of guessing `python`.

**Verified:** 9 services surveyed — 8 up, discovery optional, ULTRON retired. Gate score **100.00**, host score **96.08** (was 86.70 before this pass). Gate test re-run: accept `+7.14`, reject `−7.14`, rollback byte-identical.

---

## 4. Integration gaps that remain

| Gap | What it means | Next move |
|---|---|---|
| **NEXUS is not in TESSERACT's write path** | TESSERACT reads NEXUS's health but never asks it anything. The dashboard has no "ask the brain" surface. | Add a `/api/nexus/ask` passthrough on TESSERACT, surfaced in the dashboard next to the graph. |
| **Hive bus is under-used** | The hive is a working agent-to-agent channel, but nothing in THRONE posts to it on a schedule. | Route the evolution loop's findings to the hive so agents see them. |
| **NEXUS is not indexed from TESSERACT** | TESSERACT's own 288-node graph and 238 sessions are not in the knowledge core; the two planes know about different things. | Ingest TESSERACT's session/graph data via `tools/maintain_knowledge.py`. |
| **Discovery :8660 has no start path** | The one genuinely unknown service in the registry. | Find or retire it. |
| **Hermes API server :8642 is down** | Configured in `hermes/config.yaml` (`gateway.platforms.api_server`), nothing listening. It is the OpenAI-compatible endpoint for the whole stack. | Start it with `API_SERVER_KEY` from 1Password, then make it the standard client target. |
| **The `nexus-core` skill is duplicated across profiles** | Same skill in the default and vision profiles. | Consolidate — one canonical skill. |
| **NEXUS `ingest/alchemy_graph` is untracked** | The alchemy graph ingest is not in the repo. | Commit it with its data contract. |
| **The evolution loop proposes only file edits** | It cannot yet change a service's *configuration* (ports, model choice, registry entries) — which is where several of today's defects lived. | Extend the proposer to the registry and config files, with the same gate and rollback. |

---

## 5. The pattern worth naming

Every one of the eleven defects shares a shape: **the thing reported healthy was not healthy, and nothing questioned the report.**

- NEXUS answered `/health` with `200 OK` and `chroma: not_ready` in the same payload.
- TESSERACT reported itself offline while serving the census.
- The service registry pointed at an address that had not existed for weeks.
- A test suite that never ran the lifespan passed against a service that could not start.

The fix is not more tests — it is **making the health payload assert the thing you care about, and making a stale address impossible**. That is now enforced: the CI contract tests read the component blocks, the registry points at Tailscale addresses instead of DHCP leases, and every long-lived service has a supervisor that is *proven* by killing it.
