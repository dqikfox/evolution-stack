"""Can ChatGPT do actual WORK through the router, not just echo a nonce?

The nonce test proves the transport. This proves the capability: ChatGPT is
asked to write real code against a real spec, in a scratch directory, and the
result is judged on whether it compiles and behaves - not on whether it
looked plausible.

    python probe_chatgpt_work.py
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

ROUTER = r"C:\Users\KING\AppData\Local\hermes\scripts\provider_router.py"
ENV = dict(os.environ)
ENV.pop("PYTHONPATH", None)
WORK = pathlib.Path(r"C:\Users\KING\AppData\Local\hermes\cache\scratch\chatgpt_work")
WORK.mkdir(parents=True, exist_ok=True)

SPEC = '''Write a Python module named fib.py in the current directory.

It must define exactly this function:

    def fib(n: int) -> list[int]:
        """Return the first n Fibonacci numbers (0, 1, 1, 2, 3, 5, ...)."""

Requirements:
- fib(0) returns an empty list
- fib(1) returns [0]
- fib(7) returns [0, 1, 1, 2, 3, 5, 8]
- n below 0 raises ValueError
- n must be an int; a non-int raises TypeError

Write ONLY the module. No explanation, no tests, no prose.'''


def load():
    spec = importlib.util.spec_from_file_location("pr_work_probe", ROUTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    pr = load()
    p = pr.Provider("chatgpt", "codex", "", "gpt-6-astra",
                    cost_tier="chatgpt", priority=25, local=True)

    print("asking ChatGPT for real code...")
    text, meta = pr.call(p, SPEC, max_tokens=2000, timeout=600)
    print("   provider: %s   model: %s   elapsed: %ss" % (
        meta.get("provider"), meta.get("model"), meta.get("elapsed")))

    # write whatever came back, minus any markdown fence
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    target = WORK / "fib.py"
    target.write_text(body, encoding="utf-8")
    print("   wrote %d bytes to %s" % (target.stat().st_size, target))

    # now judge it by BEHAVIOUR, not by appearance
    checks = []
    cases = [(0, []), (1, [0]), (7, [0, 1, 1, 2, 3, 5, 8]), (10, [0, 1, 1, 2, 3, 5, 8, 13, 21, 34])]
    script = "import fib, json, sys\n"
    for n, want in cases:
        script += "assert fib.fib(%d) == %r, 'fib(%d) wrong: %%r' %% (fib.fib(%d),)\n" % (n, want, n, n)
    script += ("try:\n    fib.fib(-1)\n    print('NEG: no raise')\n"
               "except ValueError:\n    print('NEG: ok')\n"
               "except Exception as e:\n    print('NEG: wrong exc ' + type(e).__name__)\n")
    script += ("try:\n    fib.fib('x')\n    print('TYPE: no raise')\n"
               "except TypeError:\n    print('TYPE: ok')\n"
               "except Exception as e:\n    print('TYPE: wrong exc ' + type(e).__name__)\n")
    script += "print('ALL CASES PASS')\n"

    test_file = WORK / "check_fib.py"
    test_file.write_text(script, encoding="utf-8")
    r = subprocess.run([sys.executable, str(test_file)], capture_output=True, text=True,
                       timeout=120, env=ENV, cwd=str(WORK), encoding="utf-8", errors="replace")
    output = (r.stdout or "") + (r.stderr or "")
    print("\n   the behavioural check (rc=%s):" % r.returncode)
    for l in output.splitlines():
        if l.strip():
            print("      %s" % l[:120])

    passed = "ALL CASES PASS" in output and "NEG: ok" in output and "TYPE: ok" in output
    print("\n   ChatGPT's code passes the behavioural check: %s" % passed)

    result = {"provider": meta.get("provider"), "model": meta.get("model"),
              "elapsed": meta.get("elapsed"), "passed": bool(passed),
              "output": output[-500:], "bytes": target.stat().st_size,
              "code": body}
    out = pathlib.Path(r"C:\Users\KING\AppData\Local\hermes\state\chatgpt_work_proof.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("   written to %s" % out)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
