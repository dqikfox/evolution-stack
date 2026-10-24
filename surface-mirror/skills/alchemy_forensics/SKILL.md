---
name: alchemy_forensics
description: Use for chemical lineage reconstruction in historical alchemy corpora, including candidate-dossier comparison of recommended vs deprecated routes.
---

# Alchemy Forensics Workflow

Use this workflow to perform high-precision forensic reconstructions of historical chemical experiments (e.g., checking $\text{S}_n \to \text{S}_{n+1}$ continuity) by tracing reagent lineages and process continuity across provided corpora ($PDFs$ and $Telegram archives$). Pair with `historical-corpus-research` for corpus building, transcription capture, and falsification ledgers.

**References:** `references/codeword-operational-table.md` — standing map of corpus codewords (Eagle, Doves, Green Lyon, Dragon, etc.) to chemical operations, with established operational definitions and the recommended recipe-dossier JSON schema. `references/latin-collation-procedure.md` — when the corpus has both a Latin primary source and English translations, visually collate the Latin to settle translation ambiguities (e.g. *ac* = "and" vs. English "or").

## Procedure
1. **Identify Mass Anchors in Structured Data**: Search the `.json` archives (`.../corpus/*.json`) for specific numeric masses found in known experiment logs (e.g., `75`, `43`, `26`). Do not rely on PDF parsing for these numbers as OCR often fails on archaic symbols ($\mathfrak{Sb}$, etc.).
2. **Cross-Reference via Residue Fingerprints**: Use identified residue weights from one log entry as a 'fingerprint' to search other entries within the same archive for identical mass signatures of $\text{S}_{\text{residue}}$ or $\text{S}_{\text{sublimate}}$.
3. **Verify Procedural Continuity**: Look for shared thermal indicators (e.g., "red heat", "digestion") and chemical reagents in proximity to those masses to establish a chain of process rather than just substance identification.
4. **Analyze Visual Evidence**: If images contain bibliographic citations (e.g., `v. la Tourbe p.35`), treat them as *provenance clues* only; do not claim lineage until the source manuscript is identified via metadata/catalogue lookup.

5. **Capture browser-gated primary sources before analysis.** When an institution serves
   diplomatic/normalized transcriptions through a JS reader (e.g. Indiana University's
   Chymistry of Isaac Newton), open the reader URL with the browser tool, extract
   `document.body.innerText`, save the raw JSON, then regex-split on the reader's page
   markers. Do not rely on `requests`/`curl` for these pages; they are usually empty or
   redirect to a gateway. See `historical-corpus-research/references/js-gated-archive-extraction.md`
   for URL patterns and split regexes.

6. **Cross-check against modern chemistry.** Once a historical sequence is reconstructed,
   search the modern materials-science literature for whether the described effects
   (frequency-dependent electrodeposition, colloidal gold formation, piezoelectric mineral
   deposition, etc.) are reproducible. Use the result to decode coded terms and to demote
   claims that violate mass/element conservation or lack experimental support.

7. **Render PDF pages at 200 DPI for verification when OCR is uncertain.** PyMuPDF's
   `page.get_pixmap(matrix=pymupdf.Matrix(200/72, 200/72))` produces a high-resolution PNG
   suitable for vision verification. Workflow: locate target page via `pdfinfo` / grep on
   `pdftotext` output, render to `evidence/<source>-<printed-page>-pdf<leaf>.png`, then
   `vision_analyze` to confirm content. This catches OCR-misalignments, ink bleed-through,
   and stub pages that grep alone misses. Ink bleed-through from verso is the most common
   reason a rendered page is unreadable; record it as a *negative record* rather than
   retrying.

