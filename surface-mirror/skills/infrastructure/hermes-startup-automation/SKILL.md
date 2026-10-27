---
name: hermes-startup-automation
description: Verify and repair Hermes startup and cron on THRONE.
version: 1.0.0
author: Jamie Hitch (dqikfox), Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [startup, cron, scheduled-tasks, watchdog, gateway, windows, self-healing]
    related_skills: [throne-sysadmin-network, hermes-agent, constrained-ml]
---

# Startup and automation verification on THRONE

Use this skill when the user asks whether Hermes' automation actually RUNS -
not whether it is configured. The gap between "configured" and "running" is
where THRONE's automation has actually failed three times.

## When to Use

Use this skill when the user asks whether Hermes' automation is actually
running, or reports that a scheduled job, the cron ticker, the gateway, or
the evolution loop has stopped. Also use it when:

- a Scheduled Task shows no `NextRunTime`, or shows success while its service
  is dead
- a cron job fails with a context-overflow error
- the estate watchdog reports a service it cannot heal
- a new service must be wired into startup AND given independent recovery

Do not use it for authoring a new skill, tuning a model, or debugging a
provider's authentication - those are separate concerns.

## The three failure modes this skill exists for

1. **An expired Scheduled Task trigger.** A finite trigger duration that ended
   leaves `NextRunTime` empty and nothing fires, silently, for weeks.
2. **A detaching task action.** A task that launches a VBS or a background
   script reports `LastTaskResult: 0` while the real process died. The task
   looks healthy and the service is dead.
3. **A context overflow in a cron job.** One oversized tool result can consume
   the whole model window, so the job fails on every run with no obvious
   cause.

## Procedure

### 1. Prove the gateway is alive, not merely scheduled

```bash
curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8642/health
```

`/health` answers only when the gateway is genuinely up. Then confirm the
CRON TICKER is fresh - the ticker heartbeat file is written by the gateway
process, so a stale heartbeat means the gateway died even if the task says
"Ready":

```bash
python -c "import os,time; print(round(time.time()-os.path.getmtime(r'C:\Users\KING\AppData\Local\hermes\cron\ticker_heartbeat'),1))"
```

A healthy estate shows a heartbeat age under about 60 seconds.

### 2. Audit the Scheduled Tasks

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like 'THRONE_*' -or $_.TaskName -like 'Hermes_*' } |
  ForEach-Object { $i = Get-ScheduledTaskInfo $_; '{0} state={1} next={2} last={3}' -f $_.TaskName, $_.State, $i.NextRunTime, $i.LastTaskResult }
```

`NextRunTime` empty on a repeating task is the expired-trigger signature.
`State=Ready` with a `LastTaskResult` of 0 is NOT proof of health when the
action detaches.

### 3. Fix an expired trigger

Do not use `[TimeSpan]::MaxValue` - Task Scheduler rejects it as out of range
for the task XML. Use a long finite duration:

```powershell
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
```

3650 days is effectively non-expiring and is inside the range the task XML
accepts.

### 4. Make startup idempotent and foreground

Never let a Scheduled Task own a detaching action. Write a launcher that
exits 0 when the service is already healthy, and otherwise starts the real
process IN THE FOREGROUND so `RestartOnFailure` applies to it:

```cmd
@echo off
"C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" ^
  "C:\Users\KING\AppData\Local\hermes\scripts\gateway_supervisor.py"
