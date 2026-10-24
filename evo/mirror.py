"""Mirror the improvable surface into the stack repo.

The surface lives in %LOCALAPPDATA%/hermes (skills + scripts), which is not a
git repository. Without a mirror, every accepted change is invisible to
version control and to review. The mirror keeps a copy of each changed file
under `surface-mirror/<relative path>` inside the stack repo, so the history
of what the loop actually changed is inspectable and diffable.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import paths

MIRROR = paths.STACK / "surface-mirror"


MAX_FILE_BYTES = 512 * 1024

# Files the mirror refused to publish because they contain a secret-shaped
# value. Populated by record(); read by the bench and the mirror CLI.
REFUSED: list = []


def _skip(rel: str) -> bool:
    """Dot-directories (.hub, .locks, .curator_backups) and big binaries are
    not part of the improvable surface — mirroring them bloated the repo to
    254 MB of tarballs and index caches."""
    if any(part.startswith(".") for part in Path(rel).parts):
        return True
    src = paths.HERMES / rel
    try:
        if src.stat().st_size > MAX_FILE_BYTES:
            return True
    except Exception:
        return True
    return False


def secret_findings(rel: str) -> list:
    """Secret-shaped values in a file that is about to be published.

    A mirror copies files verbatim into a repository that is pushed to
    GitHub. It will eventually copy a secret. This is the check that stops
    that: a file with a secret-shaped value is never mirrored.
    """
    from .secrets import scan_file
    src = paths.HERMES / rel
    if not src.exists() or not src.is_file():
        return []
    return scan_file(src)


def record(target: str) -> str | None:
    """Copy hermes/<target> into the mirror. Returns the mirrored path.

    A file containing a secret-shaped value is refused: the mirror is a
    publishing surface, and a secret that reaches it reaches a public
    repository.
    """
    src = paths.HERMES / target
    if not src.exists() or not src.is_file():
        return None
    if _skip(target):
        return None
    findings = secret_findings(target)
    if findings:
        REFUSED.append((target, [str(f) for f in findings]))
        return None
    dest = MIRROR / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return str(dest)


def record_all() -> list[str]:
    """Mirror every file currently in the surface. Used to seed the repo.

    Files containing a secret-shaped value are refused and recorded in
    REFUSED. The caller is expected to surface them - a silent refusal
    would look like "nothing to mirror" and the secret would stay where
    it is, in the clear.
    """
    REFUSED.clear()
    out = []
    for root in (paths.SKILLS_DIR, paths.SCRIPTS_DIR):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(x in p.parts for x in ("__pycache__", ".venv", "node_modules")):
                continue
            try:
                rel = p.relative_to(paths.HERMES).as_posix()
            except ValueError:
                continue
            if record(rel):
                out.append(rel)
    return out


def diff_targets() -> list[str]:
    """Surface files that differ from their mirrored copy."""
    out = []
    if not MIRROR.exists():
        return out
    for p in MIRROR.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(MIRROR).as_posix()
        src = paths.HERMES / rel
        if not src.exists():
            out.append(f"REMOVED {rel}")
            continue
        try:
            if src.read_bytes() != p.read_bytes():
                out.append(f"CHANGED {rel}")
        except Exception:
            out.append(f"UNREADABLE {rel}")
    return out


if __name__ == "__main__":
    import json
    print(json.dumps({"mirrored": len(record_all()), "ts": time.time()}, indent=2))
