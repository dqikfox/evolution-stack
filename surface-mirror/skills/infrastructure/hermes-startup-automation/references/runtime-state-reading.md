# Reading Hermes runtime state accurately

Field names and file locations that are easy to get wrong, and the traps in
each. Use this when a health check, a cron report, or a gateway status line
disagrees with what you expect.

## Cron job state: `cron/jobs.json`

The registry is `{"jobs": {...}, "updated_at": ...}`. Each job carries these
fields — note that the timestamps are `_at`, NOT `next_run` / `last_run`:

| Field | Meaning |
|---|---|
| `next_run_at` | ISO timestamp of the next scheduled dispatch |
| `last_run_at` | ISO timestamp of the last run start |
| `last_status` | `ok` / `failed` / `running` |
| `state` | `scheduled` / `paused` / `running` |
| `failure_streak` | consecutive failures; `0` means the loop is clean |
| `last_dispatch` | `{scheduled_at, dispatched_at, lateness_seconds, kind}` |
| `paused_at` / `paused_reason` | set only when deliberately paused |

**Pitfall: `next_run` and `last_run` do not exist.** Querying them returns
`None`, which reads exactly like "this job is never scheduled again" and
sends you chasing a nonexistent fault. Use `next_run_at` / `last_run_at`.

`last_dispatch.kind` is `on_time` when the ticker fired the job close to its
scheduled instant, and `last_dispatch.lateness_seconds` quantifies the
drift. This is the field that proves an unattended loop fired BY ITSELF
rather than being force-run by hand — quote it when asked whether automation
is genuinely running.

## Execution history: `cron/executions.db`

SQLite. Table `executions` holds one row per run:

```
job_id, source, status, started_at, finished_at, error,
delivery_outcome, handoff_pending, scheduled_instant, progress_at
```

- `source` = `builtin` (the ticker fired it) vs `direct` (a human or a
  `cron run` forced it). Only `builtin` proves unattended operation.
- `cron_incidents` holds failure records with `kind`, `detail`, and
  `resolved`.

Query it directly rather than reading output files:

```sql
SELECT job_id, status, source, started_at, error
FROM executions WHERE started_at > '2026-10-27T06:26'
ORDER BY started_at DESC;
```

## Gateway state: `gateway_state.json`

```
gateway_state: running | degraded | starting | stopped | startup_failed
platforms: { api_server: {state, error_code}, telegram: {...}, ... }
```

**Pitfall: platform errors are STALE until the next restart.** A platform
that was fixed keeps its `fatal` entry in this file until the gateway
restarts and re-evaluates it. Confirm against the gateway log timestamps
before treating a persisted `fatal` as a live fault — the log shows the
moment the platform was disabled, and no connect attempt after it.

## Platform enablement

A platform auto-enables purely because its credentials are present in the
environment. If it then needs configuration it cannot have (Twilio SMS
requires a public `SMS_WEBHOOK_URL` that only exists in the Twilio console),
it refuses to start and parks the whole gateway in `degraded`.

Disable it at the TOP-LEVEL `platforms` key, not under `gateway.platforms`:

```bash
hermes config set platforms.sms.enabled false
```

A disabled platform logs a warning naming the credentials it is ignoring,
and stops being auto-started. Re-enable by setting the value back to `true`.

**Pitfall: `hermes gateway restart` on Windows leaves a short window where
the old process still owns the port.** It reports "still accepting
connections — new api_server may fail to bind", and a platform that polls
can raise a transient conflict (`telegram_polling_conflict`) while the old
process drains. Wait roughly a minute, then re-read `gateway_state.json`:
the new gateway settles to `running` with its platforms connected.

## The handoff plugin's mDNS collision

`[handoff] startup failed:` with an EMPTY reason is not a gateway fault and
not a startup failure. The handoff plugin derives its mDNS service name from
the device id, so the name is stable across restarts. A second live instance
(the running gateway, versus any CLI invocation that loads the plugin) tries
to register that same name and zeroconf raises `NonUniqueNameException`,
whose `str()` is empty. The TCP listener is already bound and serving, so the
advertisement failure is cosmetic.

The service is `hermes-<device_id>._hermes-handoff._tcp.local.` — browse
that exact type, or you will conclude discovery is broken when it is fine.

**Pitfall: the plugin lives OUTSIDE `hermes-agent/`.** It is under
`plugins/<name>/`, so grepping the Hermes package for its log line finds
nothing and you conclude the message comes from nowhere. Look in the
plugins tree.
