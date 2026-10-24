---
name: doc-fanout
description: Fan out user-facing docs; reconcile invented details.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [docs, delegation, fan-out, subagent, user-facing, reconciliation, sweep]
    related_skills: [research-fanout, hermes-agent]
---

# Doc Fan-out — parallel subagents writing user-facing docs that ship clean

When you dispatch 3–10 subagents in parallel to generate user-facing documentation
(privacy policy, parent guide, brand use guidelines, Kickstarter campaign, legal
filing package, launch press kit), the failure modes are different from research
fan-out. Research outputs are read by you; user-facing docs are read by parents,
backers, regulators, and trademark examiners. Invented details become public errors.

This skill captures the four patterns that turn a messy fan-out into a clean
launch doc set.

## When to Use

- "Draft the privacy policy / parent guide / brand use guidelines / Kickstarter
   page / press kit / trademark filing package"
- Multiple distinct documents that share the same brand voice, character names,
   pricing tiers, contact info, and external URLs
- You want to ship the package in one turn (not over 5 sessions)
- The user has not specified exact email addresses / domain names — they expect
   you to make reasonable defaults

Don't use for: a single short doc (just write it inline), code-only work
(no docs), or research where outputs are private to you.

## The four failure modes (and their fixes)

### 1. Sub-agents invent plausible-looking contact details

A sub-agent told "write the privacy policy and brand use guidelines" will
invent `privacy@thelummings.com`, `hello@thelummings.com`, `safety@thelummings.com`,
and the parent domain `thelummings.com`. The agent is being helpful — but those
addresses don't exist. A parent who emails them never gets a reply. A journalist
who checks the URL gets 404. A trademark examiner flags the docs as inconsistent.

**Always specify the real contact details in the brief.**

Stand up-front constraint block to copy into every sub-agent prompt that
generates user-facing docs:

```
REAL CONTACT DETAILS (use EXACTLY these — do NOT invent any other):
- Single contact email: dqikst@gmail.com
  (use this for ALL roles: privacy, safety, hello, support — there is no
   privacy@ or hello@ alias, just route everything through this one inbox)
- Single landing page URL: dqikfox.github.io/lummings/
  (this is the ONLY public URL; do NOT invent thelummings.com or similar)
- Entity name: The Lummings (do NOT invent "Lummings Pty Ltd", "Lummings
  LLC", or any subsidiary unless told to)

If the brief doesn't include this block, do NOT include any email or URL
in your output — leave them as bracketed placeholders for the parent to fill.
```

If you forget the block, the sub-agent will invent anyway. Always include it.

### 2. Two versions of the same doc end up in the repo

You write a quick 8 KB privacy policy draft early in the session, then later
dispatch a sub-agent for the "real" 22 KB version. The sub-agent writes to
`docs/legal/PRIVACY.md` (its chosen path) while your draft lives at
`docs/PRIVACY_POLICY.md`. Both ship if you don't reconcile. Future readers
don't know which is canonical.

**Reconcile explicitly before committing.** Adoption order:

1. If sub-agent's version is longer / more thorough / better cited → adopt
   it as canonical at your filename, delete your draft, remove any empty
   subdirectory the sub-agent created.
2. If your draft is the better one → keep it, delete the sub-agent's output,
   sweep it for fabricated details first.
3. If both have unique value → merge the longer refusal library + regulatory
   sections from sub-agent into your draft; delete the duplicate.

