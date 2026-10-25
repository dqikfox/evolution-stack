"""A heal that leaves the service inside a short-lived session works once.

The heal used to spawn the launcher with `creationflags=0x08000000` under a
comment that said `# DETACHED_PROCESS`. It was not: 0x08000000 is
CREATE_NO_WINDOW, which hides the console and does nothing else. The real
DETACHED_PROCESS is 0x00000008. The child stayed in the caller's process
group, so a service healed from inside a cron session inherited that
session's lifetime - and died when the session was reaped.

The heal now goes through the house spawner, which detaches properly and
exits immediately, breaking the ancestry chain.

These tests are source-level on purpose: the thing being tested is a
process-creation flag, and the flag is what was wrong.
"""
from __future__ import annotations

from pathlib import Path

STACK = Path(__file__).resolve().parents[1]


def test_the_detach_constants_are_the_real_windows_ones():
    from evo import services

    assert services.DETACHED_PROCESS == 0x00000008, (
        "DETACHED_PROCESS is 0x00000008; 0x08000000 is CREATE_NO_WINDOW, "
        "which only hides the console"
    )
    assert services.CREATE_NEW_PROCESS_GROUP == 0x00000200
    assert services.CREATE_NO_WINDOW == 0x08000000
    assert services.DETACHED_PROCESS != services.CREATE_NO_WINDOW


def test_the_heal_goes_through_the_house_spawner():
    source = (STACK / "evo" / "services.py").read_text(encoding="utf-8")
    assert "_spawn_detached(" in source, "the heal must use the detached spawn path"
    assert "spawn_detached.py" in source, (
        "the heal must use the house spawner - it detaches the child and "
        "exits immediately, which breaks the ancestry chain"
    )
    assert "creationflags=0x08000000" not in source, (
        "the mislabelled CREATE_NO_WINDOW flag is back"
    )


def test_the_fallback_flags_include_detached_process():
    from evo import services

    flags = services.DETACHED_PROCESS | services.CREATE_NEW_PROCESS_GROUP | services.CREATE_NO_WINDOW
    assert flags & services.DETACHED_PROCESS, "the fallback must detach the process"
    assert flags & services.CREATE_NEW_PROCESS_GROUP, (
        "the fallback must give the child its own process group"
    )


def test_the_heal_does_not_use_a_bare_popen_of_the_launcher():
    source = (STACK / "evo" / "services.py").read_text(encoding="utf-8")
    bare = "subprocess.Popen(args" in source or "subprocess.Popen([interpreter" in source
    assert not bare, (
        "the launcher must not be started with a bare Popen from the heal - "
        "that child inherits the caller's session"
    )
