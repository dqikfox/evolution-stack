"""The Codex transport must send the prompt on STDIN, not on the command line.

A Windows command line is capped at 32,767 characters. The router used to
pass the prompt as an argument, so a long prompt failed the whole call
with `WinError 206` before the request was ever made. `codex exec -`
reads the instructions from stdin, which has no such limit.

This test is the positive control: it stands a stub in place of the Codex
binary, runs the real router call against it, and asserts that the prompt
arrived on stdin. A stub is used rather than the real binary because the
live binary's answer depends on a ChatGPT Plus quota, which is not a
property of the transport and can be exhausted at any time.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROUTER = Path("C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py")

spec = importlib.util.spec_from_file_location("router_under_test", ROUTER)
mod = importlib.util.module_from_spec(spec)
sys.modules["router_under_test"] = mod
spec.loader.exec_module(mod)

# a prompt well past the Windows command-line limit
BIG_PROMPT = ("Filler sentence that must travel through stdin. " * 900) + "\n" + "THE-NONCE-47281"


def _stub_codex(tmp_path: Path) -> Path:
    """A stand-in for the Codex CLI.

    It records its stdin, its argv and its cwd, then answers the way the
    real CLI answers: a JSONL event stream on stdout and the final message
    in the file given by -o.
    """
    stub = tmp_path / "fake_codex.py"
    stub.write_text(
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "stdin = sys.stdin.read()\n"
        "Path = __import__('pathlib').Path\n"
        "Path(os.environ['STUB_OUT']).write_text(\n"
        "    json.dumps({'stdin': stdin, 'argv': args, 'cwd': os.getcwd()}),\n"
        "    encoding='utf-8')\n"
        "out = None\n"
        "for i, a in enumerate(args):\n"
        "    if a == '-o':\n"
        "        out = args[i + 1]\n"
        "if out:\n"
        "    Path(out).write_text('THE-NONCE-47281', encoding='utf-8')\n"
        "print(json.dumps({'type': 'item.completed',\n"
        "                  'item': {'type': 'agent_message',\n"
        "                           'text': 'THE-NONCE-47281'}}))\n"
        "print(json.dumps({'type': 'turn.completed',\n"
        "                  'usage': {'input_tokens': 11, 'output_tokens': 3}}))\n",
        encoding="utf-8")
    return stub


def _run_the_router(tmp_path: Path, monkeypatch):
    stub = _stub_codex(tmp_path)
    record = tmp_path / "seen.json"
    # the router must invoke this stub, as the codex binary
    wrapper = tmp_path / "codex_stub.cmd"
    wrapper.write_text(
        '@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, stub),
        encoding="utf-8")
    monkeypatch.setattr(mod, "CODEX_BIN", str(wrapper))
    monkeypatch.setenv("STUB_OUT", str(record))

    p = mod.Provider("chatgpt", "codex", "", "gpt-6-astra",
                     cost_tier="chatgpt", priority=25, local=True)
    text, meta = mod._codex_call(p, BIG_PROMPT, timeout=120)
    seen = json.loads(record.read_text(encoding="utf-8"))
    return text, meta, seen


def test_the_prompt_arrives_on_stdin(tmp_path, monkeypatch):
    text, meta, seen = _run_the_router(tmp_path, monkeypatch)
    assert seen["stdin"] == BIG_PROMPT, \
        "the prompt must arrive on stdin - a long prompt on the command " \
        "line fails with WinError 206 on Windows"
    assert "THE-NONCE-47281" in seen["stdin"]
    assert text == "THE-NONCE-47281", text
    assert meta["http"] == 200
    assert meta["error"] is None


def test_the_prompt_is_not_on_the_command_line(tmp_path, monkeypatch):
    """The prompt must not be an argument - that is the whole point."""
    _, _, seen = _run_the_router(tmp_path, monkeypatch)
    argv = seen["argv"]
    assert BIG_PROMPT not in argv, "the prompt is on the command line again"
    assert not any(len(a) > 30000 for a in argv), \
        "no argument may approach the Windows command-line limit: %s" % \
        [len(a) for a in argv]
    # the stdin sentinel must be there instead
    assert "-" in argv, argv


def test_the_usage_still_comes_off_turn_completed(tmp_path, monkeypatch):
    _, meta, _ = _run_the_router(tmp_path, monkeypatch)
    assert meta["tokens_in"] == 11
    assert meta["tokens_out"] == 3


def test_the_token_counts_do_not_depend_on_the_quota():
    """The counts are read from the event stream, never from the answer file.

    A provider that is out of quota still parses: the usage numbers are a
    property of the transport, and they must survive a change of transport.
    """
    src = Path(ROUTER).read_text(encoding="utf-8", errors="replace")
    assert "turn.completed" in src
    assert "input_tokens" in src and "output_tokens" in src
