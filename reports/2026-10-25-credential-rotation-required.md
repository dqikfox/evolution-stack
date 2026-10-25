# Credential rotation required — 2026-10-25

**Status: OPEN. Two credentials were exposed in plaintext and are still live.**
Everything else about this incident is closed. This file is the remaining
action, and it needs dashboard access that only the operator has.

## What happened

A Notion export of a credential vault had been imported into the NEXUS CORE
knowledge corpus. NEXUS is a private repository, but its corpus is served
over HTTP by `/api/ask` and embedded into a vector index — so a credential
stored in a note was a credential the AI could read back out, and a private
Git remote is not a safe place for a secret.

The exposure was found by the estate scanner, not by luck: the scanner had
two blind spots, and both of them were closed first so the sweep could be
trusted.

## What was exposed

| Credential | Where it was | State now | Action needed |
|---|---|---|---|
| Notion API credential | NEXUS corpus (note, SQLite, Chroma, Git history) | **still accepted by Notion (HTTP 200)** | **ROTATE** |
| Telegram bot token #1 | NEXUS corpus | **still accepted by Telegram (HTTP 200)** | **ROTATE** |
| Telegram bot token #2 | NEXUS corpus | **still accepted by Telegram (HTTP 200)** | **ROTATE** |
| DeepSeek API key | NEXUS corpus (note, SQLite, Chroma) | **still accepted by DeepSeek (HTTP 200)** - removed locally 2026-10-25 | **ROTATE** |
| Telegram bot token #3 (`@Ultron420bot`) | NEXUS corpus (5 notes, SQLite, Chroma) | **still accepted by Telegram (HTTP 200)** - removed locally 2026-10-25 | **ROTATE** |
| Twilio account credential | NEXUS corpus | rejected by Twilio (HTTP 401) | rotate if the account is still used |
| n8n API credential | NEXUS corpus | rejected by n8n (HTTP 401) | rotate if the account is still used |

Values are **[REDACTED]**. Their locations are unchanged:
`1Password` → vault `credentials` → the item title for each service.

## What has been done

- The four credential notes were redacted to `[[REDACTED:KEY]]` pointers.
  The notes keep their meaning — they still record *which* credential was
  there — without carrying the value.
- The five affected SQLite note bodies were redacted the same way.
- Every secret-bearing Chroma vector document was deleted, and the full
  index was rebuilt. The index and the database now match exactly:
  **2,458 notes, 2,458 vectors, 0 stale, 0 drift**.
- The NEXUS Git history was rewritten (`git filter-repo --replace-text`) and
  force-pushed with a lease. The pre-rewrite head `d4631e3`, the redaction
  commit `7581be5` and two other old SHAs all return **HTTP 404** on the
  GitHub *commits* API.
- The history was rewritten **twice more** on 2026-10-25, because the
  *commits* API is not the right test. A commit object can be gone from
  every ref and still be served by the *contents* API for the grace period
  GitHub allows for unreachable objects. Fetching the **file** at the old
  ref is the test that counts:
  - NEXUS `7aa628b3` — `tests/test_guard.py` still served 2 secret-shaped
    literals. History rewritten; head is now `2e14335`.
  - EVOLUTION `ff5c7936` and 11 other commits — `tests/test_secrets.py`
    still served a literal PEM header. History rewritten; head is now
    `aa07211`. This repo is **public**.
  - After the rewrite, `git rev-list --all` over both repositories returns
    **0 findings** — including the live `fix/working-memory-durability`
    branch on NEXUS, which carries none.
- The history sweep now reports **how many commits it examined**, refuses
  to report a finding count for a repository it could not read, and exits
  non-zero if any repository was not swept. "0 findings" and "nothing was
  scanned" must never look the same.
- The corrected history sweep reports **0 findings** across TESSERACT,
  Pixel, Lummings, Pathway, NEXUS and EVOLUTION.

## Residual: GitHub's unreachable-object grace period

The two rewrites removed the literals from every reachable ref, and the
local history is clean. GitHub, however, continues to serve those old
blobs **by SHA** for a period after the force-push, because unreachable
objects are retained before garbage collection. The values are synthetic
test fixtures, not live credentials, but they are still retrievable:

- `dqikfox/NEXUS` @ `7aa628b3` → `tests/test_guard.py` (2 literals)
- `dqikfox/evolution-stack` @ `ff5c7936` → `tests/test_secrets.py` (1 PEM)

The supported remedy is a **GitHub Support** request to purge unreachable
objects (the "Removing sensitive data from a repository" procedure). The
guaranteed remedy for the public repository is to delete and re-create it,
which resets the object store — at the cost of issues, stars, watchers and
the repository URL. **Neither is done automatically here**; both are
operator decisions, and the support request is the one worth making.
- A store-time guard was added: `core/guard.py`, called from `create_note`.
  A credential entering the corpus is now replaced with a pointer and the
  note is tagged `redacted:secrets`. Ordinary content is untouched.
- Five RAG queries naming the exposed credentials return answers with
  **zero secret-shaped values** in the response.

## The rotation itself

Rotation is the one step that cannot be automated from here: it needs the
Notion and Telegram dashboards, and a bot token is only shown once at
creation.

1. **Notion** — create a new integration token, update the consumer, then
   revoke the old one. The old token is still valid right now.
