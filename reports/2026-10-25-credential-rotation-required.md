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
  GitHub API — the old content is not fetchable.
- The corrected history sweep reports **0 findings** across TESSERACT,
  Pixel, Lummings, Pathway and NEXUS.
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
