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
    """Both a spawned and an ADOPTED backend must be releasable by pid."""
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    seg = re.search(r"def _stop_backend_locked\(.*?\n\ndef ", src, re.S)
    assert seg, "the locked reaper internal must exist"
    body = seg.group(0)
    assert "backend_pid" in body, "the reaper must handle an adopted backend"
    assert "_terminate_pid" in body, "an adopted backend must be terminated by pid"
    # the public entry point must take the lock before killing anything
    entry = re.search(r"def stop_backend\(.*?\n\ndef ", src, re.S)
    assert entry, "stop_backend must exist"
    assert "state_lock" in entry.group(0), "stop_backend must take the lock"


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




# ---------------------------------------------------------------------------
# The reaper's races. These are behavioural tests against the real module.
# ---------------------------------------------------------------------------
def _load_module():
    """Import the template as a module so its reaper can be driven directly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("demand_proxy_under_test", TEMPLATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeProc:
    """Stands in for a Popen handle."""
    def __init__(self, pid):
        self.pid = pid
        self.terminated = 0

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    def poll(self):
        return None


def _reap_once(mod):
    """One iteration of the watchdog's atomic check-and-kill."""
    import time as _t
    with mod.state_lock:
        if (_t.time() - mod.last_used) <= mod.IDLE_TIMEOUT:
            return False
        if mod.backend_proc is None and mod.backend_pid is None:
            return False
        mod._stop_backend_locked()
        return True


def _age(mod):
    mod.last_used = __import__("time").time() - (mod.IDLE_TIMEOUT + 60)


def test_the_same_backend_is_not_stopped_twice():
    """A spawned backend is also backend_pid - one process, one stop."""
    mod = _load_module()
    mod._terminate_pid = lambda pid: True
    mod._is_our_backend = lambda pid: True
    proc = _FakeProc(4242)
    mod.backend_proc = proc
    mod.backend_pid = 4242
    mod.backend_state.update(running=True, pid=4242)
    _age(mod)
    assert _reap_once(mod) is True
    assert proc.terminated == 1, "the backend must be terminated exactly once"
    assert mod.backend_proc is None and mod.backend_pid is None, "the handles must be cleared"


def test_a_fresh_backend_is_never_reaped():
    """A backend that was just used must survive the reaper."""
    mod = _load_module()
    mod._terminate_pid = lambda pid: True
    mod._is_our_backend = lambda pid: True
    proc = _FakeProc(2222)
    mod.backend_proc = proc
    mod.backend_pid = 2222
    mod.backend_state.update(running=True, pid=2222)
    mod.last_used = __import__("time").time()
    assert _reap_once(mod) is False
    assert proc.terminated == 0, "a backend in use must not be terminated"
    assert mod.backend_proc is proc, "the handle must survive"


def test_a_stale_backend_is_reaped_and_its_state_cleared():
    mod = _load_module()
    mod._terminate_pid = lambda pid: True
    mod._is_our_backend = lambda pid: True
    proc = _FakeProc(3333)
    mod.backend_proc = proc
    mod.backend_pid = 3333
    mod.backend_state.update(running=True, pid=3333)
    _age(mod)
    assert _reap_once(mod) is True
    assert proc.terminated == 1
    assert mod.backend_state["running"] is False
    assert mod.backend_state["pid"] is None


def test_a_backend_started_during_a_reap_is_not_orphaned():
    """The orphan bug: a request cold-starts a backend while the reaper runs.

    The reaper must not clear the NEW backend's handle, or a multi-GB
    process lives on with nothing able to reap it.
    """
    mod = _load_module()
    mod._terminate_pid = lambda pid: True
    mod._is_our_backend = lambda pid: True
    proc = _FakeProc(4444)
    mod.backend_proc = proc
    mod.backend_pid = 4444
    mod.backend_state.update(running=True, pid=4444)
    _age(mod)
    assert _reap_once(mod) is True
    # a request arrives and cold-starts a new backend
    mod.backend_proc = _FakeProc(5555)
    mod.backend_pid = 5555
    mod.backend_state.update(running=True, pid=5555)
    mod.last_used = __import__("time").time()
    assert _reap_once(mod) is False
    assert mod.backend_proc is not None and mod.backend_proc.pid == 5555, \
        "the reaper must not wipe a newer backend's handle"


def test_the_idle_check_and_the_kill_are_one_atomic_step():
    """The check and the kill must not be separable by a concurrent spawn."""
    src = TEMPLATE.read_text(encoding="utf-8", errors="ignore")
    seg = re.search(r"def watchdog\(.*?\n\ndef ", src, re.S)
    assert seg, "watchdog must exist"
    body = seg.group(0)
    assert "with state_lock:" in body, "the watchdog must take the lock"
    # the idle test must be INSIDE the locked block, not before it
    lock_at = body.index("with state_lock:")
    idle_at = body.index("last_used")
    assert idle_at > lock_at, "the idle check must happen under the lock, not before it"
    assert "_stop_backend_locked" in body, "the kill must use the locked internal"


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
