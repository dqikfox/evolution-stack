---
name: ultron-evolutionary-loop
description: Use for continuous self-improvement cycles.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [evolution, self-improvement, benchmark, gate, consolidation, throne]
    related_skills: [hermes-continuous-learning, doc-fanout]
---

# Evolutionary Cycle (Ultron) — THRONE

## When to Use

- The user says "evolve", "improve", "self-improve", "keep building", "optimise".
- The user asks for a continuous improvement loop, a self-improving agent, or a
  benchmark-gated evolution cycle.
- The user complains that the stack has too many disconnected systems → run the
  consolidation audit, not a new build.
- The `THRONE_Evolution_Loop` cron fires and you are the worker executing one cycle.

Do not use for: one-off refactors with no loop, or when the user wants a plan only
(use the `plan` skill).

## The rule that governs this skill
**Never add a new self-improvement system. Upgrade the driver that already fires.**

THRONE already runs an evolution cron, a gap scout and a watchdog. A fresh standalone
loop becomes system #101: it never touches the daily driver, so its gains do not
compound. Add the missing capability to the existing driver instead — archive,
benchmark, gate, rollback.

## Where the work lives
Evolution Stack: `E:\ultron-memory\evolution-stack` (github.com/dqikfox/evolution-stack).
Architecture, CLI, bench design, cron wiring and validator patterns:
`references/evolution-stack.md`. Read it before touching the loop.

The two systems this stack coordinates:
- **TESSERACT** (`:8705`, `C:\Users\KING\Projects\TESSERACT`) — the control
  plane: service census, Ollama control, sessions, graph, operator buttons.
- **NEXUS CORE** (`:8650`, `E:\ultron-memory\nexus-core`) — the knowledge
  plane: Chroma vectors, hybrid search, RAG, hive bus, importers.

The contract between them is `E:\ultron-memory\infra\SERVICES.json` (start
paths) and the TESSERACT service registry. A full analysis of both, the
defects found and the fixes, is in
`docs/stack-analysis-tesseract-nexus.md` in the evolution-stack repo.

## Workflow (one cycle)
0. **Learn** — `python -m evo learn` rebuilds the proposer prompt from live
   evidence: distilled lessons (`memories/LESSONS.md`), current cron failures,
   previously rejected proposals, and previously accepted wins. `evo cycle` does
   this automatically. A loop that cannot see what the operator corrected is
   blind: it repeats the same bad proposals.
1. **Baseline** — `python -m evo cycle` (runs the scout, benchmarks, writes
   `cron/output/evolution_status.json`). The same command also **heals** any
   service that has a documented start path in `E:\ultron-memory\infra\SERVICES.json`
   before scoring, so a dead port is restarted rather than written about. Never
   skip it; every improvement claim is a delta against this baseline.
2. **Consolidate before you build** — `python -m evo audit`. If the audit reports
   MERGE / RETIRE / REPAIR items, clear those first. Adding a component on top of a
   redundant surface is regression dressed as progress.
3. **Propose** — `python -m evo propose --model starscream-64k`. One change, one
   target, inside the allowed surface (`hermes/skills/**`, `hermes/scripts/**`,
   `.py`/`.md` only).
4. **Gate** — `python -m evo apply <id>`. The stack snapshots, applies, re-benchmarks
   and **rolls back automatically** unless the gate score strictly increased. Never
   hand-edit around the gate — that is how unmeasured drift gets in.
5. **Verify** — `python -m evo bench` and `python -m evo status`. Quote the numbers
   (before → after), never adjectives.
6. **Record** — accepted and rejected variants live in the archive with their score
   and reason; consolidation reports land in `reports/`. An accepted change is
   mirrored into the stack repo under `surface-mirror/` so what the loop changed is
   git-tracked and diffable.

## Benchmark design (decides whether the loop works at all)
- **Two scores.** `gate_score` counts only checks a *file change* can fix; `host_score`
  adds operator-level items (services with no local healer, dirty repos). Accept/reject
  is decided on the gate score.