```

Use the ABSOLUTE interpreter path. A bare `python` does not resolve in a
minimal environment and the task fails with no useful error.

The supervisor pattern: probe the health endpoint, exit 0 if it answers,
otherwise exec the service and keep it attached.

### 5. Register the service for independent recovery

The estate watchdog (`hermes/scripts/estate_watchdog.py`) reads
`E:\ultron-memory\infra\SERVICES.json` and restarts anything in it that is
down. The gateway is CRITICAL: it owns the cron ticker, so when it dies every
scheduled automation on the host stops with it.

```json
{
  "name": "hermes-gateway",
  "port": 8642,
  "owner": "hermes",
  "status": "up",
  "start": { "type": "cmd", "path": "C:\\Users\\KING\\AppData\\Local\\hermes\\scripts\\start_hermes_gateway.cmd" },
  "health": "http://127.0.0.1:8642/health",
  "critical": true
}
```

Do NOT give a service a start path unless it should be restarted
automatically. An entry with NO start path is reported by the watchdog and
never healed.

But "has a start path" and "should be auto-healed" are DIFFERENT questions.
A service can have a working launcher that a tool uses on demand while the
watchdog must still leave it alone - a GPU-heavy service that would starve
the agent's own model is the real case. The registry states the answer
explicitly:

```json
{
  "name": "comfyui",
  "port": 8188,
  "status": "optional",
  "start": {
    "type": "cmd",
    "path": "C:\\Users\\KING\\AppData\\Local\\hermes\\scripts\\start_comfyui.cmd",
    "heal": false
  },
  "health": "http://127.0.0.1:8188/system_stats"
}
```

Point the registry at a HOUSE launcher, not a vendor `.bat`. One launcher
per service, always - the vendor file can carry its own `pause` and its own
unconditional error hint, and neither belongs in an automated heal. The
house's `scripts/start_comfyui.cmd` starts the same interpreter with the
same arguments and returns.

`start.heal: false` is an explicit opt-out: the watchdog reports the service
and deliberately does not heal it, even though a launcher exists. Without
this flag, adding a start path silently turns an on-demand service into an
always-on one, which is how a 3.2GB VRAM parking spot starves a 17.5GB
agent model.

Watch for the evolution loop adding a start path to a service you deliberately
left operator-level. The loop reads "no start path" as a defect to fix. If a
service must stay unhealed, say so with `heal: false` and repeat the reason
in its `notes`, so the next cycle sees the decision and not just the field.

**The `heal: false` flag is only honoured if the FIELD says false.** The
notes can say "start.heal is false" while the field says `true` - and the
field is what the watchdog reads. On 2026-10-27 that mismatch made the
watchdog try to heal ComfyUI, and the failed heal then failed the whole
watchdog run, which failed the estate gate. When you change the policy,
change the field, then run the watchdog and read its line: "comfyui (:8188)
is marked heal: false - reported, deliberately not healed".

### 6. Prove the cron layer

```bash
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  -m hermes_cli.main cron doctor
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  -m hermes_cli.main cron list
```

Then FORCE one real run and read its output - configuration is not proof:

```bash
C:/Users/KING/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe \
  -m hermes_cli.main cron run <job_id>
