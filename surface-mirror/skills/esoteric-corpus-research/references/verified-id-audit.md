# Verified-ID and Predatory-Journal Audit Procedure

When a paste, chat excerpt, or corpus source enumerates a list of "primary source" identifiers and claims they support a contested proposition, two audit gates apply: (1) does each ID actually exist in the local corpus, and (2) is the venue of any cited paper a legitimate peer-reviewed source. This file captures the procedure for both.

## When to use

- A user-supplied paste or chat message names several document IDs and presents them as a "verified paper trail" (Tesla, Pavlita, Akimov, Stargate, etc.).
- A user-supplied link to a paper is treated as supporting evidence for a contested claim.
- A corpus source claims "the literature shows X" without naming a verifiable paper.
- An encrypted or web-walled source blocks normal extraction.

## Procedure for ID verification

### Step 1: Enumerate the local corpus

The local OCR/text corpus at e.g. `C:\Users\KING\Documents\ADVANCED RESEARCH\ocr_full\` is the first verification surface. Direct `ls` is faster and more auditable than any public archive:

```bash
ls <corpus_root>/*.txt | sort
du -sh <corpus_root>
```

### Step 2: For each cited ID, file-search

```bash
ls <cited_id>* 2>&1   # returns "No such file or directory" if absent
```

Record verified / partial / absent status with the exact file path or absence note.

### Step 3: For each cited term, grep the local corpus

When the ID does not match, search for the named person / term:

```bash
grep -li "tesla\|pavlita\|akimov\|psychotronic\|torsion" <corpus_root>/*.txt
```

If zero matches: the cited material is **absent from the local corpus**. The audit escalates to public archives only for these absent IDs.

### Step 4: Audit the local file content for the cited claim

When the local file IS present, open the first 3,000 chars and verify the cited claim is actually supported. Example pattern:

```python
import pymupdf
doc = pymupdf.open(<local_pdf>)
print(doc[0].get_text()[:3000])
```

If the cited claim is not in the first 3,000 chars, the audit searches the full text:

```bash
grep -i "<claim_phrase>" <local_txt>
```

Record whether the cited claim is **directly supported**, **partially supported**, or **absent from the cited document**.

### Step 5: Build a verification table

| ID | Paste claim | Local corpus status | Cited claim supported? |
|---|---|---|---|
| CIA-RDP96-00789R002900420001-4 | "Nikola Tesla's Papers, ATSC/Wright Field" | **NOT in local corpus** | n/a |
| CIA-RDP96-00792R000600350002-2 | "DIA / psychotronics" | **NOT in local corpus** | n/a |
| CIA-RDP96-00789R002200150001-1 | "DACOS expert system" | **In local corpus** (SRI Stargate FY 1987, 90 pp.) | **YES**, partially correct |
| DOC_0000619182 | "Studies in Intelligence" | **In local corpus** (Vol 27 Spring 1983) | **YES**, but content is satirical |

The table is the audit's primary deliverable. Future agents cite the table, not the paste.

### Step 6: Correct earlier "fabricated" flags when the local corpus contradicts them

When a previous corpus dossier flagged an ID as "fabricated" and the local corpus has the real document, the new audit must explicitly say "earlier flag was wrong" and document the corrected finding. The earlier flag is in the corpus's persistent record; the correction is also in the corpus's persistent record. Future agents reading both learn the audit's progression.

## Procedure for predatory-journal audit

When the cited source is a paper (PDF / DOI), apply this audit BEFORE integrating the paper's claims as evidence.

### Step 1: Identify the journal

Look up the journal name, ISSN, publisher, and the journal's claims about peer review / impact factor. The journal's own website is the first source; cross-check against:

- **Beall's List of Predatory Journals / Publishers** (2013–2017, archived at `beallslist.weebly.com` and Internet Archive snapshots)
- ***The Charleston Advisor*** (Jeff Beall's reviews, e.g. 2013 vol 14(4))
- **Retraction Watch** (`retractionwatch.com`)
- **DOAJ** (Directory of Open Access Journals) — but note DOAJ inclusion is not a guarantee of quality
- **Sherpa Romeo** for publisher open-access policies

### Step 2: Apply the four red-flag signals

1. **Beall's-list hit.** The journal is on Beall's list. The paper is **not citable as peer-reviewed evidence**.
2. **Fake impact factor.** The journal advertises SJIF, CiteFactor, Cosmos Impact Factor, or any non-Thomson-Reuters/Clarivate-JCR metric. These are sold by predatory metric services.
3. **Rapid / 24-hour review window.** The journal promises review in 24–72 hours. Real peer review takes weeks to months.
4. **Closed-community self-citation >57%.** Of the paper's references, more than half are authored by the same person, by members of the same subfield, or by the same small set of authors that cite each other in a self-validating loop.

When **any** of the four signals fire, apply the gating rule below.

### Step 3: Tier discipline when a red flag fires

The paper is **Tier C / unproven** in the corpus's evidence framework, not Tier B / strong interpretation. The paper's content may still be examined as a primary-source record of the author's *claims*, but the venue does not confer peer-review credibility.

**Tier discipline table:**

| Audit outcome | Tier | Citation use |
|---|---|---|
| Beall's-list hit OR fake IF OR 24h review OR 57%+ self-cite | **Tier C** | Document author's *claim*; do not cite as evidence for the claim |
| None of the four | **Tier A/B per content** | Standard tier discipline applies |

### Step 4: Worked example — Pavlenko 2021 IJCR paper

**Title:** "Some evidence of consciousness existence in elementary particles"
**Journal:** *International Journal of Current Research* (IJCR), Vol 13, Issue 12, pp 19806-19810
**Venue audit:**
- IJCR is on Beall's 2013 *The Charleston Advisor* list: "a vanity press... Do not submit any papers to this journal."
- IJCR advertises "SJIF Scientific Impact Factor: 8.132" — fake metric.
- IJCR promises "decision on their manuscript(s) within 24 h of submission" per Beall.
- Self-citation: 4 of 14 references (29%) by the same author; 4 more by Akimov/Shipov/Smirnov in the same torsion community. **Total closed-community self-citation: 8 of 14 = 57%.**

**All four signals fire.** The paper is **Tier C / unproven**. The paper's 11 claims are examined as a record of the author's beliefs, not as peer-reviewed evidence for any of the 11 claims.

The audit does NOT say "the paper is wrong" or "the paper is fraud." It says the paper's venue does not confer Tier A/B status. The author may have done good work elsewhere; the *paper* in this venue is Tier C.

## Procedure for the encrypted / web-walled source stop rule

When a source file in the corpus cannot be opened:

| Symptom | Audit | Action |
|---|---|---|
| `pymupdf.open(<file>)` raises "file is encrypted" | Source is encrypted | **Record: "encrypted, cannot extract text." Move on.** |
| Web fetch returns Cloudflare captcha HTML (first 100 bytes are `<!DOCTYPE html>`) | Web-walled | **Record: "Cloudflare-walled, first 100 bytes are HTML captcha." Move on.** |
| Web fetch returns JS reader shell (no inner content) | JS-gated | **Record: "JS-gated, browser extraction required." Use browser tool if available, else move on.** |
| Web fetch returns paywall | Paywalled | **Record: "paywalled, no preview available." Move on.** |

**The rule is ironclad:** an encrypted / walled source is a single-sentence negative result, then the next candidate. The audit does NOT narrate the failure as if the source were accessible, guess at content, or recommend "try these workarounds in order" — because none of the workarounds is known to succeed. The audit just records the block and moves on.

## Pitfalls

- **Trusting a paste's enumeration over the local corpus.** The paste says "X, Y, Z" are all real; the local corpus may have only one. Verify first, trust the local grep.
- **Treating "the corpus has it" as "the cited claim is supported."** The local corpus may have the document but the cited claim may not be in the document. Always verify the cited claim is actually in the cited page.
- **Marking a paper Tier B on journal prestige alone.** A prestigious-sounding journal name (e.g. "International Journal of...") is not a quality signal. Beall's list, fake IF, rapid review, and self-citation rate are the actual signals.
- **Narrating encrypted-source failures as a workflow.** "I tried curl, then wget, then pdftotext with password" is not a deliverable. One sentence, then the next source.
- **Letting an earlier "fabricated" flag persist when the audit contradicts it.** The audit is the corpus's institutional memory; the audit's corrections are part of the institutional memory. Update the dossier, the WORK_LOG, the OPUS DATA INDEX, and the central study log.
