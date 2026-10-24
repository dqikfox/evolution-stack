---
name: research-fanout
description: Use when fanning out research to parallel subagents.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, delegation, fan-out, subagent, write-first, transcript-recovery]
    related_skills: [hermes-agent, plan]
---

# Research Fan-out — parallel subagents that actually deliver

When dispatching 5–15 subagents in parallel for research tasks (writing reports
to disk, gathering data, building artifacts), several failure modes repeat.
This skill captures the four patterns that turn a 50%-success-rate fan-out
into 90%+.

## When to Use

User signals:
- "Research [N topics] and write a report on each"
- "Compare [competitor A] vs [B] vs [C]"
- "Build a market analysis / pricing study / hardware teardown / IP landscape"
- "Spin up agents to help you complete the work"
- The user mentions a count ("10 sub-agents", "5 research streams")

Don't use for: single-file edits (just do them inline), tasks that need user
interaction (subagents can't ask questions), work shorter than ~60 seconds
(delegation overhead exceeds the work).

## The four failure modes (and their fixes)

### 1. Subagent "fails" but the file is already on disk

A long-running research subagent (10+ minutes, many API calls) reports
`status=failed` with `Connection error`, but the `write_file` call had already
returned success minutes before the connection died. The agent's tool result
says "failed"; the artifact is real.

**Always verify on disk before declaring loss.** Read the path the agent was
supposed to write to and check size + content. If the file exists with the
expected line count, the work is done — the connection failure is a transport
issue, not a work failure.

```python
import os
p = r"E:\research\lummings\01_competitors\competitors-2026.md"
if os.path.exists(p) and os.path.getsize(p) > 10000:
    print("ARTIFACT ALREADY EXISTS — agent failure was transport, not work")
else:
    # re-dispatch with the partial transcript data
    ...
```

### 2. DDG search backend times out → all searches retry → connection dies

The default `web_search` backend (DuckDuckGo) returns 15s timeouts on long
research subagent sessions. After 3 retries per query, the whole subagent
dies. Symptoms: `Connection error. API call failed after 3 retries`.

**Mitigation:**
- Tell the subagent in its prompt: "If `web_search` times out, use
  `web_extract` or direct `curl` to that URL. Do NOT loop on the same
  failing query."
- Or: pre-fetch data in the parent, pass it inline in `context`, and tell
  the subagent to write the file first, then enrich.
- If the subagent still fails, the partial transcript at
  `C:\Users\KING\AppData\Local\hermes\cache\delegation\live\deleg_<id>\task-N.log`
  contains every successful search result. Extract from there and write the
  report yourself, or re-dispatch with the data pre-loaded.

### 3. Long transcripts push the agent over its context budget

A 15-minute research task accumulates thousands of tokens in search-result
snippets. The agent may die before reaching `write_file` because it ran out
of context for the tool call.

**Two fixes, choose by task:**

- **WRITE-FIRST PATTERN**: tell the subagent "write the file with a complete
  skeleton using what you have, THEN keep researching and refining." The
  skeleton write happens early, before context fills. If the agent dies, you
  have a partial report.
- **PUSH-DOWN PATTERN**: do the broad searches in the parent context, then
  dispatch subagents with the search results already inlined in `context`.
  The subagent's job becomes "write the report from this data," which is
  cheap and reliable.

### 4. Sibling-subagent edits collide when writing the same file

Two subagents dispatched for "research X" and "research Y" both want to write
the same index file. Last write wins; first is gone.

**Give every subagent a UNIQUE output path.** If they need to share a file
(e.g. INDEX.md), have only one write it and have the others leave it alone.
Verify uniqueness with `set([task['goal'] for task in tasks])` before
dispatching.

## The re-dispatch template

When a subagent fails after partial research, re-dispatch with the partial
transcript embedded in `context`. This converts a 50%-done failure into
a 90%-done success:

```
A previous subagent collected research data for [TOPIC] but failed to write
the file before its connection died. The partial search results and tool
calls are preserved in the live transcript at:
  C:\Users\KING\AppData\Local\hermes\cache\delegation\live\deleg_<id>\task-N.log

Your job: WRITE THE FILE FIRST using the partial data. Then enrich with 1–2
final searches. Do NOT spend more than 5 minutes on additional searches —
write the file with what you have.

Key data already gathered (cite the transcript):
- [list 5–10 key data points with sources]
- [explicit instruction: "write a complete report using these facts; cite
   each; flag anything that needs verification"]

Constraints:
- Output path: [exact absolute path]
- Specificity: every numeric claim cites a URL with access date
- Honesty: flag "data not available" rather than fabricate
- Time: 10–15 minutes max
- Save early with `write_file` — partial is better than none
```

## The dispatch context shape that survives partial failure

Three things every research-fanout subagent prompt needs:

1. **Output path** — explicit absolute path, repeated twice
2. **Write-first directive** — "write the file with a complete skeleton early,
   then refine; partial is better than none"
3. **Citation expectation** — "every numeric claim cites a URL with access
   date; flag 'data not available' rather than fabricate"

Add these three things and the success rate goes from ~50% to ~90% on long
research tasks.

## How to decide fan-out size

| Task complexity | Fan-out count | Why |
|---|---|---|
| Quick research (5-10 sources) | 1 | Overhead exceeds work |
| Topic deep-dive (10-30 sources) | 1 focused | One agent can handle it |
| Multi-domain landscape (10-15 topics) | 5-10 in parallel | Coordination cost now worth it |
| "Research everything about X" | 8-12, each with a narrow slice | Each fits in context |

For 5+ parallel subagents, set `delegation.max_concurrent_children` to a value
that fits the task — default 3 is too low for fan-out. Check it via
`hermes config get delegation.max_concurrent_children`.

## Pitfalls

- **Trust the file, not the status field.** A "failed" subagent with a
  delivered artifact is a success.
- **Never assume the second attempt will succeed where the first failed.**
  Re-dispatch with the same prompt and the same backend will fail the same
  way. Embed the partial data in `context` and require write-first.
- **Don't read the partial transcript to write the report yourself when
  you can re-dispatch cheaply.** Re-dispatch with the data pre-loaded; let
  the subagent do the synthesis. The parent loop is for orchestration, not
  long-form writing.
- **Watch for sibling collision.** Two subagents both writing
  `INDEX.md` = lost work. Assign unique paths.
- **Subagents can't ask questions.** Don't dispatch research tasks that
  require a decision the parent hasn't already made.

## Live transcript recovery

Successful and failed subagent transcripts land at:
```
C:\Users\KING\AppData\Local\hermes\cache\delegation\live\deleg_<id>\task-N.log
```
Each is append-only. Use `tail -50` to peek, `read_file` to recover the
search results, or `execute_code` with regex to extract specific data
points before re-dispatching.
