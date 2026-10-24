#!/usr/bin/env python3
"""
Post-training sanity probe for a model imported into Ollama.

Run after stage 6 of `throne-model-training` to verify the LoRA actually
took. The script sends a domain-specific prompt and checks whether the
response shows THRONE-aware behavior — uses project names, operator voice,
and concrete commands — versus generic LLM-help-desk tone.

USAGE:
  python E:/ultron-training/scripts/probe_trained_model.py \
    --model qikfox/starscream-throne-7b:latest \
    --timeout 60
"""

import argparse, json, subprocess, sys, time

THRONE_PROBES = [
    {
        "prompt": "List three services I might run on a Windows machine called THRONE.",
        "expected_signals": ["Ollama", "Tailnet", "ssh", "ADBHoney", "Tailscale", "Hermes"],
        "anti_signals": ["I'm sorry, I cannot", "as an AI language model"],
    },
    {
        "prompt": "My Ollama is using 23 GB of VRAM and the GPU is at 95%. What do I check first?",
        "expected_signals": ["context", "loaded models", "kv cache", "parallel", "num_ctx"],
        "anti_signals": ["restart your computer", "reinstall Windows"],
    },
    {
        "prompt": "Show me how to start the Watchdog cron job on THRONE.",
        "expected_signals": ["SchTasks", "schtasks", "PowerShell", "scheduled task"],
        "anti_signals": ["I don't have access to your machine"],
    },
]

def query_ollama(model: str, prompt: str, timeout: int) -> str:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 200, "temperature": 0.35},
    })
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Invoke-WebRequest http://localhost:11434/api/generate -Method POST -ContentType 'application/json' -Body '{body.replace(chr(39), chr(39)+chr(39))}' -UseBasicParsing -TimeoutSec {timeout}).Content"],
        capture_output=True, text=True, timeout=timeout + 10,
    )
    if r.returncode != 0:
        return f"ERR: {r.stderr[:200]}"
    try:
        return json.loads(r.stdout).get("response", "").strip()
    except (json.JSONDecodeError, KeyError):
        return f"PARSE ERR: {r.stdout[:200]}"


def score(response: str, expected: list, anti: list) -> tuple[int, int, list[str]]:
    """Return (expected_hits, anti_hits, details)."""
    lo = response.lower()
    hits = [s for s in expected if s.lower() in lo]
    bad = [s for s in anti if s.lower() in lo]
    return len(hits), len(bad), hits


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()

    print(f"=== probe {args.model} ===\n")
    total_expected = 0
    total_anti = 0
    failures = []
    for i, probe in enumerate(THRONE_PROBES, 1):
        print(f"[probe {i}] {probe['prompt']}")
        t0 = time.time()
        resp = query_ollama(args.model, probe["prompt"], args.timeout)
        dt = time.time() - t0
        e, a, hits = score(resp, probe["expected_signals"], probe["anti_signals"])
        total_expected += e
        total_anti += a
        status = "PASS" if e >= 2 and a == 0 else "FAIL"
        print(f"  → {dt:.1f}s | expected_hits={e} anti_hits={a} | hits={hits}")
        print(f"  response: {resp[:200]}{'...' if len(resp)>200 else ''}")
        print(f"  verdict: {status}\n")
        if status == "FAIL":
            failures.append((i, probe["prompt"][:60]))

    print(f"=== summary ===")
    print(f"expected_hits: {total_expected}")
    print(f"anti_hits:     {total_anti}")
    print(f"failures:      {len(failures)}/{len(THRONE_PROBES)}")
    if failures:
        print("Failed probes:")
        for i, q in failures:
            print(f"  [{i}] {q}")
        sys.exit(1)
    print("ALL PROBES PASSED — model is THRONE-aware.")

if __name__ == "__main__":
    main()
