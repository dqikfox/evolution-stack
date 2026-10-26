"""Canonical locations for the THRONE Evolution Stack. Single source of truth."""
from __future__ import annotations

import os
from pathlib import Path

HERMES = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local")) / "hermes"
STACK = Path(r"E:\ultron-memory\evolution-stack")
STATE = STACK / "state"
REPORTS = STACK / "reports"
SNAPSHOTS = STACK / "snapshots"
ARCHIVE_DB = STATE / "archive.db"

# --- the improvable surface: what the stack is allowed to change -------------
SKILLS_DIR = HERMES / "skills"
SCRIPTS_DIR = HERMES / "scripts"
# HERETIK owns its own directory (the demand proxy and its launcher).
# It is part of the improvable surface: a change to the proxy is a change
# to the stack, and it must be versioned like everything else.
HERETIK_DIR = HERMES / "heretik"
CONFIG_YAML = HERMES / "config.yaml"
CRON_JOBS = HERMES / "cron" / "jobs.json"
MEMORY_MD = HERMES / "memories" / "MEMORY.md"
USER_MD = HERMES / "memories" / "USER.md"

# candidate proposer prompt (the recursive part: the improver is improvable)
PROPOSER_PROMPT = STATE / "proposer_prompt.txt"
SEED_PROPOSER_PROMPT = """You are the THRONE evolution engineer on Windows host THRONE.
You propose ONE durable improvement to the local Hermes automation surface:
a Python script under %LOCALAPPDATA%/hermes/scripts/ or a skill file under
%LOCALAPPDATA%/hermes/skills/. Only .py and .md targets are accepted.
Rules: local-first, no paid model pins, no phishing tooling, one change only,
no git commands, no deletions, no service restarts, no credential access.
Reply with a single JSON object.
"""

# --- integrated external components -----------------------------------------
DARWINIAN_EVOLVER = Path(r"E:\ultron-memory\darwinian_evolver")
LEGACY_EVOLVE = Path(r"C:\Users\KING\Projects\evolution")
SCOUT = HERMES / "scripts" / "evolution_scout.py"
WATCHDOG = HERMES / "scripts" / "watchdog.py"
SCOUT_REPORT = HERMES / "cron" / "output" / "evolution_scout.json"
# The scout's OWN copy. The cron engine owns cron/output, and the gate
# must not read its freshness input from a directory another system can
# prune. This one is written by the scout and read by the bench.
SCOUT_STATE_REPORT = HERMES / "state" / "evolution_scout.json"
SCOUT_LOG = HERMES / "cron" / "output" / "evolution_scout.log"
HEALTH_STATE = HERMES / "cron" / "output" / "health_state.json"

# --- services ---------------------------------------------------------------
CANONICAL_SERVICES = {
    "nexus": 8650,
    "ultron": 8666,
    "krysys": 8500,
    "tesseract": 8705,
    "ollama": 11434,
    "heretik": 8080,
}
# Services with no local file-level healer: reported, but NOT part of the gate
# score. Restarting them is an operator action, so the automated loop must not
# chase them (that is how a loop ends up proposing nonsense fixes).
OPERATOR_LEVEL_SERVICES = {"ultron", "krysys", "heretik"}
GATEWAY_PORT = 18789

# Canonical start-path registry. A service that has a start path here is
# gate-actionable: the loop is allowed to restart it instead of just
# reporting it. A service marked "retired" is never health-checked at all
# (it had no implementation - e.g. ULTRON :8666, whose project directory was
# deleted, so the check was chasing a ghost).
SERVICES_REGISTRY = Path(r"E:\ultron-memory\infra\SERVICES.json")
PORT_MAP = Path(r"E:\ultron-memory\infra\PORT_MAP.json")
# A remote peer registry: the machines on the tailnet that run their own
# Hermes. They are part of the estate, so they are probeable and healable.
PEER_REGISTRY = Path(r"E:\ultron-memory\infra\REMOTE_AGENTS.json")

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "starscream-64k"

# --- repos under management ------------------------------------------------
KEY_REPOS = [
    Path(r"C:\Users\KING\Projects\TESSERACT"),
    Path(r"C:\Users\KING\projects\lumming"),
    Path(r"C:\Users\KING\projects\pixel"),
    Path(r"C:\Users\KING\projects\pathwaytoscripture"),
]


def ensure_dirs() -> None:
    for d in (STATE, REPORTS, SNAPSHOTS):
        d.mkdir(parents=True, exist_ok=True)
    if not PROPOSER_PROMPT.exists():
        PROPOSER_PROMPT.write_text(SEED_PROPOSER_PROMPT, encoding="utf-8")