```

The run's markdown lands in `cron\output\<job_id>\<timestamp>.md`.

A FORCED run proves the job works. It does NOT prove the automation runs by
itself. For that, read the execution history: a row whose `source` is
`builtin` was fired by the ticker, while `direct` means a human forced it.
The job's `last_dispatch` block also records `scheduled_at`,
`dispatched_at`, `lateness_seconds`, and `kind: on_time` — quote those when
asked whether the loop is genuinely autonomous.

The field names in `cron/jobs.json` are `next_run_at` and `last_run_at`, NOT
`next_run` / `last_run`; querying the wrong name returns `None` and reads
exactly like "this job is never scheduled again".

### 6a. Clear a degraded gateway

`gateway_state.json` reporting `degraded` means a platform failed to start.
The usual cause: a platform auto-enables merely because its credentials are
in the environment, then refuses to start because it needs configuration it
cannot have - Twilio SMS, for example, requires a public `SMS_WEBHOOK_URL`
that only exists in the Twilio console. That parks the whole gateway in
`degraded` even though every other platform is fine.

Disable it at the TOP-LEVEL `platforms` key, not under `gateway.platforms`:

```bash
hermes config set platforms.sms.enabled false
hermes gateway restart
```

After the restart, wait roughly a minute and re-read `gateway_state.json`:
the old process can briefly hold the port and a polling platform can raise
a transient conflict while the old instance drains.

**Platform errors in `gateway_state.json` are STALE until the next restart.**
A platform you just fixed keeps its `fatal` entry in the file. Check the
gateway log timestamps before treating it as a live fault.

### 7. Fix a context-overflow failure

The error is `Prompt used N of 65536 context tokens; no room to answer`. The
cause is almost always a read budget that can overflow the window in one
call. Set them through the sanctioned config path (config.yaml is protected -
a direct write is refused):

```bash
hermes config set file_read_max_chars 100000
hermes config set tool_output.max_lines 2000
hermes config set file.file_read_max_chars 100000
```

`file.context_file_max_chars` (150000) is separate and can stay.

## Pitfalls

- **`config.yaml` is protected.** `patch`/`write_file` on it is refused with
  "Refusing to write to Hermes config file". Always use `hermes config set`.
- **Clear `PYTHONPATH` for venv commands.** The ambient environment leaks
  another installation's packages and produces misleading import errors.
  Prefix with `PYTHONPATH=`.
- **The gateway Scheduled Task is CLI-owned.** `hermes_cli/gateway_windows.py`
  recreates its detaching VBS action, so permanently replacing the task XML
  creates an upgrade conflict. Leave that task alone and use the watchdog as
  the independent recovery layer.
- **A task reporting success is not a service being up.** Verify the health
  endpoint, always.
- **Watchdog `status: retired` entries are excluded** from the check, so the
  count it logs is lower than the number of entries in the registry.
- **Long commands time out.** Anything past about four minutes should run
  with `background=true` and be polled, not run inline.
- **A `None` from a state file is a wrong field name until proven
  otherwise.** Read the schema before concluding a job is unscheduled or a
  service is down. The field names and the traps around them are in
  `references/runtime-state-reading.md`.
- **The gateway process must be matched on the exact command line
  `hermes_cli.main gateway run`.** Matching only `*gateway*` or `Name like
  python*` returns zero because the real interpreter lives under
  `tools/python-.../python.exe`. The count is the sole gate for
  `gateway_process_unique`.
- **A PowerShell process count needs `@()`, and the query must exclude
  itself.** Two separate traps, both of which made the gateway check
  unsatisfiable. First, a PowerShell process running the query contains the
  search string in its OWN CommandLine, so a naive count always reports 2 -
  the gateway plus the checker. Filter on `Name -like 'python*'`. Second, in
  Windows PowerShell 5.1 a pipeline matching exactly ONE process yields a
  single object, and a single CimInstance has no `.Count` property - so
  `$p.Count` comes back EMPTY and a healthy single gateway reads as zero.
  Wrap the pipeline in `@(...)` to force an array. The house's own
  `scripts/hermes_remote.py` already uses this idiom; copy it.
- **One heartbeat sample is not a trend.** A single ticker-age reading can
  land anywhere in the cycle and look like a stall. Take several samples
  across a minute to establish the period before calling it stuck.
- **A restart is not a fault.** `hermes gateway restart` on Windows can
  briefly print "still accepting connections — new api_server may fail to
  bind". That is the old instance draining, not a failure. Confirm by
  re-reading `gateway_state.json` after it settles.
- **A busy service looks exactly like a dead one.** The watchdog must
  NOT heal a service on the FIRST failed probe. A service that is doing
  real work - NEXUS CORE running a vector reindex, a service rebuilding
  its index - can fail a health probe and be perfectly healthy. On
  2026-10-27 the watchdog healed NEXUS mid-reindex and destroyed the
  work in progress. A service now has to fail TWICE, with a
  confirmation probe in between; a service that answers the second
  probe was never down. Also give the probe a per-service budget: a
  health endpoint that walks its components (NEXUS's `/health` does)
  needs longer than the 6s default, and probing a busy service with a
  timeout shorter than its own work is how a healthy service gets
  restarted.
- **A service that cannot START is a far worse failure than one that is
  slow.** If a service's startup path can die on a transient lock, one
  unlucky moment takes it offline permanently. Startup must degrade, not
  die: retry, then log and carry on, and let the health endpoint report
  the degraded component truthfully. A blocked synchronous call inside an
  async handler is the worst version of this - it blocks the event
  loop, so the health endpoint never answers AND every other request
  stalls behind it. Run blocking work with `asyncio.to_thread` and give
  it a timeout so a busy component is reported as BUSY rather than
  waited on forever.
- **Two processes must never write the same SQLite file.** NEXUS holds
  `data/chroma/chroma.sqlite3` open for its lifetime; a rebuild tool
  that drops and recreates the collection deadlocks against it - the
  reindex blocks on the server's connection while the server's reads
  block on the reindex's transaction. The rebuild tool must REFUSE to
  run while the server is listening. One writer at a time.
- **A rebuild and the server must not be able to meet, even by
  accident.** The service healer runs every five minutes, so "stop the
  server first" is not a plan - something will start it again. The
  rebuild drops a LOCK FILE and the ONE canonical start path checks it
  and refuses. Put the check in the launcher, not in the caller: the
  launcher is what every caller reaches.
- **A rebuild must be resumable, and must show where it is.** A rebuild
  that drops the collection and then dies loses everything it did. An
  UPSERT keyed on the note id is idempotent, so the default should be
  to resume and only drop with an explicit `--fresh`. Feed the work in
  chunks, each its own transaction, and flush every progress line - a
  run whose output goes through a pipe loses its progress when the pipe
  closes, which is how a working run looks dead.
- **A cmd launcher must not put a path inside an `if exist (...)`
  block.** A parenthesised block ends at the first unbalanced `)`, so a
  path inside the block's own parentheses terminates it early and cmd
  fails with "was unexpected at this time" - the whole launcher dies on
  a syntax error, not just the branch. Use `if not exist "..." goto
  :label`.
- **A healer that blocks is not a healer.** OpenClaw's tray app is an
  `.exe` that never exits, and `cmd /c` waits for it anyway - so the
  watchdog sat in that call for its whole 360-second launcher budget
  before it even started waiting for the port. The run took seven
  minutes, longer than the five-minute cycle it has to fit inside, so
  the recovery layer was effectively not running. Launch a GUI app
  DETACHED - no console, no inherited handles, no wait - and let the
  PORT POLL decide whether it came back. The launcher's own exit code
  is not evidence of anything.
- **A maintenance window for one service is not a maintenance window
  for the estate.** The rebuild lock belongs to NEXUS: it is NEXUS's
  vector index being rebuilt, and NEXUS is the service that would
  deadlock against the writer. Every other service is healable while
  the lock is held. Treating the lock as a blanket excuse meant the
  watchdog declined to heal openclaw - which was genuinely down, and
  stayed down, for the whole rebuild. Scope the lock to the service it
  protects.
- **A planned outage must not fail the job that reports it.** The
  five-minute health job exits 1 when a service is DOWN. While NEXUS
  was deliberately stopped for a rebuild it was DOWN, so the job failed
  every five minutes for the length of the rebuild - a six-failure
  streak, all of them the same non-fault. That is worse than a noisy
  alarm: a job that cries wolf every five minutes for an hour is a job
  everyone learns to ignore, and the next REAL failure gets ignored
  with it. Report DEGRADED with the reason, and exit 0.
- **The lock must be taken BEFORE the check it protects.** The lock
  stops the launcher from starting the server; the port check makes
  sure the server is not already running. Check-then-lock leaves a
  window in which the five-minute health job starts the server between
  the two, and the rebuild then contends with a server it believed was
  gone. And a sequence of rebuild passes must hold the lock across the
  WHOLE sequence: a twenty-second gap between passes is a window in
  which the server comes back onto a half-built index.
- **ONE owner per rebuild. Two rebuilds on one Chroma file segfault
  BOTH.** The symptom is a child that dies with 0xC0000005 (3221225477
  as an exit code, or 3 when the server refuses), and it looks exactly
  like a mysterious killer: the rebuild dies, the server dies, and
  neither leaves a useful message. The cause is that a second rebuild
  dropped the collection the first one was filling, and the server
  opened the same file while the writer held it. On this host the
  contention came from OTHER agents: ChatGPT, Claude and Grok were
  running on the same box, alongside a second Hermes session, and each
  of them started its own rebuild. A rebuild therefore needs a CLAIM
  that names an owner, not just a lock that says "something is
  running" - and the other agents have to be told, not left to guess.
- **A service that "did not answer" is often out of memory, not broken.**
  ComfyUI sat for 180 seconds and reported "did not answer
  /system_stats" - but it was not hung, it was STARVED. The RTX 3090
  has 24 GB; the agent's own model (starscream-64k, 64K context) is
  resident in Ollama and parks 17.5 GB of it, and llama.cpp parks
  most of what is left. About 2 GB free, and ComfyUI needs ~3.2 GB of
  CUDA context before loading anything. Measure the free memory
  BEFORE starting anything GPU-shaped, and release what is resident if
  it is short - the house already has scripts/mem_guard.py for this.
  And undo the release: a cold model costs a reload, so whatever
  takes the memory has to give it back. The diagnosis has to name the
  constraint, or the next person spends an hour reading a timeout
  that means "out of memory".
- **A destructive first step must be done ONCE PER CYCLE, not once per
  run.** A rebuild that drops the index and rebuilds from zero is
  right when the policy changed - but a run that gets killed then
  loses the cycle's work to the next run's drop, and the estate never
  finishes. A marker file records that the drop already happened; a
  later run RESUMES instead of dropping again, and the marker is
  cleared on completion so the next cycle starts clean.
- **"timeout /t" does not work on this host.** Git for Windows ships a
  GNU "timeout" in usr\bin, and that directory comes BEFORE
  C:\Windows\System32 on the PATH - so "timeout /t 20 /nobreak" is
  resolved to the GNU program, which rejects "/t" as an invalid time
  interval and returns at once. A sleep that silently does not sleep.
  Use "ping -n 21 127.0.0.1 > nul" instead.
- **A lock must be reclaimable by its OWNER'S LIVENESS, not by its age.**
  A lock whose timestamp is fresh can still be a corpse: a rebuild that
  was killed leaves a lock that is seconds old, and an age-based guard
  then says everything is fine - so the service stays down over a lock
  nothing will ever clear. Test the owner's process, not the clock. And
  when you scan for "is it alive", exclude the scan's own ANCESTORS:
  the shell and the agent that are running the scan have the pattern in
  their command lines, so a naive scan finds itself and reports a live
  process that does not exist. A dead owner with a live CHILD is still
  a live rebuild - check for any matching process, not one pid.
- **A vector index that reports a healthy count can still be answering
  every query with garbage.** Chroma keeps the VECTOR BLOBS in the HNSW
  segment files in the collection directory, not in SQLite. The
  `embeddings` table is a manifest: ids, slugs, chunk indexes, nothing
  more. Delete the HNSW files and `count()` still reports every row,
  `/health` still says the index is fine, and the only vectors left are
  the handful still in the write queue - which happen to be whatever was
  being written at the time.
  - The only proof an index works is SELF-RETRIEVAL: embed a chunk
    whose text you know, query with it, and confirm the same chunk
    comes back at distance ~0. One minute of work, and it is the only
    test that would have caught it.
  - Never delete a collection's HNSW files to "fix" a corrupt index. The
    recovery for a corrupt HNSW is to REBUILD. The vectors exist nowhere
    else, so deleting them destroys what the rebuild was meant to
    preserve.
- **A distance is not a similarity, and the conversion is a claim about
  the collection's space.** Chroma's `l2` distance is the SQUARED L2 -
  verified on the live index: reported 1.440718 against a computed
  `||q-v||^2` of 1.440717, exact to six decimals. For unit vectors
  `||a-b||^2 = 2 - 2*cos`, so cosine = `1 - dist/2`. Using the cosine
  conversion (`1 - dist`) on an l2 collection produces negative scores,
  which get clamped to zero - so the vector half of a hybrid search
  silently contributes nothing while appearing to work. State the space
  explicitly when opening the collection, and verify the conversion
  against a hand-computed distance before trusting a single score.
- **A start path is a fact; whether to use it now is a policy.** The
  registry's `start.heal: false` is an explicit refusal and it wins over
  the existence of a start path. ComfyUI has a start path and is meant
  to be down: starting it holds ~17GB of the RTX 3090's VRAM and evicts
  the model the automation itself runs on. Every layer has to honour the
  refusal - the watchdog, the bench, and `heal()` itself.
- **A stall detector that shares a process with the stall cannot detect
  the stall.** The vector rebuild's own watchdog thread was created,
  slept, and then never ran again: chroma's Rust `delete_collection` and
  `upsert` hold the GIL for the whole call, so the thread could not get
  the GIL back. It was visible in the thread list and provably unable to
  fire - which is worse than no watchdog, because it reads as protection.
  A detector must live in a DIFFERENT process and read something the
  stalled process cannot fake. The rebuild now TOUCHES its lock file
  after every batch, so the lock's mtime is a heartbeat, and
  `nexus-core/tools/rebuild_lock_guard.py` - run by the server launcher,
  from outside - treats a quiet lock as a wedged rebuild, ends it, and
  clears it so the service can come back. A FRESH lock still wins and
  the server still stays down: that is the whole point of the lock.
- **Take the lock BEFORE the expensive part, not after.** The rebuild
  imported chromadb + onnxruntime before it took the lock - 18 minutes
  on this host - so for those 18 minutes it owned nothing and a second
  rebuild could start, pass the same checks, and take the lock a moment
  later. Two rebuilds against one Chroma file is not slower, it is
  broken. Time the lock's appearance: it must appear in seconds.
- **One service, one owner.** Two agents managing the same port fight
  over it: each supervisor kills the other's child, so the service
  flaps between up and down while both agents believe they are healing
  it. The symptoms look like a crashing service - a child exiting with
  uvicorn's STARTUP_FAILURE code 3 every few seconds with the backoff
  climbing, and a supervisor log full of "another supervisor already
  owns this port". Pick ONE owner (the estate watchdog) and let the
  other hand off, rather than running two start paths at one service.
- **A launcher's exit code is not proof that it did the thing.** The
  canonical launcher exits 0 when it REFUSES to start a service, which is
  the correct answer while a maintenance lock is held. A healer that
  reads "rc == 0" as "healed" will report a false success on a service
  that is still down. After any heal, PROBE the service. The only proof
  that a service is up is that it answers.
- **A maintenance window and a fault look identical from outside.** A
  deliberate outage (a rebuild holding a lock) and an accidental one (a
  crash) are the same to a prober. Only the lock tells them apart, so
  the lock has to be visible to the gate, the bench and the healer - and
  all three must say "maintenance", not "failed".
- **A disable must have a restore, and the restore has to be
  STRUCTURAL.** A SKILL can switch off the estate's recovery layer:
  two skills told an agent to disable THRONE_Watchdog_5min before long
  GPU work, which is correct, but one of them never said to re-enable
  it, so an interrupted run left the watchdog off with nothing in the
  event log. Use a `try/finally`, or a shutdown path in the worker. And
  make the estate restore it itself - the watchdog cannot heal itself, so
  something that is not the watchdog has to. CHECK IT EVERY TIME: a
  disabled watchdog is invisible from the service side, because the
  services it would have healed are simply down, and nothing in the
  cron log says why. `Get-ScheduledTask -TaskName THRONE_Watchdog_5min`
  returning `State=Disabled` is the single most useful line to read
  when a service that should be up is not.
- **The disk-cleanup plugin deletes `test_*` files at session end.** It
  classifies any file named `test_*` outside a protected top-level tree as
  category `test`, and a `test` file is deleted when the session ends. A
  house test that the estate gate RUNS is therefore disposable unless its
  directory is protected. Put house tests in `tests/` (protected as of
  2026-10-27) and never in `scripts/`. The symptom is a gate run that
  reports "test file missing" and an estate that looks broken when it is
  only incomplete. Check `disk-cleanup/cleanup.log` for `TRACKED:` then
  `DELETED:` on the same path to confirm this. `guess_category()` returning
  `None` for the path means it is protected.
- **A launcher's `pause` hangs any caller that inherits a console.** The
  watchdog ran the ComfyUI `.bat` with an inherited stdin, so `pause` waited
  for a keypress that never came; the heal burned its whole budget and
  reported the service as still down even though the launcher had worked.
  The watchdog now passes `stdin=subprocess.DEVNULL`. If you write a
  launcher for the house, do not end it with `pause`, and do not print a
  conditional-sounding hint unconditionally - an unconditional
  "if you get a c10.dll error" line gets logged as the diagnosis.

- **A check that CANNOT pass is a check that teaches you to ignore it.** Three
  verifications in this estate had been failing for months against systems that
  were entirely healthy, and all three failed the same way: they compared the
  wrong two things. The launcher contract asserted `notes == vectors` on a
  CHUNKED index (2,804 notes legitimately become 20,561 vectors, one vector
  per chunk). The rebuild compared a slice against the whole corpus, so its
  fallback re-upserted every note and its "did this pass finish" test was only
  true in a state the function is never reached in. The mirror parity check
  read a file as TEXT and compared it to a row, a str, so a CRLF file could
  never equal an LF row - 699 of 2,804 files reported as drifted when not one
  character of text differed. When a verification has been red for months while
  everything else is green, THE CHECK IS THE SUSPECT, not the system. Compare
  the two things that are actually supposed to agree, in the representation
  they are actually stored in, and treat a line ending as a non-content
  difference. Prove a check can still FAIL before you trust it to clear
  anything.
- **A chunked index is verified by COVERAGE, not by a count.** The only
  question is whether every note has all of its expected chunk ids present.
  `nexus-core/tools/index_coverage.py` computes the expected chunk ids for
  every note (`chunk_note` -> `_chunk_ids`) and asserts they are all in the
  collection, fetching the ids DIRECTLY rather than trusting `count()` - the
  rebuild had already learned that `count()` disagrees with the id set the
  collection actually holds. A separate trap: the vector BLOBS live in the
  HNSW segment files, not in SQLite, so `count()` can report every row while
  the index answers every query with garbage. Only self-retrieval proves an
  index works.
- **A second Chroma client CRASHES THE SERVER, not just the other tool.**
  This is the sharp edge of the rule above, and it was learned the
  expensive way: 161 child crashes with 0xC0000005, 338 server
  generations, the supervisor restarting every 4-33 seconds. The Windows
  event log names the faulting module - `chromadb_rust_bindings.pyd` - so
  it was never a supervisor problem. A READER on the server's own
  Chroma file is enough; it does not have to be a writer.
- **Measure a live service's index in the window where it is DOWN.**
  The tempting fix - compute the coverage INSIDE the server, with the
  connection it already owns - was tried and it was worse: reading 2,804
  note bodies took 37 seconds, so every call was a 44-second request,
  and while it ran the service's own `/health` went from 7 milliseconds
  to 12 seconds with one probe failing outright. A check that degrades
  the thing it verifies is not a check. The working shape is SEQUENCED:
  stop the service, run `nexus-core/tools/index_coverage.py` (which
  writes `data/index_coverage.json` atomically), start the service, then
  read the result. The window where the service is down is also the
  window where nothing can write the index, so the measurement is still
  true after the restart. `GET /api/index/coverage` SERVES that file - it
  opens no Chroma client, computes nothing, and answers in milliseconds;
  the result carries the time it was measured, so a stale answer is
  visible rather than misleading. The tool REFUSES to run against a live
  service (exit 2) because it is a second Chroma client, and that is the
  thing that has been crashing the server. `--force` overrides.
- **A lock that is WRITTEN is not a lock.** The supervisor's
  `_take_lock()` wrote `logs/supervisor.lock` with a plain `write_text`,
  so two supervisors could both "take" it - the second overwriting the
  first's record - and both went on to serve the same port, each killing
  the other's child as an orphan. That was the flapping, and restarting
  never fixed it because the arbitration was never atomic. Take it with
  `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` so the kernel
  decides the winner; steal the lock only after showing the holder is
  DEAD; never take one from a live holder.
- **A refused process must not write the owner's files.** A supervisor
  that refused to start used to overwrite the OWNER's
  `supervisor_status.json` with its own refusal, so the service could be
  running while its own status file said it had been refused - and the
  contract's "the running service is undisturbed by the refusal" check
  failed for a reason nobody could see. A refusal is evidence and
  belongs in its own file (`supervisor_refusal_<pid>.json`).
- **A check that reads a pipe it did not create can block forever.** The
  launcher contract started the service with
  `subprocess.run(["cmd","/c","start","/b",...], capture_output=True)`,
  and the detached supervisor inherited the stdout pipe - so
  `communicate()` waited for every writer on that pipe to close, and the
  call raised `TimeoutExpired` after 60 seconds with the service
  actually up and healthy. The launcher is a STARTER, not a service: fire
  it with `Popen` and `DEVNULL` and prove it with a health poll. The
  same shape appears with a file handle left behind by a measurement
  process killed mid-run, which left the service reporting chroma
  "busy" long after the measurement was over - a killed process leaves
  its handle on the file.

## Verification

A healthy estate passes all of these:

- `http://127.0.0.1:8642/health` returns 200 with `{"status":"ok"}`
- the ticker heartbeat is under 60 seconds old, and several samples confirm
  a steady period rather than one lucky reading
- every repeating task has a future `NextRunTime`
- `hermes cron doctor` reports no issues
- a forced `cron run` of the target job SUCCEEDS and its output file contains
  a real report
- at least one execution row shows `source: builtin` for the job being
  claimed as autonomous
- `hermes mcp test <server>` connects and lists the expected tool count
- the estate watchdog exits 0 with "estate is healthy"
- the NEXUS launcher contract exits 0 with "LAUNCHER CONTRACT: ALL PASSED",
  and the index line reads "N/ N notes covered, M/ M chunk ids present"
- `nexus-core/tools/verify_corpus.py` prints "VERIFY: PASS", with "distinct
  notes covered by vectors" equal to the note count and "rows containing a
  known live value" at 0

## References

- `references/runtime-state-reading.md` — the `cron/jobs.json`,
  `executions.db`, and `gateway_state.json` field names, plus the traps
  around stale platform errors, platform enablement, and the handoff
  plugin's mDNS collision.