- A benchmark that scores unfixable items makes the proposer chase unreachable goals —
  it will write a script to "fix" repo cleanliness by committing the user's work. The
  benchmark was wrong, not the model. Split the score rather than blaming the proposer.
- **Strict improvement only.** A 0.00 delta is a rejection: a change that changes
  nothing is churn, and churn accumulates in the surface.
- **Proof obligation.** Before claiming the loop works, run a test that demonstrates
  BOTH paths: accept-on-improve and reject-then-rollback-on-regression, with the
  restored content verified byte-for-byte. `tests/test_gate.py` in the stack is the
  reference implementation.

## Safety rules (non-negotiable)
- Improvable surface: `hermes/skills/**` + `hermes/scripts/**` only. Never
  `cron/jobs.json`, `config.yaml`, credentials, 1Password, or another profile's
  skills/plugins/cron/memories.
- The proposal validator blocks recursive deletes, `git add`/`git commit` (shell *and*
  list form), disk ops, registry/task deletion, process kills, `eval`, path traversal
  and non-`.py`/`.md` targets.
- The stack never deletes files. Deletion is an operator action, done by hand, with the
  archive recording why.
- Every apply snapshots the whole surface first; rollback is automatic and re-verified
  by a second benchmark run.

## Pitfalls
- **Parallel-loop syndrome** — building DGM/SICA as a fresh project while an evolution
  cron already runs. The gains never reach the daily driver.
- **A check that always fails poisons the gate** — e.g. `py_compile` writing to
  `os.devnull` on Windows reports every script as broken; a skill-dir check that counts
  `.hub`/`.locks` as broken skills. Validate every check against the real host before
  trusting a score, or every candidate looks like a regression and gets rolled back.
- **Baseline must be measured inside the same apply call** — a baseline taken minutes
  earlier, or before an unrelated change, makes the delta meaningless.
- **Blind regex rename corrupts mapping prose** — a sweep that renames every occurrence
  also rewrites sentences that *describe* the rename ("X (= X)"). Repair those by hand;
  the full rename procedure is in `doc-fanout`.
- **Recursion needs storage** — keep the proposer's own prompt in the archive and use
  the best-scoring proposer for the next mutation, otherwise the improver can never
  improve itself.
- **Learning must be plumbed in** — lessons, cron failures and rejected proposals
  belong in the proposer prompt (`evo learn`), not in a separate notes file. A
  learning loop that does not change what it proposes is just a logger.
- **A one-sample threshold is a false alarm** — `ollama-health.py` failed its cron
  every 5 minutes because a single 100% CPU sample tripped the threshold. Require
  sustained pressure (consecutive samples) before declaring degradation.
- **Vault outages must not break automation** — 1Password's service account gets
  rate-limited (its CLI even prints an empty retry hint). Cache resolved secrets
  with Windows DPAPI (CurrentUser) so dependent jobs survive the outage; the
  plaintext never touches disk or a command line.
- **Orphaned search processes are a real load** — a stray `find`/`grep` burned
  6,681 CPU-seconds and pegged the host at 100% CPU. Check for leftovers from
  timed-out searches before blaming the workload. BOUND every search: an unbounded
  recursive walk over a large tree (a knowledge corpus, a venv, a repo with
  `node_modules`) can pin the tool call until it is killed and lose the work it
  was carrying. Search a named root, cap the result count, and use the search
  tool's own path and glob filters instead of hand-rolled recursion.
- **Mirroring the surface needs size discipline** — mirroring dot-directories
  (`.curator_backups`, `.hub`) pulled 254 MB of tarballs into the repo. Skip
  dot-paths and files over 512 KB.
- **A service with no start path cannot be healed** — the loop was writing notes
  about HERETIK :8080 and KRYSYS :8500 for days instead of restarting them.
  Document the start path in `E:\ultron-memory\infra\SERVICES.json` and the
  cycle restarts it automatically.
- **A start path is PERMISSION, not just a capability** — the rule above
  pushes the loop to add a start path to EVERY service it finds unhealed, and
  that is wrong for a service that must stay down. ComfyUI is the case: it
  parks ~3.2GB of CUDA context on the RTX 3090 while the agent's own
  `starscream-64k` needs 17.5GB of 24GB, so a watchdog-healed ComfyUI starves
  the agent that is running the loop. The loop read "no start path" as a
  defect and added one. The registry therefore carries an explicit opt-out,
  `start.heal: false`, and the loop must honour it: "has a launcher" and
  "may be auto-healed" are different questions. When you deliberately keep a
  service unhealed, record the reason in the entry's `notes` so the next
  cycle sees the DECISION and not just the missing field. A service the loop
  should never touch belongs to the operator, not to the healer.
- **The loop's own report is a CLAIM, not evidence** — a cycle that reports
  "updated with a valid launcher (run_nvidia_pro.bat)" may have written a
  different path, or a path that does not exist on disk. The report also
  asserted the state was correct while the bench it cited had itself errored
  out. Before acting on a cycle's report, re-read the file it says it changed
  and confirm the named path exists; a self-report that cannot be checked
  against the filesystem is the loop grading its own homework. Quote the
  gate delta you actually measured, and say plainly when a sub-step failed
  rather than substituting a reason for why the disk state is "confirmed".
- **A start path without its interpreter is not a start path** — a script that
  needs a specific environment (NEXUS needs the uv venv with numpy+chromadb)
  will fail when the healer launches it with the bare `python` on PATH. Put the
  interpreter in the registry entry (`"interpreter": "..."`) and the healer
  uses it; the loop refuses to launch if the interpreter is missing.
- **A bare background process is not a service** — NEXUS died on a Windows
  socket-accept failure (`WinError 64`) and stayed dead because nothing owned
  it. Every long-lived service needs a supervisor that restarts it with capped
  backoff, reclaims the port from an orphaned previous instance, and reports
  state to a status file. Then *prove* it: kill the child and verify it comes
  back without intervention.
- **A health endpoint that probes its own dependencies reports false outages** —
  TESSERACT's `/health` ran a service census that included TESSERACT itself, so
  the nested request timed out and the dashboard showed the instance as offline.
  A liveness endpoint must be local-only and single-digit milliseconds, serving
  dependency state from a background-loop cache.
- **"The port answers" is not "the service works"** — NEXUS answered `/health`
  with `200 OK` and `chroma: not_ready` in the same payload, for a long time.
  Read the component block, not the envelope; a degraded component is a defect
  even when the envelope is green.
- **Hardcoded LAN addresses rot silently** — TESSERACT pointed four services at
  `192.168.4.230`, a dead DHCP lease, so they were permanently "offline" while
  two genuinely local services were classified as remote. Address remote hosts
  by Tailscale IP, and verify every registry entry against the live machine.
- **TestClient without a context manager never runs startup** — every NEXUS test
  passed while the service could not start. Any test that must cover a startup
  hook uses `with TestClient(app) as c:`.
- **Check that a service still exists before health-checking it** — ULTRON :8666
  had no implementation left (its project directory was deleted, the startup
  shortcut dangled), so the check was chasing a ghost and depressing the score.
  Mark it `retired` and document the supersession.
- **A dangling startup shortcut is worse than none** — it fails at every logon
  and hides the fact that the service is gone. Resolve shortcuts to their real
  targets before trusting a service registry.
- **A self-copy in the working tree is not work** — an archive of the repo plus its
  extraction is the repo inside the repo, and the proposer must never generate or
  keep one. Verify the duplicate, then delete and gitignore it. (For human commits,
  `code-review-light` runs this as its payload check.)
- **A mirror that copies files verbatim will eventually publish a secret** — the
  surface mirror copied a launcher containing a plaintext `N8N_ENCRYPTION_KEY` into
  the PUBLIC `dqikfox/evolution-stack` repository. The fix is a refusal path, not
  vigilance: `evo/secrets.py` scans a file, `evo/mirror.py` refuses to publish one
  with a secret-shaped value, `evo/bench.py` gates on `secrets:mirror` /
  `secrets:scripts`, and `hermes/scripts/safe_commit.py` refuses to stage one.
  A secret belongs in 1Password and is read at run time — never in a file.
- **A secret in git history is not a secret you deleted** — purge it in this order:
  rotate the value first (so any cached copy is worthless), rewrite every blob
  (`git filter-repo --replace-text`), force-push, then confirm the old commit is
  unfetchable by SHA and the API no longer serves the file. Note that
  `filter-repo --force` does a `git reset --hard`: it silently discards unstaged
  work, so re-apply anything you had not committed.
- **A service that inherits the launching session's stdout pipe never lets that
  session end** — the child holds the pipe open after the session dies, so the
  session never sees EOF, stays "running" forever, and replays its stale buffer
  as endless heartbeats. `close_fds=True` is required on EVERY spawn in the
  chain, not just the last one.
- **A cron job whose work a script can do should BE a script** — the hourly
  `Nexus_Core_Sync` was model-driven; on two of five runs the model degenerated
  into a repetition loop and the run was recorded as a FAILED job, while the
  actual condition was "MSI offline" (an expected external state, not a defect).
  The work was a file listing plus a front-matter parse: deterministic work with
  a deterministic exit code. Rewrite the job as `script` + `no_agent`, have the
  script own the data, and let the model report the exit code. A model in the
  path adds three failure modes (loops, forgotten preflight, wrong channel).
- **A health observation must not travel through the job-failure channel** — the
  5-minute Ollama beat exited 1 whenever the host was busy, so a loaded machine
  produced a failed job every 5 minutes and buried the failures that matter. A
  probe's exit code must mean "did the probe do its job"; load state is DATA
  (`degraded`, `reasons`), judged separately on a TRANSITION. Alert on an
  episode (sustained pressure) and on its recovery — never per sample. Put the
  episode in the operator's existing feed (a TESSERACT alert row) rather than
  opening a second channel nobody watches.
- **A secret in a LOCAL corpus is still a published secret** — the NEXUS corpus is
  served over HTTP by `/api/ask` and embedded into a vector index, so a
  credential stored in a note is a credential the AI can read back out. A
  Notion export of a credential vault had put live Notion, Telegram and Twilio
  keys into it. Redact at the STORE (`create_note` is the choke point), not
  only at the publish boundary: a corpus is a read boundary too. A redaction
  keeps the note's MEANING — `[[REDACTED:NAME]]` plus a `redacted:secrets`
  tag — and the guard must stay narrow, because a guard that mangles real
  notes gets switched off.
- **A scanner that only understands assignments cannot see a bare secret** — a
  key staged alone on a line has no name and no context. The estate sweep
  reported the scratch tree clean while the live n8n key sat in it. Detect a
  high-entropy token alone on a line as well, and keep the rule narrow (not
  hex-only, mixed case, entropy ≥ 3.5, never a placeholder or a uuid).
- **Git QUOTES non-ASCII paths, so a suffix filter silently skips the file** —
  every credential note was named with an em-dash and an emoji, so the history
  sweep reported those repos clean while the secrets sat in the history. Use
  `git ls-tree -r -z` and split on NUL. A sweep that has never scanned a file
  is a sweep that has never been tested.
- **A synthetic secret-shaped fixture in source is a finding in every commit
  that contains it** — assemble test fixtures at runtime. The pre-commit
  scanner is right to refuse a commit whose test file holds a literal.
- **An endpoint that counts a swallowed exception as a success will lie** —
  `/api/elite/reindex` wiped the collection, indexed nothing (every call
  failed on a `KeyError` that was swallowed) and still reported
  "indexed: 2472". Make the count honest, rebuild BEFORE deleting the stale
  entries, and never let a helper swallow its error without reporting it.
- **Batch the work, and know which part is slow** — 2,472 notes took 10m50s
  because each note was one embedding call and one Chroma upsert. 32 notes
  per embedding call and one upsert per batch: 2s per note → 0.06. Chroma's
  cost is per CALL, not per row.
- **A test suite that talks to the LIVE service writes into the LIVE corpus** —
  the hive test posts a message, the running service stores it as a note, and
  `/api/ask` then serves the test output as knowledge. Five notes per run had
  been accumulating for weeks. Give the suite its own corpus
  (`NEXUS_CORPUS_DIR`) and make a test that writes delete what it wrote.
- **A test harness that lives in scratch is a hazard, not a test** — the scratch
  `launcher_e2e.py` waited 90s for a launcher whose own budget is 180s, so it
  reported "LAUNCHER NEVER EXITED" on a launcher that was working, and it killed
  processes by PID in a live stack. Put the contract in the repo
  (`tests/test_launchers.py`), make the deadline EXCEED the implementation's
  stated budget, always restore the service, and assert exactly one supervisor
  chain afterwards. A test that can leave a service down is not a test.
- **"The port answers" is NOT "the service is healthy"** - a supervisor that
  was killed leaves its child running and holding the port, and a launcher
  that only probes the port says "already up" and never starts a supervisor.
  The service then serves unsupervised, on possibly stale code, and nothing
  restarts it if it dies. Worse, the replacement supervisor cannot bind
  ([Errno 10048]) and the service is DOWN while the launcher reported
  success. So the launcher must RECLAIM before it decides: clear an orphan
  only when no live supervisor owns the port, and never touch an unrelated
  process on it. `hermes/scripts/service_control.py reclaim --port <p>
  --marker <script>` does this, and both canonical launchers call it before
  their "already up" check - so the check now means "up AND supervised".
- **A process matcher must not match its OWN invocation** - the marker is
  usually the tool's last argument, so the tool's own command line ends
  with it. A supervisor is a python interpreter whose command line ENDS with
  the service script: nothing else, and the tool excludes itself by name.
  A powershell/cmd wrapper that merely has the marker as an ARGUMENT is
  not a supervisor, and counting it produces a false "2 chains" verdict on
  a perfectly healthy service.
- **An unescaped `(` inside a cmd `if ( )` block breaks the parser** - the
  launcher dies with "- was unexpected at this time" and a non-zero exit,
  which looks like a service failure and is not one. Keep echo text inside
  cmd blocks free of parentheses.
- **A logger with its own handler AND a root handler pointing at the SAME
  file writes every record twice** - and a traceback, being one record with
  many lines, is duplicated line for line. `propagate: false` on the child
  logger is the fix; check the other explicit loggers for the same shape.
- **Read the service's OWN logs** - the defects that matter (a port that
  cannot be bound, a record written twice) are visible in the log file and
  invisible to a passing test suite.
- **"The commit API returns 404" is NOT "the content is gone"** - a commit can
  be unreachable from every ref and still be served by the contents API
  during GitHub's grace period for unreachable objects. The test that counts
  is fetching the FILE at the old ref. Verifying a history rewrite with the
  commits API alone is a false all-clear, and it is how a rewritten
  repository can still be serving the literal it was rewritten to remove.
- **A scanner that reports "0 findings" must also report WHAT IT SCANNED** -
  a repository that could not be swept produced exactly the same output as a
  clean one, and that is the most dangerous output a scanner can give. Print
  the commit count, refuse to report a count for a repo it could not read,
  and exit non-zero when any repo was not swept.
- **`git filter-repo` REMOVES the `origin` remote** as a safety measure, and
  with it the remote-tracking ref. Re-add the remote before pushing, or the
  push fails with "'origin' does not appear to be a git repository" and the
  rewrite looks lost. The lease must be ONE argument
  (`--force-with-lease=main:<sha>`), not two.
- **A test must not depend on a stale environment variable** - a guard that
  read `os.environ["NEXUS_DB_PATH"]` to protect the live corpus was itself
  the thing that broke the moment the stale value was cleaned up. Read it
  with a default, and treat an unresolvable path as harmless.
- **A supervisor RESTARTS its child, so kill the supervisor FIRST** — and check
  for an ORPHAN still holding the port: a supervisor that died while
  respawning leaves the child serving, the launcher calls the service
  "already up" and never starts a supervisor. `hermes/scripts/service_control.py`
  does this and asserts the end state: one supervisor CHAIN with the port
  owned by its tree. Count CHAINS, not processes — the uv shim and the venv
  python are two processes in one tree.
- **An env var that already exists will hijack your new override** — the Hermes
  `.env` had a stale `NEXUS_DB_PATH` pointing at an empty `core/nexus.db`.
  Use a NEW name for a new knob, and never make a live path depend on an
  inherited environment variable without checking what is already set.
- **A namespace package loses to a regular package of the same name anywhere on
  `sys.path`** — the stack's `tools/` was a namespace directory, so
  `from tools.history_secret_sweep import sweep` resolved to the Hermes agent's own
  `tools` package and failed naming the SUBMODULE, which is the tell: `tools`
  imported fine, it was simply the wrong `tools`. Give the directory an
  `__init__.py` so it is a regular package found first on the path.
- **One canonical lesson ledger, and a one-way snapshot of it** — the live ledger is
  `hermes/memories/LESSONS.md`; NEXUS keeps a private snapshot refreshed by
  `scripts/sync_lessons.py`. A second writable ledger is a second source of truth
  that drifts; take the pattern of a new tool (dedupe, reversibility, check before
  the log line) without the substrate.
- **Operational state read by another system lives under its writer's directory** —
  the estate publishes peer state under the evolution stack's own `state/`, not under
  a consumer's directory, and writes it atomically so a reader never sees a
  half-written file. Carry the generation time with it: a reader that shows stale
  state as current is worse than one that shows nothing.
- **Stage explicit paths, never the whole tree** — `git add -A` in the evolution
  stack can stage the publication mirror's deletions and a scratch file in one
  commit. List every path, including the paths a mirror pruned.
- **The surface mirror publishes the house surface and prunes what the house
  archived** — a skill that moved to `.archive/` in the house is removed from the
  mirror, which is correct: the mirror is a publication surface, not a backup.
- **A peer that is unreachable is not a failed service** — score it false on the
  gate and report it, so the gate does not fail for a machine that is switched off.
  The states, the transports and the estate implementation are in the
  `throne-sysadmin-network` skill under "Service and Peer Contracts".
- **Report the delta, not the vibe** — "gate 84.62 → 76.92, rejected, rolled back"
  beats "made it better".
- **Network awareness** — never ignore the relationship between this host (THRONE) and
  its satellites (MSI, S23, Cyclone-C4). We evolve as a network, not in isolation.
- **Stagnation** — do not re-run a completed task without adding verification or
  complexity; do not park a green-health result and stop.
- **A finished milestone is not a stopping point** — under a standing "keep
  building" instruction, the end of one coherent batch is the moment to pick the
  next obvious high-leverage gap and ship it, not the moment to hand back a status
  summary and wait. Choose the next target yourself, decide, execute, and report
  what the work DID rather than a plan for it: an operator who has to ask "what
  next?" every cycle is doing the agent's job. Spend a question only on a decision
  that is genuinely the operator's — a spend, a deletion, a credential, a
  third-party account — and batch everything else into the turn and ship it.

### When the work is a shop that takes money

- **A quote and a charge must be the same function.** Two copies of the price
  arithmetic drift, and the drift is invisible until a customer is quoted one
  number and charged another. One builder produces the line items, the
  subtotal, the shipping and the total; every route calls it.
- **A static handler mounted over a project root publishes the project's
  private data, not just its assets.** The order store, the server source
  and the wholesale cost basis are all fetchable by path. Deny them
  explicitly, and prove it by fetching the path and reading the body.
- **A webhook handler that falls back to an unsigned body when the signing
  secret is missing is a free-goods button.** Fail closed with a 503. A
  default secret in source is worse than no secret, because it lives in the
  repository's history.
- **Credentials hardcoded in source are compromised the moment they are
  committed.** Remove the fallback, require the environment, and rotate the
  exposed value - the commit history keeps the old one.
- **Verify the whole path a customer walks, over the public URL, with a real
  checkout session** - not a dry run and not a local probe. A dry run proves
  the arithmetic; only a real session proves the money path.
- **A checkout session created for a test is an order in the live store.**
  Identify it precisely and remove it, so the pre-existing real orders stay
  the record of what actually happened.
