# Peer and Service Contracts

Depth for the rules in SKILL.md's "Service and Peer Contracts". The estate-side
implementation lives in the evolution stack: `evo/peers.py` (the peer model),
`evo/bench.py` (the gate), and `hermes/scripts/estate_watchdog.py` (the healer).

## The two registries

| File | Holds | Owner |
|---|---|---|
| `E:\ultron-memory\infra\SERVICES.json` | local services: port, owner, start path, args, health URL, criticality | the house |
| `E:\ultron-memory\infra\REMOTE_AGENTS.json` | remote peers: IP, ssh user/key, and a service list per peer | the house |

Both are read by the estate gate and the watchdog. A registry that has drifted
turns every probe into a confusing failure, so validate the shape when you load it
and treat a malformed entry as "no such peer" rather than a crash.

## Peer service entry

```json
{"name": "gateway", "port": 8644, "health": "http://127.0.0.1:8644/health",
 "heal_task": "Hermes_Gateway", "critical": true, "notes": "the channels gateway"}
```

- `health` is the peer's OWN loopback URL — the peer is asked about it over ssh.
- `heal_task` is a scheduled task ON THE PEER. Its presence is what makes a
  service gate-actionable: a service with a documented start path can be healed, a
  service without one is operator-level.
- `notes` is free text shown in the dashboard. It is where the operator learns what
  the service is for, so it should say the thing you would have to ask.

## The three states and what each one does

| State | Meaning | Gate | Watchdog | Dashboard |
|---|---|---|---|---|
| `up` | the peer answered and the service is healthy | scored pass | nothing | UP (green) |
| `down` | the peer answered, the service is not | scored fail, **healable** | healed via the peer's task | DOWN (red) |
| `unreachable` | the peer did not answer at all | **not scored** (host score only) | reported, never healed | AWAY (amber) |

The `unreachable` distinction is the whole point. The same three states must be
used by the gate, the watchdog and the UI, or the house tells the operator two
different stories about the same machine.

## The probe transport

Probe the peer by running a short script on it over ssh and asking for its health
endpoint. Keep the remote script SHORT: it travels on the peer's command line, and
Windows caps that at ~8191 characters. A long script belongs in the upload/run/remove
transport, not on a command line.

- Short remote script: base64 of UTF-16LE, passed with `powershell -EncodedCommand`.
- Long remote script: upload with `scp`, run with `ssh -File`, delete with `ssh`.
  Never pipe a script over stdin — a timeout leaves the remote reader alive holding
  its session, and every later call then fails the same way.
- Use a UNIQUE remote filename per run and remove it on both success and failure.

## Publishing peer state for other systems

The estate writes `state/peers.json` (under the evolution stack's own directory,
because the stack is its writer). The dashboard reads it rather than probing peers
itself.

- Write it **atomically** (write a temp file, rename it) so a reader never sees a
  half-written file.
- Include `generated_at` and the age. A reader that shows a peer state from an hour
  ago as if it were current is worse than a reader that shows nothing; the UI marks
  it stale past a threshold.
- Refresh it from the watchdog, which already probes the peers every cycle — one
  probe, one writer, one truth.

## Rented peers (stopped when idle)

A rented GPU node is a peer that is switched off when there is no work. Declare a
wake command on the peer:

```json
"wake": ["providerctl", "start", "shadow"], "wake_timeout": 180
```

The command runs HERE, on THRONE: the provider's control plane is what starts the
node, and a peer that is switched off cannot run its own wake command. After the
wake, wait for the peer to answer on the tailnet, then treat it as an ordinary
peer — probed, healed, and displayed like any other.

A peer with no wake command is never woken. Stopping a peer and not being able to
start it is a configuration gap to fix, not something to retry.

## Verifying the whole chain

1. `python -m evo.peers` — the peer survey, one line per peer service.
2. The estate gate — the peers appear as checks, and an unreachable peer is
   `scored: false`.
3. The watchdog — an unreachable peer is reported, the run still exits 0.
4. The dashboard — the peer panel renders the same three states.
5. The house suite — hermetic tests cover the states, the refusal to heal an
   unreachable peer, and the wake path.
