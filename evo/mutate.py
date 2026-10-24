"""The proposer: how a candidate improvement is generated.

Local-first. Uses Ollama on 127.0.0.1:11434 (no cloud, no paid model).

The proposer's own prompt lives in the archive as a variant of kind='proposer'.
The best-scoring proposer prompt is used for the next mutation — that is the
recursive part (the improver is itself improvable), and it is what separates
this stack from the old "always apply the latest fix" cron job.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from . import archive, paths


def ollama_chat(system: str, user: str, model: str | None = None,
                temperature: float = 0.4, timeout: int = 180) -> str:
    model = model or paths.DEFAULT_MODEL
    payload = json.dumps({
        "model": model,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{paths.OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return (data.get("message") or {}).get("content", "")


def _extract_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        i, j = text.find("{"), text.rfind("}")
        blob = text[i:j + 1] if i != -1 and j > i else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except Exception:
        return None


def best_proposer_prompt() -> str:
    """The proposer prompt that carries the most learning.

    Priority: the live file written by `evo learn` (it embeds the evidence
    brief) -> the best-scoring archived proposer -> the seed.
    """
    if paths.PROPOSER_PROMPT.exists():
        txt = paths.PROPOSER_PROMPT.read_text(encoding="utf-8", errors="ignore")
        if "## LEARNED CONTEXT" in txt:
            return txt
    best = archive.best_variant(target="proposer_prompt")
    if best and best.get("diff"):
        return best["diff"]
    if paths.PROPOSER_PROMPT.exists():
        return paths.PROPOSER_PROMPT.read_text(encoding="utf-8")
    return paths.SEED_PROPOSER_PROMPT


FORBIDDEN_PATTERNS = [
    (r"git[^\n]{0,120}\badd\b", "git add"),
    (r"git[^\n]{0,120}\bcommit\b", "git commit"),
    (r"['\"]add['\"][^\n]{0,60}['\"]\.['\"]", "git add . (list form)"),
    (r"['\"]commit['\"][^\n]{0,40}['\"]-m['\"]", "git commit (list form)"),
    (r"git\s+(reset\s+--hard|clean\s+-[a-z]*f)", "destructive git operation"),
    (r"Remove-Item\b[^\n]*-Recurse", "recursive delete"),
    (r"shutil\.rmtree", "recursive delete"),
    (r"os\.remove|os\.unlink|Path\([^\n]*\)\.unlink", "file deletion"),
    (r"Remove-Item\b[^\n]*-Force", "forced delete"),
    (r"Format-|diskpart|Clear-Disk", "disk operation"),
    (r"Invoke-Expression|eval\(", "dynamic code execution"),
    (r"reg\s+delete", "registry deletion"),
    (r"schtasks\s+/delete|sc\s+delete", "service/task deletion"),
    (r"Stop-Process[^\n]*-Force[^\n]*(python|node|ollama|hermes)", "process kill"),
]
ALLOWED_TARGET_SUFFIXES = (".py", ".md")


def validate_proposal(target: str, content: str) -> str | None:
    """Return a rejection reason, or None if the proposal is safe to apply."""
    if not (target.startswith("skills/") or target.startswith("scripts/")):
        return f"target outside allowed surface: {target}"
    if ".." in target:
        return "path traversal rejected"
    if not target.lower().endswith(ALLOWED_TARGET_SUFFIXES):
        return f"target type not allowed: {target} (allowed: {ALLOWED_TARGET_SUFFIXES})"
    lowered = content.lower()
    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, lowered):
            return f"forbidden content ({label})"
    if len(content) > 200_000:
        return "proposal too large"
    return None


def propose(failures: list[dict], model: str | None = None) -> dict:
    """Ask the local model for one concrete, benchmark-improving change.

    Returns a proposal dict: {target, content, rationale}.
    `target` is relative to %LOCALAPPDATA%/hermes and MUST be inside the
    allowed surface (skills/ or scripts/).
    """
    proposer = best_proposer_prompt()
    fail_text = json.dumps(failures, indent=1)[:4000]
    system = (
        proposer
        + "\n\nOUTPUT FORMAT: reply with a single JSON object and nothing else:\n"
        '{"target": "<path relative to hermes home, must start with skills/ or scripts/ '
        'and end with .py or .md>",'
        ' "content": "<complete new file content>", "rationale": "<one sentence>"}'
    )
    user = (
        "Benchmark failures on this host (JSON):\n" + fail_text +
        "\n\nPropose ONE .py or .md change that makes a failing check pass. "
        "Output the complete new file content for the target. "
        "No git commands, no deletions, no shell scripts, no service restarts, "
        "no credential access. Do not touch cron/jobs.json or config.yaml."
    )
    raw = ollama_chat(system, user, model=model)
    obj = _extract_json(raw)
    if not obj or "target" not in obj:
        return {"ok": False, "error": "unparseable proposal", "raw": raw[:800]}
    target = str(obj.get("target", "")).replace("\\", "/").strip()
    content = str(obj.get("content", ""))
    reason = validate_proposal(target, content)
    if reason:
        return {"ok": False, "error": reason, "target": target, "raw": raw[:400]}
    return {
        "ok": True,
        "target": target,
        "content": content,
        "rationale": str(obj.get("rationale", ""))[:400],
        "raw": raw[:400],
    }


def apply_content(target: str, content: str) -> Path:
    """Write proposal content to the surface. Callers MUST have snapshotted."""
    dest = paths.HERMES / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest
