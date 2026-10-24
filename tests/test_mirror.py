"""
Contract tests for the surface mirror.

The mirror copies the live Hermes surface (skills, scripts, heretik) into the
stack repository so that every accepted change is versioned and reviewable.
That makes it a PUBLICATION surface: whatever lands in it ends up in a public
GitHub repository.

The defect this file pins down: the mirror only ever COPIED. A file deleted
from the live surface stayed in the mirror - and therefore in the public
repository - forever. The gate test proved it: its probe fixture
(`_evo_gate_probe.py`) existed in the live scripts directory for the length
of one test run, was mirrored, and was still committed and pushed to the
public repo a day later.

`diff_targets()` could already report a removed file ("REMOVED <rel>"), but
nothing acted on the report. Detection is not correction.
"""
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from evo import mirror, paths  # noqa: E402

PROBE = "scripts/_mirror_prune_probe.py"


def _live_path() -> Path:
    return paths.HERMES / PROBE


def _mirror_path() -> Path:
    return mirror.MIRROR / PROBE


def test_prune_removes_an_entry_whose_source_is_gone():
    live = _live_path()
    mirror_path = _mirror_path()
    try:
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text('"""prune probe."""\nprint("probe")\n', encoding="utf-8")
        assert mirror.record(PROBE), "the probe must be mirrored"
        assert mirror_path.exists(), "the mirrored copy must exist"
        live.unlink()
        removed = mirror.prune()
        assert PROBE in removed, f"prune must report the removal, got {removed}"
        assert not mirror_path.exists(), "the stale mirror entry must be gone"
    finally:
        if live.exists():
            live.unlink()
        if mirror_path.exists():
            mirror_path.unlink()


def test_prune_keeps_an_entry_whose_source_exists():
    live = _live_path()
    mirror_path = _mirror_path()
    try:
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text('"""prune probe."""\nprint("probe")\n', encoding="utf-8")
        mirror.record(PROBE)
        removed = mirror.prune()
        assert PROBE not in removed, "a live file must never be pruned"
        assert mirror_path.exists(), "a live file must stay mirrored"
    finally:
        if live.exists():
            live.unlink()
        if mirror_path.exists():
            mirror_path.unlink()


def test_prune_leaves_unmanaged_areas_alone():
    """Only the managed subtrees may be touched."""
    stray = mirror.MIRROR / "notes" / "_stray_prune_probe.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("not a managed surface\n", encoding="utf-8")
    try:
        mirror.prune()
        assert stray.exists(), "prune must not touch unmanaged paths"
    finally:
        if stray.exists():
            stray.unlink()
        try:
            stray.parent.rmdir()
        except OSError:
            pass


def test_the_real_surface_has_no_orphans():
    """No published file may lack a live source."""
    orphans = [t for t in mirror.diff_targets() if t.startswith("REMOVED ")]
    assert not orphans, f"the mirror publishes files that no longer exist: {orphans[:5]}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