2. **Telegram** — for each bot, message `@BotFather` → `/revoke` (or
   `/token`) to issue a new token and invalidate the old one. The old
   tokens are still valid right now.
3. Update the new values in 1Password (`credentials` vault), then let the
   consumers pick them up. The consumers read through
   `hermes/scripts/secret_resolver.py`, which caches in DPAPI, so a
   rotation does not require a code change — it requires the consumer to
   re-read.

## Why this happened twice, and what stops it

The public `N8N_ENCRYPTION_KEY` incident and this one share a shape: a
secret was stored where a machine would read it and a human would not
look. Three layers now exist, and each one is a refusal rather than a
warning:

| Layer | What it does |
|---|---|
| `evo/secrets.py` | scans a file for secret shapes — assignments **and** bare high-entropy tokens |
| `evo/mirror.py` | refuses to publish a file that holds one |
| `evo/bench.py` | gates on `secrets:mirror` and `secrets:scripts` |
| `hermes/scripts/safe_commit.py` | refuses to stage one |
| `core/guard.py` (NEXUS) | refuses to STORE one |

Two lessons are worth keeping in mind when the next one is found:

- A private repository is not a safe place for a secret, and a local RAG
  index is a read surface, not a storage surface.
- A scanner that has never scanned a file is a scanner that has never been
  tested. The sweep reported clean for weeks because `git ls-tree` quoted
  every non-ASCII path, and the suffix filter skipped all of them.
- **"The commit API returns 404" is not "the content is gone".** Fetch the
  file at the old ref. A commit can be unreachable and still be served.
- A scanner that reports "0 findings" must also report **what it scanned**,
  or an unscanned repository is indistinguishable from a clean one.
- `git filter-repo` **removes the `origin` remote** as a safety measure.
  Re-add it before pushing, or the push fails with "'origin' does not
  appear to be a git repository" and the rewrite looks lost.


## Second incident, same day: the redaction that redacted the label

The first pass replaced the *pointer* to each credential - the text
`[DEEPSEEK_API_KEY]` - and left the credential value in place. A scan for
the provider prefix found nothing, so the corpus reported clean while the
value was still stored, still indexed, and still live.

**The shape is the evidence.** A credential is a provider prefix followed
by a long token; searching for the prefix alone proves nothing, because
the prefix was exactly what the first pass removed.

Two credentials were confirmed live by provider verdict (HTTP 200 from
the provider, value never printed) and then removed from all three
surfaces: the note file, the SQLite body, and the Chroma document.

- DeepSeek API key: **still accepted by the provider (HTTP 200)** -
  removed locally, **ROTATE**.
- Telegram bot token (`@Ultron420bot`): **still accepted by Telegram
  (HTTP 200)** - removed locally, **ROTATE**.

A blanket guard backfill was rejected: it flagged ordinary words
(`PASSED`, `Token`, `passman`). Targeted, evidence-backed redaction is
the rule.

### The bug that hid it

`index_note()` accepted a note id and looked it up with `get_note()`,
which keys on the **slug**. Passing an id returned `False` - silently.
The reindex therefore reported success while the stale vector document -
with the secret in it - stayed in the index. Fixed in NEXUS `6058bf9`:
look up by id first, fall back to the slug, report honestly.

**A re-embed that silently does nothing is worse than one that fails.**

### Final state

Corpus audited across 15 provider prefixes on all three surfaces
(SQLite, `notes/*.md`, Chroma): **0 findings**, 2,458 records intact.

## Third incident, same day: the MCP surface was dead and nobody knew

Six of the twenty-two configured MCP servers could not start. The
symptom was not an error anyone was reading - it was **47,739 failed
start attempts** for one server in `mcp-stderr.log`.

| Server | Why it never started | Fix |
|---|---|---|
| `throne` (32 tools) | `command: python` resolved to an interpreter without `mcp.server.mcpserver` | point at the Hermes venv interpreter |
| `bot-team` | pre-`MCPServer` API: `server.run(r, w, server.create_initialization_options())` | `server.run("stdio")` |
| `youtubedl` | `${VAR:-default}` is not Hermes syntax, so the literal string reached the server as a path | real values in the config |
| `ffmpeg` | same as `youtubedl` | real values in the config |
| `thinking` | `mcp-server-sequential-thinking` is not on PyPI | `sequential-thinking-mcp` |
| `globalping` | OAuth cannot complete non-interactively, so it warned on every tool load | disabled |

A null server entry (`time:`) also crashed `hermes mcp list` with
`TypeError: argument of type 'NoneType' is not a container`, so the list
of every other server never printed.

**"Enabled" is not "connected".** `hermes/scripts/mcp_doctor.py` now
spawns each server the way Hermes does, performs the initialize
handshake and lists the tools it really exposes. Current state: **18
live, 197 tools, 3 disabled, 0 dead** (http servers are not stdio
testable and are reported as such, never as dead).

`hermes/scripts/mcp_call.py` calls any tool on any server from the CLI,
which both proves the server works and gives immediate access to tools
fixed mid-session - the desktop only rebuilds its catalog at session
start.

### A verifier that fails is not a verifier

The first version of the doctor reported every server as dead, including
`throne`, which starts perfectly. The bug was in the doctor:
`init.serverInfo` does not exist in the Python SDK (it is
`init.server_info`). The control - a server already known to work - was
not run, so the harness bug looked like a system failure. **Always run a
known-good control before believing a negative result.**