8. **When a corpus author compares two routes, document BOTH.** A 17c alchemical author
   who explicitly prefers one procedure over another (e.g. *"Some use X, which is tedious;
   the other way (which is most secret) we commend"*) is providing a source-critical
   finding. The recommended route is the operational core; the deprecated alternative is a
   historical survival of an older practice. Both routes aim at the same material identity
   (e.g. the same Sophick Mercury menstruum), so discrimination is by *yield, time, and
   apparatus*, not by *product*. Capture: recipe identification, author's explicit
   preference, yield/timing comparison, and the modern operational hypothesis for each
   route.

9. **Verse vs prose operational texts map to the same procedure.** When a corpus
   contains both a verse alchemical text (e.g. Marrow of Alchemy 1655 in stanzas) and a
   prose alchemical text (e.g. Sci-Hist MS 13 in Starkey's hand), the verse form is the
   literary surface and the prose form is the operational core. Operational equivalence
   should be ~80% or higher; expect the verse to substitute allegorical vocabulary for
   operational terms (e.g. "Souls" = active principles; "hill" = upper part of sealed
   vessel; "grosser matter" = residue). Three possible reasons for the verse form: veil
   (obscurity for secrecy), marketing (verse books commanded higher prices in the 17c
   book trade), or mnemonic (verse is easier to memorize than prose). Record which
   reasons apply in the dossier.

10. **Check pseudo-Bacon / pseudo-Aristotle / pseudo-Lully attribution in 13-14c Latin
    alchemical corpus.** Many Latin alchemical texts (Speculum Alchemiae / Mirror of
    Alchemy, Aurora Consurgens, Rosarium Philosophorum, etc.) carry 16c English
    translations with false attributions to famous medieval figures. The 1597 English
    translation of Speculum Alchemiae, for example, claims Roger Bacon was "sometime
    fellow of Martin College and Brasen-nase College in Oxenforde" — but no Martin
    College exists at Oxford. Verify the Latin original via the Kassel university
    library catalog (`orka.bibliothek.uni-kassel.de`) which flags suspicious
    attributions with `(?)`. Treat the text as a valid 13-14c alchemical document but
    hold its attribution separate.

11. **Check projection ratios for self-consistency with the claimed endpoint.** When an
    alchemical text claims a 1:N projection ratio, calculate the resulting alloy
    composition: if a 30% gold Elixir is projected at 1:1000 onto a base metal, the
    resulting alloy contains 0.03% gold, which is well below 17c assay thresholds for
    "pure gold". A projection ratio that is self-inconsistent with the claimed endpoint
    is a strong signal that the text is using "projection" in a different sense
    (philosophical tincture, surface alloying, hyperbolic claim). Hold the projection
    claim separate from the recipe identification per OPUS §0; do not promote the
    projection to the recipe as a stoichiometric claim.

12. **Build candidate dossiers that compare recommended vs deprecated routes.** When
    a corpus has multiple routes to the same product (e.g. R01 Sophick Mercury vs R03
    Diana's Doves), structure the dossier as a comparison rather than as isolated
    recipes. The schema that worked: candidate_id, question, intended_endpoint,
    witnesses, passages (each verified via page-render), materials_as_written,
    identity_hypotheses (≥3), ordered_operations, apparatus_conditions,
    quantities_units_repetitions, intermediates_and_stop_criteria,
    claimed_product_and_tests, statement_type, missing_critical_information,
    constraint_comparison (≥5), counterevidence, textual_status, identity_status,
    efficacy_status, next_discriminating_check. Place dossiers in
    `project-control/candidates/<R##>.json` and the narrative write-up in
    `research-YYYYMMDD-r##/DOSSIER_NARRATIVE.md`. Write JSON via Python `json.dump`
    when the data contains embedded quotes that break `write_file`'s escape-sensitive
    parser.

13. **Establish the chemical identity of named operations through primary-source
    comparison.** When a corpus uses a code-name (Eagle, Doves, Lyon, Dragon, Cadmus)
    with an unknown chemical referent, find the operational definition in the
    contemporary prose source. The Eagle, for example, is a *cohobation cycle* — one
    redistillation of the sulfur-charged acidic menstruum in a sealed vessel. Starkey's
    Sci-Hist MS 13 (Newton's hand copy) gives the operational definition: *"in diem
    dimidium Aquilam unam praeparare possum"* — half a day per Eagle, using vinegar +
    pure sea salt. This is reproducible with 17c apparatus and modern reagents. See
    `references/codeword-operational-table.md` for the standing map of
    corpus codewords to operations.

14. **Build a counter-evidence dossier as a first-class deliverable, not an
    afterthought.** When the corpus's alchemical theory has a known contemporary
    scientific objection (e.g. Robert Boyle's *Sceptical Chymist* 1661 explicitly
    attacks the Salt-Sulphur-Mercury framework that the corpus's R01/R02/R03 dossiers
    adopt), document the objection in a separate `G##C_COUNTER_EVIDENCE_DOSSIER.md`
    rather than burying it in a footnote. The counter-evidence dossier is *equal
    evidentiary weight* with the supporting dossiers; it is the corpus's audit trail
    for the standing position that transmutative claims are unproven. Procedure:
    (a) inventory corpus for contemporary scientific critics (Boyle, Hooke, Royal
    Society), (b) extract the specific passages that attack the corpus's theory
    (e.g. "do not subscribe to the grand Doctrine of the Chymists touching their
    three Hypostatical Principles"), (c) characterize what the critic is *not*
    saying (Boyle does not deny all chymical experiments, only the theoretical
    framework), (d) explicitly state what the corpus's standing position becomes
    in light of the objection. See `references/counter-evidence-and-three-way-dialogue.md`
    for the standard schema.

15. **Search the corpus for independent empirical verification of the color-sequence
    claims.** When the corpus's alchemical texts describe a color sequence (nigredo
    → albedo → citrine → rubedo, etc.), the natural next question is whether a
    contemporary or modern scientist independently studied the same colors in the same
    materials. Boyle's 1664 *Experiments and Considerations Touching Colours*
    mentions orpiment (As₂S₃, the corpus's citrine stage) 13 times — that is direct
    independent empirical verification of the corpus's color claim. Procedure:
    (a) keyword-count the corpus color terms (black/white/red/citrine/orpiment)
    across candidate independent sources, (b) when a contemporary source has >5 hits
    on a corpus color term, treat it as independent empirical support, (c) cite the
    specific passage and the corpus's interpretation, (d) record in the G07 color
    catalog as a corroborating witness.

16. **Catalog the 14c Latin alchemical witnesses to anchor the textual chain.** The
    corpus's R02 Mirror of Alchemy is a 13-14c Latin *Speculum Alchemiae* with a
    fabricated 16c English Bacon attribution. The 14c Latin witnesses are sparse in
    many corpora; Petrus Bonus's *New Pearl of Great Price* (1320, Lombard, dialogue
    with Janus Lacinius) is one of the most important, with 522 hits on "gold", 480
    on "silver", 377 on "sulphur", 25 on "geber", 17 on "transmutation". Use it as
    a *witness for the 14c Latin standard theory* and as a *foil for the corpus's
    later 17c innovations*. Petrus Bonus (1320) explicitly CRITICIZES arsenic and
    sulphur as solvents for transmutation ("what have those substances to do with
    metals?"); this is the opposite of the corpus's R01 Philalethes, which uses
    arsenic heavily. The corpus's R01 arsenic emphasis is therefore a **17c
    innovation**, not a 14c Latin recipe. Procedure: when the corpus has a 17c
    recipe that diverges from the 14c Latin standard, document the divergence as
    a source-critical finding (innovation or contamination).

17. **Render the same passage to a plain-English dossier for non-expert readers.**
    When the user asks for "plain English" or "anyone can understand," produce a
    parallel `G##B_PLAIN_ENGLISH_DOSSIER.md` (or `G##B_PLAIN_<topic>.md`) with
    the same evidence as the technical dossier, but stripped of: Latin terms without
    translation, assumed knowledge of 17c chemistry, jargon like "Sophick Mercury"
    without explanation, and direct citation of PDF page numbers without context.
    Keep the tier discipline (Documented / Strong interpretation / Unproven) but
    explain each tier in a single sentence at the top. Add a "What does X mean, in
    plain English?" section for every technical term. The plain-English dossier
    is *not a summary* — it is the same content rendered for a different audience.
    See `references/plain-english-dossier-template.md` for the section structure.

18. **Hunt for the author's own epistemic admission of the missing
    knowledge.** When a witness case (e.g. Helvetius 1666) describes a
    successful operation but the same author, in the same book, also writes
    that they could *not* reproduce the operation or could not recognize the
    Philosophic Matter, that admission is the strongest single source-critical
    finding in the corpus. Latin primary sources are where these admissions
    usually appear because 17c authors were freer in Latin than in
    vernacular. The Latin *nullus tamen putarim ... agnoscere posse* pattern
    ("I never thought I could recognize [the matter]") is a
    corpus-severing statement: the witness's recipe is *not* the corpus's
    recipe, even if the same author appears in both. Procedure: when
    auditing a witness case, search the *Latin* primary for explicit
    epistemic admissions (*nescio*, *ignorare*, *non potui*, *cognoscere
    non possum*) in addition to the operational passages. An author who
    admits the missing knowledge is a stronger source-critical witness than
    a third-party interpreter.

19. **The 17c "key is missing" frontispiece is a tier-1 corpus source-critical
    finding.** Some 17c alchemical books include an engraved frontispiece
    that explicitly says the recipe is hidden while the imagery is given —
    e.g. *nil deest, nisi Clavis* ("nothing is missing, except the Key") on
    the 1678 Ripley Reviv'd first edition (Wellcome Historical Medical
    Library 6549, *LONDON, Printed by Tho. Ratcliff and Nat. Thompson, for
    William Cooper at the Pelican in Little-Britain*). This is *direct 17c
    evidence* that the alchemical authors deliberately obscured their
    recipes. The corpus's R01/R02/R03 candidate recipes are *corpus
    reconstructions of deliberately obscured 17c texts*, not direct recipe
    transcriptions. Procedure: when a candidate recipe dossier is built
    from a 17c witness, check the frontispiece and prefatory matter for
    explicit "the key is missing" / "the secret is reserved" / "for the
    adepts only" / "I do not write the practice" wording. Treat that
    wording as a tier-1 finding that the candidate dossier is a corpus
    reconstruction, not a direct recipe. Update the evidence tier table to
    add a "Corpus reconstruction" category distinct from "Primary-source
    statement" and "Modern interpretation". A "corpus reconstruction" is a
    modern interpretation that proposes a specific recipe, procedure or
    material based on multiple primary sources, distinguished from a
    direct recipe transcription.

20. **Apply tier discipline to the N-gate recipe audit, not just to claims.**
    The 4-gate recipe framework (Gate 1 textual identification, Gate 2
    recipe identification, Gate 3 material identity, Gate 4 independent
    reproduction with mass balance) is the calibration point for "how
    complete is this dossier." Tier-A gates are met (the candidate's
    textual attribution is right, the recipe is reconstructable, the
    passages verify). Tier-B gates are partial (the material identity is
    plausible but unconfirmed). Tier-C gates are unmet (no independent
    reproduction). The standing position summary should list gate status
    alongside claim tier: "R01 stands at Gates 1-2 met, Gate 3 partial,
    Gate 4 not met" is a more useful summary than "R01 stands at FACT
    tier." The gate framework is the operationalization of "FACT vs
    FICTION" for recipe dossiers; the gate-state table replaces the
    single-tier label.

21. **Final consolidation pass: wire a multi-dossier series into the central
    study log.** When a research cycle produces a letter-series dossier
    set (G08, G08B, G08C, ...) totaling hundreds of KB and dozens of
    evidence page images, the corpus's central study log (e.g.
    `HITCHYZ OPUS.md`) needs a final consolidation pass before the
    research cycle is complete. Procedure: (1) add a top-of-document
    position statement as of the new revision date; (2) add a new
    "Corpus reconstruction" row to the evidence-framework table in
    the central study log; (3) insert targeted subsections at the
    existing relevant sections (e.g. Philalethes, Newton, chronology,
    mercury vocabulary) that summarize the new findings in 100-200
    words each; (4) add a "claims removed" entry for any
    newly-disproven claim (e.g. "R01 = the Helvetius 1666 recipe");
    (5) add new §N section that consolidates the dossier series
    (file-by-file table + the new findings in 5-10 bullets + tier
    discipline applied); (6) add a §N+1 standing-position section
    that restates the central question's answer in 3-5 paragraphs;
    (7) update WORK_LOG and DATA INDEX with one dated entry per
    dossier. The central study log is the spine; the dossier series
    is the muscle; the user has to be able to read the central log
    and know the standing position. Without the consolidation pass,
    the dossier series sits beside the central log unread, and the
    standing position drifts.

22. **Compile a corpus-wide experimental-research-notes dossier when the
    user asks for "data collection."** The user has a recurring
    directive ("KEEP COLLECTING EVIDENTIARY DATA",
    "collect data should be the focus", "there is limited available
    data, we need to collect and compile it all"). When this fires,
    the deliverable is a single `G##M_EXPERIMENTAL_NOTES_DOSSIER.md`
    that tabulates every experimental research note in the corpus:
    historical lab notebooks (Newton Add MS 3975 normalized JSON, ~65k
    words, ~385k chars), modern peer-reviewed replications
    (PNAS / Nature / Royal Society / J. Synchrotron Rad.), structured
    attempt registers (`ATTEMPTS_REGISTER.{md,json,csv}` files in
    `research-expansion-*/` directories), ancient recipe books
    (Leiden X), museum archaeometry (Louvre PIXE/XRD), and the
    corpus's own earlier crystal/colour catalogues. Procedure:
    (a) `ls` the corpus root and all `research-expansion-*/` and
    `corpus/downloads/` subdirectories; (b) extract size + char counts
    for every experimental-record file (lab notebooks, primary papers,
    attempt registers, museum studies); (c) for each record, document
    practitioner, date, source/locator, reported result, evidence
    limit, and tier; (d) cross-source synthesis: when modern
    peer-reviewed replication and the corpus's 17c text both report on
    the same empirical question, the *structured attempt register* is
    the corpus's strongest single piece of evidence for the standing
    position (e.g. "no record in A001-A031 establishes elemental
    transmutation" is the OPUS §13 conclusion in dataset form);
    (e) tier discipline: every claim either Tier A documented (with
    primary source) or Tier B strong interpretation (with named
    mechanism) or Tier C unproven (with explicit test plan). The
    point of this dossier is **the data, not the explanation**: the
    user wants to be able to read one file and see every experimental
    record the corpus holds, with practitioner, source, and result
    each attributed.

23. **When surveying "secret, restricted, forbidden" knowledge in the
    corpus, treat the directive as a *unsealing* task, not a
    narrative.** The user has a recurring pattern of asking for
    "secret, restricted, forbidden" or "no knowledge should be
    prohibited" material. The deliverable is a single
    `G##L_SECRET_KNOWLEDGE_DOSSIER.md` that audits three distinct
    categories: (a) 17c alchemical "secrets" deliberately obscured by
    authors (Tabula Smaragdina, Albertus Magnus *Secreta*,
    Atalanta Fugiens, Aurora Consurgens, Ripley *Liber Marrow*,
    Zosimos *On the Letter Omega*; the G08H "nil deest, nisi Clavis"
    frontispiece is the corpus's direct evidence that the obscuration
    is intentional, not accidental); (b) declassified US government
    documents in the local OCR corpus (e.g. `ocr_full/` directory:
    5 SECRET + 3 CONFIDENTIAL + 1 OFFICIAL USE ONLY + 5+ UNCLASSIFIED,
    including the 1994 DIA Stargate plan and the 1990 Koruga
    CONFIDENTIAL paper on microtubules); (c) "forbidden" crystal+metal
    knowledge (the corpus's G08K surface-plasmon / d-d / bandgap
    framework is no longer forbidden — it is documented modern
    materials science). Procedure: (a) inventory the OCR corpus for
    classification markers (SECRET / CONFIDENTIAL / NOFORN / LIMDIS
    / 25X / declassification dates); (b) for each classified
    document, capture title page metadata + executive summary; (c) for
    each 17c alchemical "secret" text, capture the frontispiece
    framing (the corpus's evidence that obscurity was deliberate);
    (d) tier discipline: the "secret" is Tier A documented historical
    fact (the text was once secret, the declassification is
    documented), the *prohibition* is Tier C unproven (no modern
    authority prohibits the corpus's recovery work). **The user's
    standing principle is the corpus's standing principle: no
    knowledge should be prohibited; the corpus is the unsealing
    work itself.**

24. **Test the user's "I think X" hypothesis on two axes: broad and narrow.** When
    the user states a hypothesis ("I think the prohibition of mercury is connected
    to the Philosopher's Stone" / "I think the dāndǐng cauldron is the same as
    the corpus's R01" / "I think the corpus's 17c recipes are the same as
    the Chinese waidan"), the deliverable is a single `G##N_<TOPIC>_DOSSIER.md`
    that tests the hypothesis on **two explicit axes**:

    - **Broad axis** (Tier B strong interpretation): is the user's intuition
      historically well-founded? Gather the strongest primary-source evidence
      that the user's claim *fits* the historical record, even if the record
      is multi-causal. The Chinese imperial elixir-poisoning record (5 Tang
      emperors dead from jīndān 金丹 / xiāndān 仙丹 = Philosopher's Stone
      ingestion) is a Tier-A example: the broad claim "mercury prohibition is
      connected to the Stone" is historically well-founded because the
      empirical record shows alchemists (and their imperial patrons) died from
      the same operations that produced the corpus's R01 Sophick Mercury.

    - **Narrow axis** (Tier C unproven unless independent reproduction): is the
      user's intuition a *deliberate-suppression* narrative? The narrow claim
      "mercury prohibition is a conspiracy to suppress the Stone" is
      unsupported by the available evidence — the empirical record is
      multi-causal (Roman mining, 19c occupational, 20c environmental, 21c
      regulatory), and each layer has independent mechanism. The narrow claim
      should be held as Tier C until independent verification.

    **Procedure:**

    1. Inventory every theory layer the user might have intuited — start with
       the most direct (ancient empirical, imperial/royal patronage, occupational,
       environmental, modern regulatory, philosophical/theological, pharmacological,
       metaphysical) and add a layer for every primary-source text the user names
       (e.g. Chinese waidan, Indian rasaśāstra, Greek-Egyptian Leyden Papyrus X,
       Islamic Jabir/Avicenna, Latin Petrus Bonus, 17c English Philalethes/Starkey).
    2. For each layer, document: date range, primary-source evidence (verbatim
       where possible), and tier (Tier A documented / Tier B strong interpretation /
       Tier C unproven).
    3. Apply tier discipline per layer — the broad-axis finding is often Tier B
       (well-founded in the historical record); the narrow-axis finding is often
       Tier C (unproven unless independent reproduction).
    4. End the dossier with a synthesis section that explicitly distinguishes
       "well-founded in the broad sense" from "not established in the narrow
       sense." The user's intuition deserves honest engagement, not a hedge.

    **Why this pattern works:** the user often *intuits* a correct broad claim
    (mercury is dangerous and alchemists knew it) but the narrow claim
    (deliberate suppression by authorities) is overreach. By testing both
    axes, the assistant validates the user's intuition where it is correct
    and refuses the overreach where the evidence does not support it. The
    corpus becomes a record of *tested* hypotheses, not just stored ones.

## Pitfalls

- **Never assume Metric Units:** Always interpret all numerical mass values (`gr`) as grains, never grams. Using grams breaks the stoichiometry of historical reconstruction.
- **Do not trust PDF OCR for symbols:** Symbols like $\mathfrak{Sb}$ or $\text{\char"2ng}$ are frequently misparsed by standard readers; rely on structured `.json` archives or raw string searches in terminal to find true matches.
- **Avoid 'The Smoking Gun' trap:** Do not declare a connection confirmed based solely on text matching; ensure you have verified provenance and chronological continuity through metadata/logs first.
- **Decode chemically, then validate physically.** A decoded recipe (e.g. a 'sophick
  mercury' prepared from Hg + Fe-Sb-Ag alloy) is only a working hypothesis until modern
  chemistry confirms the described transformations are possible under the stated conditions.
  Claims that imply creation of elements or impossible mass gains must be downgraded, not
  left as 'unexplained'.
- **A decoded recipe is a process, not a substance.** When a historical text gives a
  concrete sequence of operations (fusion, grinding, sublimation, distillation) rather
  than a single named material, model it as a **prepared reactive mercury/alloy process**,a
  not as a literal 'stone' or universal catalyst. Add the process node to the knowledge
  graph and link the known ingredients to it with `used_in` edges.
- **Take a deprecated alternative route seriously — it is historical evidence, not
  noise.** When an alchemical author explicitly deprecates one route in favor of another
  (e.g. *"Some use X, which is tedious; the other way we commend"*), the deprecated route
  is a survival of an older practice, not a mistake. Build a comparison dossier that
  documents both routes; the deprecated one anchors the recipe in textual history and
  establishes the corpus's internal chronology. The 17c Philalethes/Starkey corpus, for
  example, names the *Doves of Diana* route (silver precipitation via aqua fortis + salt)
  and explicitly deprecates it in favor of the salt-vinegar distillation route (the
  Sophick Mercury). Both routes are 17c chemistry; one is the recommended modern (17c)
  practice, the other is the older (14c?) practice that the author knows and rejects.
- **Verse alchemical texts are operational, not decorative.** When a corpus text is in
  verse (Marrow of Alchemy 1655, Ripley Reviv'd 1678), do not skip it as "literary
  surface." Verse form is a deliberate choice — veil, marketing, or mnemonic — and the
  operational content is recoverable by cross-referencing with the prose contemporary
  (Sci-Hist MS 13 for Starkey; Newton's Index Chemicus for 17c chemistry). Expect ~80%
  operational match between verse and prose versions of the same procedure.
- **A codeword used for both a product and a route is doing double duty.** The
  *Doves of Diana* in the Marrow appear as both a *visible product* of the operation
  (a silver-white precipitate) and as an *alternative route* (a procedure to prepare
  the menstruum). The two meanings are not contradictory; they are two perspectives on
  the same material. When a codeword is used in both senses, document both and
  identify which sense the author is criticizing in the deprecation.
- **Hold the projection claim separate from the recipe.** Alchemical texts frequently
  state a projection ratio (1:1000 in Mirror of Alchemy, 1:10 in some Philalethes
  passages) that is internally inconsistent with the claimed endpoint ("turns all
  metals into pure gold"). The projection is the *claim*, not the *recipe*. Decode
  the recipe operationally (matter + apparatus + fire + color sequence) and treat
  the projection as a separate proposition. Per OPUS §0, *"A successful material
  operation, an author's explanation of it and a promised philosophers' stone are
  separate propositions requiring separate support."*
- **The contemporary scientific critic is part of the corpus's evidence base, not
  outside it.** Robert Boyle's *Sceptical Chymist* (1661) was published in the
  same generation as the corpus's 17c alchemical texts. Treat contemporary
  criticism as a tier-1 witness equal in weight to contemporary endorsement. A
  corpus that documents only its supporters is not audit-ready; the audit trail
  must include the strongest contemporary objection and the corpus's standing
  position in light of it.
- **A 17c innovation is not a 14c Latin recipe.** When a 17c alchemical text
  uses a reagent (e.g. arsenic) that the 14c Latin standard explicitly rejects,
  the divergence is a source-critical finding. The 17c author is *innovating*, not
  transmitting the older tradition. Document the divergence; do not silently
  treat the 17c text as a faithful 14c continuation.
- **Plain-English is not a summary.** When the user asks for "plain English," do
  not write a 1-page summary of a 30-page technical dossier. Write a parallel
  dossier at the same depth, with every term explained and every tier-discipline
  claim labeled. The plain-English dossier must be auditable on its own; if a
  reader who has never seen the technical dossier can verify the same conclusions
  from the plain-English version alone, the translation succeeded.
- **Boyle's Sceptical Chymist does not deny all alchemy.** When mining Boyle
  1661, distinguish what he is attacking (the Salt-Sulphur-Mercury theory of
  matter) from what he is not attacking (chymical experiments themselves, the
  use of chemical remedies, the empirical investigation of matter). A
  counter-evidence dossier that mischaracterizes the critic is worse than no
  counter-evidence dossier at all.
- **User's "LOOK FOR EVIDENCE" / "KEEP COLLECTING" commands require counter-evidence too, not just support.** When the user pushes the corpus forward with these commands, they want the *opposing* evidence as well as the supporting evidence. A corpus that documents only its supporters is not audit-ready. The three-way dialogue (alchemists vs. modern chemists vs. empirical natural philosophers) is the user's standing analytical framework; maintain it in every batch.
- **A witness report of a transmutation event is NOT a recipe.** When a 17c
  alchemical author (e.g. Helvetius *Vitulus Aureus* 1667/1670) describes a
  transmutation that he witnessed but could not reproduce, his account is
  evidence of an *event*, not evidence of a *process*. The corpus must read
  such accounts in the author's own words — Helvetius explicitly says in
  Latin that he had read Paracelsus, Helmont, Basil Valentine, and Sendivogius
  but could not, even in person, have recognized the Philosophic Matter. The
  Latin epistemic admission (*"nullus tamen putarim à me Philosophicam
  Materiam ... agnoscere posse"*) is the corpus's strongest evidence that
  the 17c Philalethes corpus recipe is a *separate process* from any
  transmutation case. Do not collapse the two.
- **Sealed-vessel vs open-crucible is an operational distinction, not a stylistic
  one.** When the corpus's R01 dossier describes a sealed-vessel distillation
  (Sophick Mercury, gentle heat, 9 months, 7-9 cohobation cycles) and a
  witness case (Helvetius 1666) describes the operation performed *"in Igne
  aperto Crucibuloque"* (in an open fire and open crucible), those are
  *different operations*. Latin primary sources will settle this
  unambiguously — the conjunction *Igne aperto* (open fire) appears twice in
  P30 Helvetius 1667 (pp. 38 and 71) and cannot be reconciled with a
  sealed-vessel reading. Hold the corpus's R01 and the witness case as
  related-by-doctrine but operationally distinct; do not promote one to the
  other's recipe.
- **Old-language OCR (pre-1800) is its own class of error.** Latin and early
  modern English PDFs use `u/v` interchangeably (`Metalla` may OCR as `Mctalla`
  or `Metalia`), use long-s `ſ` that breaks substring searches, use ligatures
  `æ`/`œ`/`ct`, and drop word-medial `i`/`j`. When a `grep` returns zero hits
  for a Latin word you know is there, render the page at 200 DPI and
  `vision_analyze` it; the OCR is probably fine but the search pattern is
  too modern. Naive `grep` for *Chalybs* in P30 found nothing until a
  case-insensitive `text.lower().find('chalyb')` was used together with
  PyMuPDF page-level extraction; the word was on the page the whole time.
- **Use case-insensitive + Latinized search, not exact modern spelling, for
  17c proper nouns and technical terms.** The corpus's alchemical vocabulary
  was modernized over 300 years: *Chalybs* in 1667 Latin = *Chalybs* in
  modern English, but *Mercurialis* may be spelled *Mercurjallis* or
  *Mercurialis* depending on the typesetter. Search `.lower()` and accept
  partial matches when verifying that a Latin technical term appears; do not
  demand exact modern spelling.

- **The corpus's actual 17c lab notebooks are the primary source, not
  tertiary references.** When a normalized JSON transcription of
  Newton's Add MS 3975 (or any 17c alchemist's actual lab notebook)
  exists in the corpus, the JSON is the audit trail — it carries
  Newton's own symbols (☉☿♂♁🜍☽♀♃♄), his cross-references to 17c
  texts by page number, and his quantitative observations (grain
  weights, residue masses, dated entries). Tertiary references about
  "what Newton thought" are *not* substitutes for the notebook
  itself. Procedure: when the corpus has a normalized lab-notebook
  JSON (Newton 3975 is ~385k chars; check `corpus/downloads/historical_alchemists/Newton_ALCH*_normalized.json`),
  query the JSON directly with regex on the *text* field, render key
  folios at 200 DPI for vision verification, and cite the corpus's
  own copy. Do not synthesize Newton's recipe from secondary
  literature; the corpus has the primary source.

- **A "vdoc.pub" / "dokumen.pub" / "pdfdrive" wrapper text is not the
  book.** When a corpus has a multi-source acquisition list and one
  of the local files is a vdoc.pub or pdfdrive.to cover-page
  repetition (the same `---PAGE---` line printed 100 times with no
  body), the file is *not* the book. Do not use the wrapper as a
  source. Look for the genuine copy: Newman/Principe *Alchemical
  Laboratory Notebooks and Correspondence* is encrypted in the
  corpus's `Alchemy_Tried_in_the_Fire_*.pdf` and unavailable in
  vdoc wrapper; the corpus's Starkey data comes instead from
  secondary references (G08E Newton Chymistry Project) and from the
  corpus's own normalized transcriptions of related 17c texts
  (Newton 3975 contains Starkey's *Sophick Mercury* recipe copied
  into Newton's hand, which is more useful than a vdoc wrapper
  anyway). Document the wrapper as a blocked acquisition, not as
  a usable source.

- **The structured attempt register is the corpus's strongest single
  piece of evidence for the standing position.** When the
  `ATTEMPTS_REGISTER.{md,json,csv}` files in
  `research-expansion-*/` total ≥30 records (A001-A031+ in this
  corpus), the absence of any record establishing elemental
  transmutation is the OPUS §13 conclusion in dataset form. Do not
  bury this in a footnote. The register is the audit trail: every
  practitioner, every result, every evidence limit, every
  independent-verification status, all in one schema. When the
  user asks "what does the data say," the register is the answer.

- **When the corpus's normalized JSON for a primary lab notebook
  exists, query it for *operational* matches, not just keyword
  matches.** Newton 3975 contains the corpus's R01 Sophick Mercury
  recipe in f123r, but a literal `grep "Sophick"` or `grep "Mercury"`
  returns false because Newton's entry is in alchemical symbols
  (☉☿♂) and 17c English ("Eagle", "cohobation"). Query for
  operational vocabulary instead: "Eagle", "cohobat", "sublimate",
  "amalgam", "Mercury first internally", "common ☉" (Gold). The
  recipe is in the JSON; the search pattern must be 17c, not
  modern.

- **`patch` tool old_string mismatch on long markdown files: read the exact
  text from the file, do not paraphrase from memory.** When patching a
  large, frequently-edited file (the central study log, `HITCHYZ OPUS.md`,
  reaches 500+ lines; a `G##M` or `G##N` dossier that integrates into OPUS
  hits the same problem), the `patch` tool's fuzzy match can fail with
  "old_string not found" even when the patch context looks correct from
  memory. The cause is whitespace, line-ending, or character-level drift
  accumulated across many prior patches. Procedure: (1) `read_file` the
  exact target region with `offset=` and `limit=` covering the surrounding
  context; (2) copy the literal text from the read_file result (including
  the final newline, trailing spaces, and any em-dash characters); (3) use
  the *exact copied text* as `old_string` in the patch. Do not paraphrase
  from memory. The patch tool will then match on the first try. Skipping
  this read-and-copy step costs 1-2 failed patch attempts per §-section
  addition to the central study log, which is the highest-cost editing
  pattern in the corpus workflow.
