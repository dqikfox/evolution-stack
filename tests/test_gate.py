"""End-to-end test of the DGM gate: accept on improvement, reject + rollback on regression.

Run:  python tests/test_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evo import archive, bench, loop, mutate, paths, snapshot  # noqa: E402
from evo import mirror

PROBE = "scripts/_evo_gate_probe.py"
GOOD = '"""Gate probe (valid)."""\nprint("probe ok")\n'
BAD = '"""Gate probe (deliberately broken)."""\ndef broken(:\n    pass\n'


def _score() -> float:
    sc = bench.run()
    return sc.score


def main() -> int:
    archive.init()
    failures: list[str] = []

    # 1. baseline with a broken file present -------------------------------
    (paths.HERMES / PROBE).write_text(BAD, encoding="utf-8")
    base = _score()
    print(f"[1] baseline with broken probe: {base:.2f}")

    # 2. ACCEPT path: a variant that fixes the broken file -----------------
    vid = archive.add_variant(target=PROBE, summary="fix broken probe",
                              diff=GOOD, kind="file", score_before=base)
    rc = loop.cmd_apply(type("A", (), {"variant_id": vid})())
    v = archive.get_variant(vid)
    if v["status"] != "accepted":
        failures.append(f"expected ACCEPT, got {v['status']} (rc={rc})")
    else:
        print(f"[2] ACCEPT ok — variant #{vid} score_after={v['score_after']:.2f}")

    # 3. REJECT path: a variant that breaks it again -----------------------
    good_score = _score()
    vid2 = archive.add_variant(target=PROBE, summary="re-break probe",
                               diff=BAD, kind="file", score_before=good_score)
    rc = loop.cmd_apply(type("A", (), {"variant_id": vid2})())
    v2 = archive.get_variant(vid2)
    if v2["status"] != "rejected":
        failures.append(f"expected REJECT, got {v2['status']} (rc={rc})")
    else:
        print(f"[3] REJECT ok — variant #{vid2} rolled back")
    restored = (paths.HERMES / PROBE).read_text(encoding="utf-8")
    if restored != GOOD:
        failures.append("rollback did not restore the good content")
    else:
        print("[3b] rollback restored original content")

    # 4. cleanup -----------------------------------------------------------
    (paths.HERMES / PROBE).unlink(missing_ok=True)
    # The accepted phase MIRRORS the probe into the surface mirror, which is
    # a public repository's working tree. Leaving it there means a test
    # artefact sits in a repo until the next mirror run prunes it - and in
    # that window a commit could sweep it into the published surface. The
    # test owns its artefacts in BOTH surfaces.
    mirrored = mirror.MIRROR / PROBE
    if mirrored.exists():
        mirrored.unlink()
        print("[4a] removed the mirrored probe from the published surface")
    final = _score()
    print(f"[4] final score after cleanup: {final:.2f}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nGATE TEST PASSED — accept-on-improve, reject-and-rollback-on-regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
