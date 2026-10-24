#!/usr/bin/env bash
# THRONE health runner — uses only scripts known to execute cleanly under Hermes shell.
set -u
OUT="${LOCALAPPDATA:-/c/Users/KING/AppData/Local}/hermes/cron/output"
SCR="${LOCALAPPDATA:-/c/Users/KING/AppData/Local}/hermes/scripts"
mkdir -p "$OUT"
LOCK="$OUT/health.lock"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# simple lock to prevent heal storms
if [ -f "$LOCK" ]; then
  age=$(( $(date +%s) - $(date -r "$LOCK" +%s) ))
  if [ "$age" -lt 120 ]; then
    echo "{\"ts\":\"$TS\",\"status\":\"SKIP\",\"reason\":\"lock_held_age_${age}s\"}"
    exit 0
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# Probe via tiny inline python (known-good pattern)
PROBE=$(python - <<'PY'
import json, socket, urllib.request
from datetime import datetime, timezone

def port(p):
    try:
        socket.create_connection(("127.0.0.1", p), 0.4).close(); return True
    except OSError:
        return False

def http(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200, r.read(100).decode("utf-8","ignore")
    except Exception as e:
        return False, type(e).__name__

svc = {k: port(p) for k,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()}
n_ok, n_b = http("http://127.0.0.1:8650/health")
t_ok, t_b = http("http://127.0.0.1:8705/health") if svc["tesseract"] else (False, "down")
print(json.dumps({"services": svc, "nexus_ok": n_ok, "tess_ok": t_ok, "nexus_snip": n_b, "tess_snip": t_b}))
PY
)

echo "$PROBE" > "$OUT/health_probe.json"
N_OK=$(python -c "import json,sys; print(json.load(open(r'$OUT/health_probe.json'))['nexus_ok'])" 2>/dev/null || echo False)
T_OK=$(python -c "import json,sys; print(json.load(open(r'$OUT/health_probe.json'))['tess_ok'])" 2>/dev/null || echo False)

HEALS=""
if [ "$N_OK" != "True" ]; then
  python "$SCR/restart_nexus.py" > "$OUT/last_nexus_heal.txt" 2>&1 && HEALS="${HEALS}nexus:ok;" || HEALS="${HEALS}nexus:fail;"
fi
if [ "$T_OK" != "True" ]; then
  python "$SCR/start_tesseract.py" > "$OUT/last_tess_heal.txt" 2>&1 && HEALS="${HEALS}tess:ok;" || HEALS="${HEALS}tess:fail;"
fi

# Re-probe
PROBE2=$(python - <<'PY'
import json, socket, urllib.request

def port(p):
    try:
        socket.create_connection(("127.0.0.1", p), 0.4).close(); return True
    except OSError:
        return False

def http(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False

print(json.dumps({
  "services": {k: port(p) for k,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()},
  "nexus_ok": http("http://127.0.0.1:8650/health"),
  "tess_ok": http("http://127.0.0.1:8705/health"),
}))
PY
)

python - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone
out = Path(r"$OUT")
p1 = json.loads(Path(out/"health_probe.json").read_text(encoding="utf-8"))
p2 = json.loads('''$PROBE2''')
heals = [x for x in "$HEALS".split(";") if x]
alerts=[]
notices=[]
if not p2["services"].get("ollama"): alerts.append("ollama:DOWN")
if not p2["services"].get("openclaw"): alerts.append("openclaw:DOWN")
if not p2.get("nexus_ok"): alerts.append("nexus:UNHEALTHY")
if not p2.get("tess_ok"): notices.append("tesseract:UNHEALTHY")
notices += heals
state={
  "ts": datetime.now(timezone.utc).isoformat(),
  "status": "ALERT" if alerts else ("DEGRADED" if notices else "OK"),
  "services": p2["services"],
  "http": {"nexus": p2.get("nexus_ok"), "tesseract": p2.get("tess_ok")},
  "heals": heals,
  "alerts": alerts,
  "notices": notices,
  "pre": p1,
}
(out/"health_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
with (out/"health.log").open("a", encoding="utf-8") as f:
    f.write(f"[{state['ts']}] {state['status']} {state['services']} heals={heals}\n")
print(json.dumps(state, separators=(",", ":")))
raise SystemExit(1 if alerts else 0)
PY
