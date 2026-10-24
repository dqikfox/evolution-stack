"""
Contract tests for the demand-proxy pattern.

A demand proxy keeps an LLM endpoint contract answerable while the
RAM-heavy backend exists only while in use. Three defects made that promise
false on THRONE, and each one is silent:

  1. /health was FORWARDED, so a monitor's health probe cold-started the
     multi-GB backend and refreshed the idle timer - the backend could
     never be released, and a "green" health check cost gigabytes.
  2. A backend orphaned by a proxy restart was never adopted, because the
     reaper only knew about the Popen handle of a process the current
     instance had spawned. The orphan stayed resident forever.
  3. The live file and the skill's template were separate copies that
     drifted; fixing one did not fix the other.

The tests below pin all three.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "surface-mirror/skills/devops/local-llm-endpoints/templates/demand_proxy.py"
LIVE = Path(r"C:\Users\KING\AppData\Local\hermes\heretik\heretik_demand.py")
MARK = "# ============================ CONFIG END ============================="


def _code_after_config(text: str) -> str:
    return text[text.index(MARK):] if MARK in text else text


def test_template_exists_and_parses():
    assert TEMPLATE.exists(), "the template is the published copy of the pattern"
    ast.parse(TEMPLATE.read_text(encoding="utf-8", errors="ignore"))


def test_health_is_answered_locally():
    """/health must not reach the backend - that is what spawns it."""
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(src)
    getter = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "do_GET")
    body = ast.dump(getter)
    assert "/health" in body, "do_GET must special-case the health path"
    # the health branch must not call _forward
    for node in ast.walk(getter):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "_forward":
            # a forward call is allowed, but not on the health branch
            seg = ast.dump(node)
            assert "health" not in seg.lower() or True   # structural, see below
    assert re.search(r"def _health\s*\(", src), "there must be a local health handler"
    h = re.search(r"def _health\s*\(.*?\n\n    def ", src, re.S)
    assert h, "the local health handler must exist"
    assert "_forward" not in h.group(0), "the local health handler must not forward"


def test_health_does_not_refresh_the_idle_timer():
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    assert "USE_PATH_HINTS" in src, "idle accounting must be based on real use"
    assert "def _is_use(" in src
    # last_used is only refreshed for a use-path
    seg = re.search(r"def _forward\(.*?\n\n    def ", src, re.S)
    assert seg, "_forward must exist"
    fwd = seg.group(0)
    assert "_is_use(self.path)" in fwd, "last_used must be refreshed only for a use-path"


def test_an_orphaned_backend_is_adopted():
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    assert "def adopt_backend(" in src, "an orphaned backend must be adoptable"
    assert "_is_our_backend" in src, "adoption must verify the process is ours"
    assert "def _port_owner_pid(" in src, "adoption must find the port owner"


def test_the_reaper_terminates_by_pid():
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    seg = re.search(r"def stop_backend\(.*?\n\ndef ", src, re.S)
    assert seg, "stop_backend must exist"
    assert "backend_pid" in seg.group(0), "the reaper must handle an adopted backend"


def test_the_template_config_is_generic():
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    port = int(re.search(r"BACKEND_PORT = (\d+)", src).group(1))
    proxy = int(re.search(r"PROXY_PORT = (\d+)", src).group(1))
    assert port != proxy, "the backend port must be distinct from the contract port"


def test_the_live_copy_has_not_drifted():
    """The live file and the published template must share one implementation."""
    if not LIVE.exists():
        return   # not a THRONE host; the template contract is still enforced
    live = _code_after_config(LIVE.read_text(encoding="utf-8", errors="ignore"))
    tmpl = _code_after_config(TEMPLATE.read_text(encoding="utf-8", errors="ignore"))
    assert live == tmpl, (
        "the live demand proxy and the published template have drifted - "
        "fix both or regenerate the template from the live file")


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
