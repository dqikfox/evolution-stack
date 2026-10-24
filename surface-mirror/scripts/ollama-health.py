#!/usr/bin/env python
"""
ollama-health.py - Cron-friendly health probe of local Ollama + host summary.

Exit code means "did the probe do its job", not "is the host happy":
    0  the probe measured successfully (the host may be busy - that is data)
    2  the probe could not do its job (Ollama unreachable, deps missing)

Why: a busy host is a HEALTH observation, not a probe failure. Reporting it
through the job-failure channel meant a loaded machine produced a failed job
every 5 minutes, which buries the failures that matter. The load state is
recorded in the sample and judged by host_load_watchdog.py, which alerts on
a TRANSITION (sustained pressure), not on every sample.

Use --strict to get the old behaviour (exit 1 when degraded) for manual or
CI use where a non-zero exit is what you want.
"""
import sys, json, time, argparse
from pathlib import Path

try:
    import httpx, psutil
except ImportError:
    print("httpx + psutil required", file=sys.stderr); sys.exit(2)

OLLAMA = "http://127.0.0.1:11434"
LOG = Path(r"C:\Users\KING\AppData\Local\hermes\health\ollama-beat.jsonl")
LOG.parent.mkdir(parents=True, exist_ok=True)


def probe() -> dict:
    out = {"ts": time.time(), "ollama_http": False, "ollama_models": 0, "cpu": 0, "ram_pct": 0, "gpu_temp": None}
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=2.0)
        out["ollama_http"] = r.status_code == 200
        if out["ollama_http"]:
            out["ollama_models"] = len(r.json().get("models", []))
    except Exception:
        pass
    out["cpu"] = psutil.cpu_percent(interval=0.2)
    out["ram_pct"] = psutil.virtual_memory().percent
    try:
        import subprocess
        s = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3)
        out["gpu_temp"] = int(s.stdout.strip().splitlines()[0]) if s.stdout.strip() else None
    except Exception:
        pass
    return out


def _cpu_sustained(threshold: float, samples: int = 3, gap: float = 0.5) -> bool:
    """True only if CPU is above threshold on consecutive samples.

    A single 100% sample is normal on a 64-core box under load; failing the
    cron on it produced false streaks and noisy alerts every 5 minutes.
    """
    hits = 0
    for _ in range(samples):
        v = psutil.cpu_percent(interval=gap)
        hits = hits + 1 if v > threshold else 0
        if hits >= 2:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--cpu-threshold", type=float, default=99.5)
    ap.add_argument("--ram-threshold", type=float, default=98.0)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when the host is degraded (manual/CI use)")
    args = ap.parse_args()

    p = probe()
    # Degraded only when the pressure is sustained, not a single spike.
    cpu_hot = _cpu_sustained(args.cpu_threshold)
    reasons = []
    if cpu_hot:
        reasons.append(f"cpu_sustained>{args.cpu_threshold:g}")
    if p["ram_pct"] > args.ram_threshold:
        reasons.append(f"ram>{args.ram_threshold:g}")
    p["degraded"] = bool(reasons)
    p["reasons"] = reasons

    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(p) + "\n")

    if not args.quiet:
        print(json.dumps(p, indent=2))

    if not p["ollama_http"]:
        print("OLLAMA DOWN", file=sys.stderr)
        return 2
    if p["degraded"]:
        print(f"DEGRADED cpu={p['cpu']} ram={p['ram_pct']} ({', '.join(reasons)})",
              file=sys.stderr)
        if args.strict:
            return 1
    # The probe worked. Load is recorded, not failed.
    return 0


if __name__ == "__main__":
    sys.exit(main())