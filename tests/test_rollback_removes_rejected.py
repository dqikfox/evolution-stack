"""A rejected variant must not leave its file behind in the surface.

Observed on 2026-10-27: variant #115 proposed `skills/recover_comfyui.md`
at 07:54 and the gate rejected it at 07:56. The rollback restored the
snapshot - and the restore is additive, so it never deleted anything. The
rejected file stayed in skills/, and `skills/recover_nexus.md` had survived
the same way from variant #113. Both were then published by the mirror like
real skills, and the next cycle found the artefact and proposed the same
rejected idea again.

Two properties are worth pinning:

  1. The rollback removes the rejected variant's OWN target.
  2. The rollback removes NOTHING ELSE. The restore is additive on purpose:
     a file added to the surface after the snapshot was taken is a
     legitimate concurrent edit, not a leftover, and a rollback that
     deleted it would silently destroy unrelated work.

These tests are source-level plus one live filesystem check, because the
thing being tested is a rollback's file-effect on a real tree.
"""
from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

STACK = Path(__file__).resolve().parents[1]
if str(STACK) not in sys.path:
    sys.path.insert(0, str(STACK))


def test_the_rollback_removes_the_rejected_variant_file():
    """The rejection path must delete the variant's own target."""
    from evo import loop

    src = inspect.getsource(loop.cmd_apply)
    assert "_remove_rejected_target" in src, (
        "cmd_apply must call _remove_rejected_target when the gate rejects a "
        "variant; restoring the snapshot is additive and never deletes"
    )
    # The removal must happen BEFORE the restore, so the restore cannot
    # resurrect the file it just deleted.
    assert src.index("_remove_rejected_target") < src.index("snapshot.restore"), (
        "the rejected file must be removed BEFORE the snapshot is restored"
    )


def test_the_removal_touches_only_the_variant_target():
    """_remove_rejected_target must delete exactly one named file."""
    from evo import loop

    src = inspect.getsource(loop._remove_rejected_target)
    assert "unlink" in src, "the helper must unlink the file"
    # No directory removal, no glob, no rmtree: a rollback that removed a
    # directory would take unrelated files with it.
    for forbidden in ("rmtree", "glob(", "rglob(", "iterdir"):
        assert forbidden not in src, (
            f"_remove_rejected_target must not use {forbidden} - it deletes one "
            f"named file and nothing else"
        )


def test_the_removal_actually_deletes_the_file(tmp_path, monkeypatch):
    """Live check: point the helper at a temp tree and prove the file goes."""
    from evo import loop, paths

    target = tmp_path / "skills" / "rejected_thing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# rejected artefact\n", encoding="utf-8")

    monkeypatch.setattr(paths, "HERMES", tmp_path)
    removed = loop._remove_rejected_target("skills/rejected_thing.md")

    assert removed, "the helper must report the path it removed"
    assert not target.exists(), "the rejected file must be gone from the surface"
    assert not target.parent.exists() or not any(target.parent.iterdir()), (
        "the emptied directory must not be left holding anything"
    )


def test_the_removal_leaves_unrelated_files_alone(tmp_path, monkeypatch):
    """A file that is NOT the variant's target must survive."""
    from evo import loop, paths

    rejected = tmp_path / "skills" / "rejected_thing.md"
    unrelated = tmp_path / "scripts" / "important.py"
    concurrent = tmp_path / "skills" / "added_after_the_snapshot.md"
    for p in (rejected, unrelated, concurrent):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")

    monkeypatch.setattr(paths, "HERMES", tmp_path)
    loop._remove_rejected_target("skills/rejected_thing.md")

    assert not rejected.exists()
    assert unrelated.exists(), "an unrelated script must not be deleted"
    assert concurrent.exists(), (
        "a file added to the surface after the snapshot is a legitimate "
        "concurrent edit and must survive a rollback"
    )


def test_the_removal_is_safe_when_the_target_is_absent(tmp_path, monkeypatch):
    """Removing a target that is not there must not raise."""
    from evo import loop, paths

    monkeypatch.setattr(paths, "HERMES", tmp_path)
    assert loop._remove_rejected_target("skills/never_existed.md") == ""
    assert loop._remove_rejected_target("") == ""


def test_the_restore_is_additive(tmp_path, monkeypatch):
    """The snapshot restore must not delete a file it does not contain."""
    from evo import paths, snapshot

    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "in_snapshot.py").write_text("original\n", encoding="utf-8")
    # The surface roots are module-level constants, so they must be patched
    # as well as HERMES - patching only HERMES would snapshot the real tree.
    monkeypatch.setattr(paths, "HERMES", tmp_path)
    monkeypatch.setattr(paths, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(paths, "SCRIPTS_DIR", tmp_path / "scripts")
    monkeypatch.setattr(paths, "SNAPSHOTS", tmp_path / "snaps")
    monkeypatch.setattr(snapshot, "SURFACE_FILES", [])
    (tmp_path / "snaps").mkdir()

    sid = snapshot.create(label="test")
    # A file added AFTER the snapshot.
    (tmp_path / "scripts" / "added_later.py").write_text("new\n", encoding="utf-8")
    # The snapshot's own file is changed on disk.
    (tmp_path / "scripts" / "in_snapshot.py").write_text("CHANGED\n", encoding="utf-8")

    snapshot.restore(sid)

    assert (tmp_path / "scripts" / "in_snapshot.py").read_text(encoding="utf-8") == "original\n", (
        "the snapshot's content must be restored"
    )
    assert (tmp_path / "scripts" / "added_later.py").exists(), (
        "the restore must be additive: a file the snapshot does not mention "
        "is not the rollback's to delete"
    )