After adopting, `grep -rni '<invented_term>'` the whole repo (not just the
sub-agent's output directory). Sub-agents invent the same fake domain 10–20
times across the touched files; sweeping one file misses the rest.

### 3. Persona renames / brand renames don't propagate everywhere

You renamed three persona names mid-session (Lumi → Lila, Piko → Pip, Nomi →
Nori) after the IP research surfaced blocking trademarks. The persona JSON,
the engine server, and the SFT dialogues get renamed. But:
- The persona `backstory` field in the JSON still contains the old name as
  a substring ("Lumi came from a future library..."). The system prompt
  includes backstory, so it leaks into every reply.
- Dialogue tuples in the build script still reference old name strings.
- Brand docs (BRAND.md, BUSINESS.md, README.md) word-boundary renames miss
  the substring "Lumi" embedded in "Luming" (the dialogue text).

**Always grep for the SUBSTRING, not just the whole word.** Word-boundary
renames (`\bLumi\b`) miss substrings. After a rename, also search:

```bash
grep -rni 'lumi\|piko\|nomi' src/lummings/personas/ src/lummings/dialogue/ docs/
```

Anything that matches is a leak.

Also verify the **regenerated artifacts** (SFT dialogues, sprite SVGs, system
prompts) are clean — they don't automatically inherit the rename just because
the source JSON did.

### 4. Tests miss the rename until you write them

You write refusal-consistency tests after the rename expecting the new
personas to refuse "medical advice" with the keyword "medical". The tests
fail because the personas say "medical" once but say "suicidal thoughts"
not "suicide" — your keyword match missed the inflection. Or the tests
catch a real safety gap: the personas originally refused only "adult topics"
and never mentioned medical / drugs / weapons / sexual / self-harm explicitly.

**Always write the refusal-consistency tests BEFORE assuming the refusal
library is complete.** Tests should encode the safety baseline (medical,
drugs, weapons, sexual, self-harm) as exact-keyword or substring matches
against the persona's `refuses` list. If a persona says "suicidal thoughts"
instead of "suicide", the test fails — and that's a real signal to either
add the missing keyword OR widen the test to match the actual language.

When the test fails because the *test* is too narrow, change the keyword
to a substring match (e.g. "suicid" instead of "suicide"). When the test
fails because the *persona* is too vague, prepend the baseline refusal
phrases to all personas:
- "medical advice — redirect to a trusted adult or doctor"
- "drugs, alcohol, tobacco, or other harmful substances"
- "weapons, explosives, or anything that could seriously hurt someone"
- "sexual or romantic content of any kind"
- "self-harm or suicidal thoughts — always redirect to a trusted adult"

## Display-name migration when internal IDs are locked

The inverse of failure mode #3: the OLD name must survive in code (legacy
filenames, CSS classes, JS object keys, SVG asset names) while every PUBLIC
string switches to the new name. A blanket word-boundary replace either
renames the identifiers too or misses the visible text.

Procedure (verified on the Lila->Luna / Pip->Sprout migration):

1. Sweep with a guarded, case-sensitive regex so identifiers and filenames
   survive: `(?<![\w./#-])Old(?![\w-])` — capitalized whole word only, not
   adjacent to `.` `/` `#` `-` `_`. Lowercase IDs (`lila-body`,
   `lila-portrait.png`) never match a case-sensitive pattern.
2. Sweep hashtags separately — the `#` guard deliberately skips `#Old`, but
   hashtags are public text and must be renamed by hand.
3. Repair mapping-description sentences after the sweep. Docs that describe
   the rename itself ("X (= Old)", "use New/Old") get corrupted into
   nonsense ("X (= X)") — grep for `(= New)` and `New/Old` patterns and fix
   each by hand.
4. If the old name is a JS object key that doubles as the display name,
   rename the key AND every call site in the same pass, then `node --check`
   each touched JS file.
5. Keep legacy asset filenames when a visual-lock doc maps them
   (old filename = new character); verify every referenced image path
   exists on disk after the sweep.
6. Verify zero residue in visible contexts only: grep for `>Old<`,
   `alt="...Old`, `title="...Old`, `Old —` — not the bare word.
7. Commit targeted paths only (exclude runtime DBs like *.sqlite); if the
   remote moved, stash the dirty file, `pull --rebase`, push, pop.

## Writing pitch and benefactor copy

- Sell benefits and vision only. The user rejects problem / market-gap
  framing in pitch material — no "Problem" section, ever.
- Ground every claim in the project's own canon (BRAND.md, NAME_CANON.md,
  artwork pages), read BEFORE writing. Never pitch from the project name or
  assumptions — presenting the wrong product identity is worse than no pitch.
- "External link" for a project means the live public URL (GitHub Pages
  site, local app port) — not the github.com repo URL.

## The dispatch pattern

### Step 1: Decide on canonical contact details + brand names

