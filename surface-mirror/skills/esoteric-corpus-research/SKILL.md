---
name: esoteric-corpus-research
description: Use when decoding esoteric corpora into tiered logs.
---

# Esoteric Corpus Research

For archival study of esoteric/alchemical/occult source material: Telegram study-group exports, scanned treatises, historical figure dossiers, transmission-chain mapping. Goal is a *living study log in the source folder* plus verifiably-tiered conclusions.

## Procedure

1. **Inventory the corpus first.** List all files (chat exports, PDFs, images). For Telegram Desktop HTML exports: `<div class="text">` holds messages, `from_name` holds sender; grep -ioE with wide context `{0,150}term{0,250}[^<]` works well; count senders by extracting from_name with python collections.Counter.
2. **OCR/extract PDFs to text** into a `_extracted/` subfolder beside the sources (pymupdf: `'\n'.join(pg.get_text() for pg in doc)`). Count every deckname/code term across the corpus — occurrence density shows which text is the operating manual vs the theory text (the densest file is the master).
3. **Build a coded-term table** (codeword → property/function, NOT assumed substance). Note when a term's count is **zero in the primary source** — deliberate absence is itself evidence of a cover-name.
4. **Maintain ONE cumulative study-log file in the source folder** (user's example: "HITCHYZ OPUS.md" beside the corpus). Append numbered Parts; anchor patches to existing sections; cross-reference by §number. Never scatter findings across new files.
- **Pull the historical chain** via web_search (DuckDuckGo backend here cannot web_extract — curl Wikipedia with a Mozilla UA to $LOCALAPPDATA/Temp and strip tags with python). Verify transmission links figure-to-figure; map them as an ASCII chain in the log.
- **Verify the presence of a 'mass balance' check in every step.** A failure to account for mass loss (sublimation/volatilization) results in phantom transmutation claims; always search for weight logs alongside reagent additions to find the true $\Delta m$.
- **Prioritize residue analysis over substance identification.** Identifying the name of an ingredient is secondary to tracking its physical footprint ($\vec{V}_{\text{op}}$); focus on what remains vs. lost via chromatography or sublimation patterns much more than identifying chemical species names.
7. **Demystify on request** — but keep the audit trail (see tiering below).
8. **Build a queryable knowledge graph.** After extracting structured data, model it as nodes (people, texts, materials, experiments, concepts, scientific facts) and edges (influence, authorship, co-occurrence, falsification, evaluation). Store the graph as JSON with a `nodes` and `edges` array, then generate RDF-style triples (`subject → predicate → object`) for ingestion into local knowledge systems.
9. **Index the graph in NEXUS CORE.** Convert the graph to a Markdown note with frontmatter and import it via `importers.markdown.import_single_file` from the NEXUS core path; also write a JSON triples copy to `E:/ultron-memory/nexus-core/ingest/<topic>/` so future reindexing can pick it up. See `references/knowledge-graph-and-nexus-ingestion.md` for the exact import sequence and file layout.
10. **Maintain a live progress ledger.** Because much of this work happens in background tool calls, publish a concise status table at the end of every major turn: task ID, phase, status, and verifiable evidence path. The user must be able to audit where results live without scrolling the chat.
11. **Verify a pasted document-ID list against the local corpus before treating any ID as real.** When a paste enumerates several document IDs grouped under a topic (e.g. "all CIA-RDP-XXXX files" or "all NIST torsion papers"), the local OCR/text corpus is the first verification surface — not the public archive. Procedure: (a) `ls <corpus_root>` to enumerate what is actually present; (b) `grep -li "<key_term>" *.txt` over the local corpus for each cited term (Tesla, Pavlita, Akimov, Tachyon, etc.); (c) for each cited ID, file-search `<exact_id>` and grep the local copy for the ID string itself; (d) record verified / partial / absent status with the exact file path or absence note; (e) my earlier "fabricated" flag is too aggressive — when the local corpus has a real document I had previously dismissed, the audit must correct that. The rule: **never trust a paste's enumeration; verify against the local corpus first, then escalate to external archives only for IDs the local corpus does not contain.** See `references/verified-id-audit.md`.

12. **Apply a tier-A–D predatory-journal audit to any "published paper" cited as evidence.** When a paste or corpus source cites a peer-reviewed paper as supporting a contested claim, three signals warrant a journal-level audit before the paper's content is integrated: (a) the paper is published in a journal on Beall's List of Predatory Journals / Publishers (the 2013–2017 Beall list at `beallslist.weebly.com` / archived copies; the *Charleston Advisor* review; the Retraction Watch database); (b) the journal advertises a fake impact factor (SJIF / CiteFactor / Cosmos Impact Factor) that is not a Thomson Reuters / Clarivate JCR figure; (c) the journal promises a 24-hour review window. When any of these signal, the paper is **not citable as peer-reviewed evidence** — its content may still be examined as a primary-source record of the author's *claims*, but the claims themselves are Tier C / unproven, not Tier B / strong interpretation. **A 57%+ closed-community self-citation rate** in the paper's reference list (e.g. 8 of 14 references authored by the same author or by members of the same subfield) is a fourth red flag. See `references/verified-id-audit.md`.

13. **Encrypted / locked sources get the ironclad stop rule.** When a source file in the corpus is encrypted (pymupdf open() throws "file is encrypted") or web-walled (Cloudflare captcha, JS-gated, paywall), do not invent a working method. State: "encrypted, cannot extract text — would require decryption key or alternate unencrypted source." Document the blocking observation in the audit, then **move on to the next candidate source**. The lesson: an unresolved source is recorded as blocked, not narrated as if it were accessible. **A 21.8 MB encrypted PDF or a Cloudflare-captcha HTML page is a negative result, not a deliverable.** See `references/verified-id-audit.md`.

## Standing rules for THIS user

- The study log lives IN the corpus folder with a grand name the user picks; make it dense (tables, verbatim quotes, cross-reference tables), styled like a grimoire dossier, not a lab report.
- **User pushes research forward with short commands** ("decode", "proceed", "keep doing research", "KEEP COLLECTING EVIDENTIARY DATA", "LOOK FOR EVIDENCE", "CONTINUE", "collect data should be the focus"); don't ask scope questions — expand to the next obvious stratum (deeper history, older sources, missing links, contemporary critics). Each new stratum is one focused batch with: tier-1 source identification, primary-text extraction, page-render evidence, dossier write, work-log patch, opus-index patch. Don't stop to ask "what next?" — just decide and execute. The standing pattern: when the user says one of these, deliver a complete, named dossier file plus the central-study-log patch in the same turn; never produce a "what would you like next?" question.
- **User explicitly wants contemporary counter-evidence, not just supporting evidence.** When the user says "LOOK FOR EVIDENCE" or "KEEP COLLECTING", they mean both supporting AND opposing evidence. A corpus that documents only its supporters is not audit-ready. Mine the corpus for: (a) contemporary critics (Boyle, Royal Society, scientific establishment), (b) modern scientific assessments (PNAS, Nature, peer-reviewed reproductions), (c) 14c Latin witnesses that may diverge from the corpus's 17c emphasis. Document each as a tier-1 witness in its own dossier.
- **When the user says "plain English" or "anyone can understand," produce a parallel plain-English dossier, not a summary.** The plain-English dossier is the same depth as the technical dossier, with every Latin term translated, every technical term explained, every tier-discipline claim labeled. See `alchemy_forensics/references/plain-english-dossier-template.md` for the section structure.
- User explicitly wants outside-the-box historical tracing (to Egyptian/pharaonic roots); ancient bench processes and their modern lab replications are prized evidence.
- **Default to skeptical, science-first framing.** Strip mysticism on request: translate coded terms to chemical/physical mechanisms, provide real probabilities or confidence tiers, and never present a modern group doctrine as historical fact. Frequency-count primary sources against chat/group commentary before accepting any term as central to an author's system.

## Evidence tiering — MANDATORY (peer-review correction)

Claims in this field collapse numerology into discovery constantly. Tag EVERY interpretive claim:
- **Documented** (present verbatim in primary text, with source)
- **Strong interpretation** (defensible inference, labeled as such)
- **Unproven** (pattern-fit, hypothesis — labeled with a test plan, never presented as solved)

## Pitfalls

- **Never present a numerological pattern as a solved law.** A symbolic calendar arithmetic (e.g. 360×7) is not a physical constant until it predicts held-out data. Present such findings as candidate frameworks with an explicit falsification protocol.
- **Test pattern hypotheses mechanically before announcing them.** Build the full duration/quantity dataset, try all candidate transforms, and report the GCD/divisibility split. The values that REFUSE the model are usually the empirical data: sacred-arithmetic fits are the frame, non-fits are the bench observations.
- **Classify observations by provenance independence.** If author B copied author A, identical numbers are ONE observation, not two confirmations. A single transmission chain can never provide an out-of-sample test — say so.
- **Train/holdout rule:** derive downstream predictions from the fitted rule BEFORE comparing to those downstream values; fitting a rule to all observations then claiming it predicts them is circular.
- **Codewords are context-shifting, not fixed chemicals.** Method is symbol→author→text→context→operation; a glossary from the same tradition (e.g. Newton's Index Chemicus) demonstrates the same word flips referents between authors. Never publish a symbol→substance table without author/context qualifiers.
- **Preserve exact technical terms from sources** — sublimation ≠ distillation; when quoting Newton/Philalethes keep their verb. Modernizing terms silently invents process claims.
- **Ratios and timings must be traced to specific passages.** Manuscripts contain multiple conflicting numbers (e.g. 1:29→864 vs 1:2); never blend them into one clean rule.
- **Demystification needs a status disclaimer.** When rendering a coded recipe in plain modern language, label what is documented skeleton vs reconstructed hypothesis vs unknown (matter identity, proportions). A clean kitchen recipe that hides its uncertainty is worse than none.
- **A modern lab replication of an ancient recipe is strong grounding** — search for replication studies (e.g. archaeological-metallurgy journals) before deciding an old process was purely symbolic.
- **Interpret coded phrases as instrument-free measurements.** 'Sealed pot' = pressure control, 'heat that chars bran' = a temperature band, color stages = colorimetric endpoints. Map each phrase to its control function before treating it as poetry.
- **A term with zero primary-text hits and dozens of group-chat hits is a modern retrojection, not historical doctrine.** Dump per-source counts before asserting centrality; label the result explicitly.
- **Document contemporary critics as tier-1 witnesses, equal in weight to supporters.** When a contemporary scientific critic (e.g. Boyle's *Sceptical Chymist* 1661) explicitly attacks the corpus's theoretical framework, the counter-evidence is a first-class deliverable, not a footnote. A corpus that documents only its supporters is not audit-ready. The counter-evidence dossier is the audit trail for the standing position that transmutative claims are unproven. See `alchemy_forensics/references/counter-evidence-and-three-way-dialogue.md`.
- **A 17c recipe that uses a reagent the 14c Latin standard explicitly rejects is a 17c innovation, not a 14c transmission.** When Petrus Bonus (1320) explicitly criticizes arsenic and sulphur as solvents for transmutation ("what have those substances to do with metals?") and the corpus's R01 Philalethes (1654+) uses arsenic heavily, the divergence is a source-critical finding. The 17c author is innovating, not transmitting the older tradition. Document the divergence; do not silently treat the 17c text as a faithful 14c continuation.
- **Never leave results only in chat memory.** Write every significant finding to a durable file in the corpus folder, then report the exact path. Chat text is transient; disk records are the audit trail.
- **Progress must be trackable.** If the user asks "where are your results?" or "I can't track your progress," respond with file paths, counts, and a status table — not a narrative summary.
- **Do not assume NEXUS CORE ingests raw JSON.** The markdown importer is the live path; the `ingest/` directory is the staging path. Use both; confirm the note ID/slug after import.
- **A knowledge graph built on guessed coefficients is computational theater.** If base kinetic data is missing, run parametric sensitivity sweeps and label outputs as bounded scenarios, not single predictions.
- **Catalogs of "primary source" identifiers in chat pastes are fabrication-prone.** When a
  paste enumerates several document IDs grouped under a single topic (e.g. "all STARGATE
  files on AI/NN/AC" or "all CIA torsion documents"), at least one is usually a sibling
  of a real ID that does not itself exist in the indexed subset. Treat every ID as
  unverified until the live catalog returns it. For CIA: `/readingroom/search/site/<ID>`
  lists the indexed subset; a 302 redirect to the reading-room home means the ID is not
  indexed, withdrawn, or fabricated. For other archives (Internet Archive, HathiTrust,
  Pergamon, etc.) use the catalog metadata endpoint. Never treat a pasted URL as proof the
  document exists; verify, log verified/unverified status, and flag unverified IDs as
  fabrication candidates before any later citation work.
- **The local OCR/text corpus is the first verification surface, not the public archive.**
  The local corpus at e.g. `C:\Users\KING\Documents\ADVANCED RESEARCH\ocr_full\` may
  contain the exact document the paste cites, OR it may be silent. Direct `ls` + `grep`
  on the local files is faster, more reliable, and more auditable than the public
  archive. The audit table records the local finding, then escalates to public archives
  only for IDs the local corpus does not contain. **Trust the local grep before
  trusting a paste's enumeration.**
- **Beall's-list and fake-impact-factor signals are an audit gate, not a stylistic
  objection.** A paper in a journal advertising SJIF / 24-hour review / rapid publication
  is not citable as peer-reviewed evidence. Continue the audit — extract the paper's
  claims as a primary-source record of the author's *claims* — but do not let the paper
  content upgrade from Tier C (an unverified claim) to Tier B (a peer-reviewed finding).
  The 57% closed-community self-citation rate is the threshold signal: a paper where the
  same author / same subfield wrote the majority of references is self-validating, not
  independently verified.
- **Encrypted / locked source files are blocked, not pending.** When a PDF in the corpus
  cannot be opened (pymupdf "file is encrypted") or a web source is JS-walled
  (Cloudflare captcha, paywall, JS reader), the audit records the blocking observation
  and **moves on**. Do not narrate the failure as if the source were accessible. Do not
  guess at content. Do not present "I tried several things, none worked" as a workflow.
  An unresolved source is recorded as a single sentence ("encrypted, cannot extract
  text") and the next candidate source is approached.
- **Pseudo-attribution to famous medieval figures is endemic in 13-14c Latin alchemical
    corpus.** Texts like Speculum Alchemiae (the Mirror of Alchemy), Aurora Consurgens, the
    Rosarium Philosophorum, and the Latin works attributed to "Geber" are routinely
    pseudo-attributed to famous figures (Roger Bacon, Aristotle, Ramon Lull, Jabir ibn
    Hayyan). The 16c English translations often added *additional* false biographical
    details (e.g. "Roger Bacon, sometime fellow of Martin College and Brasen-nase College
    in Oxenforde" — there is no Martin College at Oxford). Verify attribution by checking
    the university-library catalog (Kassel `orka.bibliothek.uni-kassel.de` flags
    suspicious attributions with `(?)`) and the standard critical-edition series (e.g.
    the Warburg Institute surveys, Michela Pereira's introductions to the *Art aurifera*).
    Treat the *text* as a valid 13-14c alchemical document but hold its *attribution*
    separate; the doctrine is real, the author is not who the title page claims.

- **Heredoc with embedded single-quote in MSYS bash truncates the input mid-write.**
    When appending a markdown block to a file via `cat >> file.md << 'EOF' ... EOF` and
    the body contains an apostrophe (`'`) or a backtick (`` ` ``), the MSYS bash parser
    may close the heredoc early or report `unexpected EOF while looking for matching }'`
    even though the file content was *actually* appended successfully. Always verify
    the write landed by `tail -3 file.md` after the heredoc error, and switch to a
    Python `open(path, 'a', encoding='utf-8').write(content)` block when the markdown
    body has embedded quotes. The Python path is unambiguous: it writes the exact
    string, with no bash interpretation of the contents.
