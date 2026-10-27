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

# ── Probe ────────────────────────────────────────────────────────────────
#
# The timeout matters more than it looks. NEXUS CORE's /health walks its
# components - the database, the Ollama roster, the embedding models -
# and that walk can outlast a short probe. A service that is BUSY then
# looks exactly like a service that is DEAD, and a healer that cannot
# tell the difference restarts healthy work.
#
# That is not hypothetical. On 2026-10-27 this job, running every five
# minutes with a 5-second probe, restarted NEXUS CORE while a vector
# reindex was holding its database. The restart did not fix the stall -
# it destroyed the reindex's work and left the service unable to come
# back at all, because the startup path could not get the database
# either. The knowledge base was offline for the better part of an hour.
#
# So NEXUS gets a timeout that matches its own work, and no service is
# restarted on a single probe - see the confirmation step below.
PROBE=$(python - <<'PY'
import json, socket, urllib.request

# NEXUS's health endpoint does real work, so it needs a real budget.
# Everything else answers in milliseconds.
TIMEOUTS = {"nexus": 30.0, "tesseract": 10.0}

def port(p):
    try:
        socket.create_connection(("127.0.0.1", p), 0.4).close(); return True
    except OSError:
        return False

def http(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200, r.read(100).decode("utf-8", "ignore")
    except Exception as e:
        return False, type(e).__name__

svc = {k: port(p) for k,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()}
n_ok, n_b = http("http://127.0.0.1:8650/health", TIMEOUTS["nexus"])
t_ok, t_b = http("http://127.0.0.1:8705/health", TIMEOUTS["tesseract"]) if svc["tesseract"] else (False, "down")
print(json.dumps({"services": svc, "nexus_ok": n_ok, "nexus_snip": n_b, "tess_ok": t_ok, "tess_snip": t_b}))
PY
)

echo "$PROBE" > "$OUT/health_probe.json"

# ── Confirm, then heal ───────────────────────────────────────────────────
#
# A service that fails ONE probe may be busy, not dead. Probe a second
# time before touching anything: a service that answers the confirmation
# was never down, and restarting it would destroy whatever it was doing.
# Only a service that fails twice is restarted.
#
# This is the same rule the estate watchdog follows. Two healers, one
# rule: a restart is a last resort, not the first response to a
# timeout.
CONFIRM=$(python - "$OUT" "$SCR" <<'PY'
import json, socket, subprocess, sys, time, urllib.request
from pathlib import Path

OUT = Path(sys.argv[1])
SCR = Path(sys.argv[2])
TIMEOUTS = {"nexus": 30.0, "tesseract": 10.0}

def port(p):
    try:
        socket.create_connection(("127.0.0.1", p), 0.4).close(); return True
    except OSError:
        return False

def http(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def probe():
    svc = {k: port(p) for k,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()}
    return {
        "services": svc,
        "nexus_ok": http("http://127.0.0.1:8650/health", TIMEOUTS["nexus"]),
        "tess_ok": http("http://127.0.0.1:8705/health", TIMEOUTS["tesseract"]) if svc["tesseract"] else False,
    }

first = json.loads((OUT / "health_probe.json").read_text(encoding="utf-8"))
heals = []
notices = []

if first.get("nexus_ok") and first.get("tess_ok"):
    # Everything answered the first time. Nothing to confirm, nothing to
    # heal - the common case, and it stays fast.
    print(json.dumps({"heals": [], "notices": [], "confirmed": False}))
    raise SystemExit(0)

time.sleep(20)
second = probe()

if not second["nexus_ok"]:
    with open(OUT / "last_nexus_heal.txt", "w", encoding="utf-8") as fh:
        rc = subprocess.call([sys.executable, str(SCR / "restart_nexus.py")],
                             stdout=fh, stderr=subprocess.STDOUT)
    heals.append("nexus:ok;" if rc == 0 else "nexus:fail;")
elif not first.get("nexus_ok"):
    # It failed the first probe and answered the second. That is a BUSY
    # service, not a dead one, and it was not restarted. Say so - but
    # only when the first probe actually failed, otherwise this notice
    # fires on every healthy run and drowns the real ones.
    notices.append("nexus:busy-not-restarted")

if not second["tess_ok"]:
    with open(OUT / "last_tess_heal.txt", "w", encoding="utf-8") as fh:
        rc = subprocess.call([sys.executable, str(SCR / "start_tesseract.py")],
                             stdout=fh, stderr=subprocess.STDOUT)
    heals.append("tess:ok;" if rc == 0 else "tess:fail;")
elif not first.get("tess_ok"):
    notices.append("tesseract:busy-not-restarted")

print(json.dumps({"heals": heals, "notices": notices, "confirmed": True}))
PY
)

# Re-probe for the final state. Same timeouts as the first probe: the
# point of the second probe is to report the truth, and a short timeout
# here would report "unhealthy" for a service that is merely busy.
PROBE2=$(python - <<'PY'
import json, socket, urllib.request

TIMEOUTS = {"nexus": 30.0, "tesseract": 10.0}

def port(p):
    try:
        socket.create_connection(("127.0.0.1", p), 0.4).close(); return True
    except OSError:
        return False

def http(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

print(json.dumps({
  "services": {k: port(p) for k,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()},
  "nexus_ok": http("http://127.0.0.1:8650/health", TIMEOUTS["nexus"]),
  "tess_ok": http("http://127.0.0.1:8705/health", TIMEOUTS["tesseract"]),
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
try:
    c = json.loads('''$CONFIRM''') or {"heals": [], "notices": []}
except Exception:
    c = {"heals": [], "notices": []}
heals = [x for x in c.get("heals", []) if x]
alerts=[]
notices=list(c.get("notices", []))
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