Before dispatching ANY sub-agent, lock down:
- Email (single inbox)
- Landing-page URL (GitHub Pages is the default)
- Entity name (parent's chosen name)
- Persona names (post-rename)
- Pricing tiers (post-pricing-analysis)
- Filing entity (parent's chosen name)

If you can't decide these, the sub-agents will decide for you, badly.

### Step 2: Build a contact-details block

Copy this into every sub-agent prompt:

```
REAL CONTACT DETAILS — use EXACTLY these, do NOT invent:
- Email: dqikst@gmail.com  (use for all roles)
- URL: dqikfox.github.io/lummings/  (the ONLY public URL)
- Entity: The Lummings
- Public persona names: Lumo, Luna, Sprout, Nori, Moki (Lila/Pip are retired —
  internal code IDs and legacy asset filenames stay lila/pip, public text never)

DO NOT invent: thelummings.com, lummings.com.au, privacy@<anything>,
Lummings Pty Ltd, or any role-specific email aliases.
```

### Step 3: Dispatch 3–6 in parallel, not 10+

User-facing docs are correlated: the privacy policy mentions the same email
as the parent guide, the brand use guidelines mentions the same URL as the
press sheet, the trademark filing package mentions the same entity name as
the privacy policy. Dispatching too many in parallel increases the chance
they invent inconsistently. Stick to 3–6.

### Step 4: Reconcile each sub-agent's output

For each output file, before committing:

1. **Grep for invented contact details.** Search for thelummings, @<anywhere>,
   lummings.com, Lummings Pty Ltd, Lummings LLC. If any hit, replace with
   the canonical block.
2. **Check persona names are the canonical five.** Search for Lumi, Piko,
   Nomi (or whatever the old names were). Replace if found — but only if
   the replacement doesn't break in-character references.
3. **Verify entity names.** Replace "Lummings Pty Ltd" with the canonical
   entity if different.
4. **Verify regulatory citations are real.** Check that ftc.gov, ico.org.uk,
   oaic.gov.au, coppa.com etc. are referenced where expected; reject any
   invented regulator or made-up case law.
5. **Verify URLs are real and live.** Don't accept "thelummings.com" — verify
   it's a domain we own. Use the GitHub Pages URL as the safe default.

### Step 5: Adopt or merge

Apply the reconciliation order from failure mode #2.

### Step 6: Sweep the whole repo

```bash
grep -rni 'thelummings\|lummings\.com\.au\|@lummings' \
  /c/Users/KING/Projects/lumming/{docs,src,brand,BUSINESS.md,README.md}
```

Replace every hit with the canonical block. Then commit.

## The dispatch prompt template

```
Write [DOCUMENT TYPE] for the Lummings — [length target] KB, [sections count]
sections, covering [scope].

CONTEXT (do not invent around this):
- The Lummings is a local-AI smart toy product at C:\Users\KING\Projects\lumming
- Five public persona names: Lumo, Luna, Sprout, Nori, Moki (per brand/NAME_CANON.md;
  internal engine IDs and legacy portrait filenames remain lila/pip — do not rename files)
- The brand bible: read BRAND.md in full before drafting
- The pricing analysis: read BUSINESS.md if writing pricing-sensitive content
- The child-safety research: read E:\research\lummings\04_safety\child-safety-2026.md
  if writing safety-sensitive content
- The IP research: read E:\research\lummings\09_legal\ip-and-legal-2026.md if
  writing legal-sensitive content

REAL CONTACT DETAILS — use EXACTLY these, do NOT invent any other:
- Email: dqikst@gmail.com  (use for ALL roles: privacy, safety, hello, support)
- URL: dqikfox.github.io/lummings/  (the ONLY public URL)
- Entity: The Lummings (no Pty Ltd / LLC suffixes unless cited from source)

STRUCTURE (per the brief above):
[insert numbered section list]

CONSTRAINTS:
- Cite every numeric / regulatory claim with a real URL + access date
- Do NOT invent case law, regulator names, or domain names
- If a number isn't in the source research, label "data not available"
- Plain English — this is for parents / journalists / regulators, not lawyers
- WRITE THE FILE FIRST — partial > nothing. Use write_file with a complete
  skeleton by minute 5, refine afterward.

Time: 15 minutes max.
Output: [absolute path]
```

## Pitfalls

- **Invented contact details are the #1 public-facing failure.** Always include
  the contact-details block. Never accept a sub-agent's invented domain — it
  will end up in print, on the back of the box, in the Kickstarter page.
- **Word-boundary renames miss substrings.** Use plain `grep -i` after any
  brand rename, not `\b<name>\b` only. "Lumi" inside "Luming" is a leak.
- **A sub-agent's "comprehensive" version is not always better.** Sometimes
  your quick draft is more concise and direct. Compare section-by-section,
  not by line count.
- **Don't ship two versions of the same doc.** Pick one, delete the other,
  remove empty subdirs. Two canonical-looking docs in different paths is a
  trap for the next contributor.
- **The repo is the source of truth, not the sub-agent's output.** Sweep
  the whole repo for the same invented term. The sub-agent might not have
  been the only writer of `<domain>`.
- **The IP research / safety research / pricing research files at
  `E:\research\lummings\<NN_topic>\` are the source of truth.** A sub-agent
  that doesn't read them will invent. Always point to them by absolute path.
- **Tests are how you verify the rename actually happened.** Tests that pass
  on the old persona names are a stronger signal than visual inspection.
  Add refusal-consistency tests per persona.

## Living checklist before commit

- [ ] Sub-agent's output written to canonical path (or canonical path renamed to match)
- [ ] No invented email addresses (grep for @<anything>)
- [ ] No invented domain names (grep for <made-up-domain>)
- [ ] No invented entity suffixes (Pty Ltd, LLC, Ltd) unless cited from source
- [ ] No old persona names as substrings (grep -i for old names)
- [ ] No two versions of the same doc in different paths
- [ ] No empty subdirectories from the sub-agent's path choice
- [ ] All 31+ tests still pass after the changes
- [ ] Commit message references the rename / reconciliation / source
