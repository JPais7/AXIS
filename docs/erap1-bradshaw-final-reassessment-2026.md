# ERAP1 BRADSHAW main-article unblock and scientific reassessment

Cutoff: **2026-10-05**. Review mode: **exploratory, pending independent scientific review**.

## Outcome

**Stage A: A1 — BLOCKER RESOLVED. Stage B executed: DECISION STABLE.**

The legitimately supplied main article establishes the missing BRADSHAW assay
identity and an explicit protocol-inheritance chain. The unchanged AXIS engine
created `decision-state:2:212f995ecc55c989`, causally linked to the actual canonical
`decision-state:1:cebbae3880aeec90`. The critical uncertainty remains
`uncertainty:target_engagement`; the recommended experiment remains
`decision:exp:chemical-genetic-engagement`.

This is an actual engine execution, not a hand-written stable-state assertion.
More programme-level evidence of ERAP1 chemical tractability does not establish
direct cellular engagement of the historical phenotype-producing Maben compounds.

## Repository and immutable boundaries

Verified after fetching the configured remote:

- Branch: `codex/erap1-data-rich-evidence-integration-2026`.
- Starting HEAD: `1a8d0ffb39eb493e2d87abb568d70d4ab9cb283a`.
- Starting working tree: clean in `AXIS-evidence-refresh`, the active integration
  checkout. The ambient `AXIS` directory is a separate old checkout and was not edited.
- `main` was not modified. No commit, push or merge is authorized by this task.
- Historical `v1`, `closure-v1` and `assay-methods-v2` bytes are preserved and
  individually bound into the new manifest. The historical A2 refusal remains valid
  as a historical access-state result, not a statement about the newly supplied article.
- New sibling package: `axis/resources/evidence-integration/erap1-data-rich/2026/bradshaw-main-v3/`.
  Fifteen files, 1,275,604 bytes; largest file 622,421 bytes. No primary PDF,
  coordinates, workbook, raw MS or duplicate original CSV is distributed.
- Canonical snapshot SHA-256:
  `83b2bcff0b58daccfeda58126d918d593e002e1499382f1ddfa450fe2737ee68`.
- Baseline engine input digest exactly reproduces
  `cebbae3880aeec9084784f9f8df4a89abfe71a6058e3c924ce78651beaa44541`.
- Decision rules fingerprint remains
  `184a1e2949a61e362545e897de43890014bcdcac7191f621c84fb2b739cecd33`.

The new state is recorded in an isolated temporary EvidenceStore during freeze and
replay, and exported into the versioned package. It does **not** mutate a user's
production database or replace the commercial baseline. The existing explicit-record
window API and `DecisionService.build` are used; no decision rule is changed.

The engine digest binds rule-consumed records. The package manifest additionally
binds primary-source hashes, method adjudication, numerical reconciliation and
context not interpreted by the current engine. These are different boundaries:
retaining a context registry does not imply that the engine interprets every sentence.

## Source authentication and one-publication provenance

Law et al., *Automated Molecular Design in BRADSHAW, Applied to the Optimization
of ERAP1 Inhibitors*, Journal of Medicinal Chemistry 2026, 69, 8869–8896.
DOI: `10.1021/acs.jmedchem.5c03071`.

- Exact supplied filename: `jm5c03071.pdf`; complete 28-page article.
- SHA-256: `63e41f98ff9c84e2c6f9b09d81631ce72ae74b98d22bdbb4611e9d0b23233e01`.
- Publication date: **2026-04-13**, directly printed on page 1, not inferred from
  retrieval date or DOI metadata.
- Access: PDF footer identifies `UNIV LUSOFONA 02800` on **2026-10-05**.
  This is legitimate institutional access; it is not an open-redistribution license.
- Cutoff eligible. No post-cutoff primary material was acquired.
- Main article, existing SI, CSV and mapped structures are one linked publication
  package, not independent studies. Tinworth preprint/final likewise remains one
  programme/publication-version chain, not replication.
- SI SHA-256: `c4c3b8a379ea6db1c44dcd925bb5dabc6ed25a86028c98a52a4068eca28673bb`.
- CSV SHA-256: `108d53d44a970844876c158827c1b7bc22119016c49b1498d027300be5bd23e8`.
  Supplied SI/CSV match previously frozen originals. CSV source rows are checked
  against the 42 existing BRADSHAW chemical identities; they are not recreated.

The manifest timestamp is a deterministic cutoff snapshot, not a claimed real-time
execution timestamp. A date-only source-access footer is not converted into a
fictitious recorded access time; claim serialization explicitly marks that precision.

## Primary methods and explicit inheritance

Main PDF page 4 (8872) directly identifies purified ERAP1 Hap2, RapidFire mass
spectrometry, YTAFTIPSI substrate and TAFTIPSI hydrolysis product. Page 5 Figure 4
explicitly defines “ERAP1 pIC50” as Hap2 biochemical potency with YTAFTIPSI.

Page 17 (8885), **ERAP1 Enzymatic Activity**, explicitly refers to reference 22,
verified on page 27 as **Liddle et al. 2020**, DOI `10.1021/acs.jmedchem.9b02123`.
The already accessible Liddle full methods, PDF page 8 (H), establish:

- Full-length Hap2 assay protein with retained C-terminal 6His, not a deleted
  crystallographic construct.
- 1 nM enzyme, 5 uM YTAFTIPSI, 60 minutes, 25 uL/well in 384-well format.
- 50 mM HEPES, pH 7.0; 100 mM NaCl; 0.002% Tween20; 0.005% BSA.
- RapidFire C18/Sciex4000 Q-trap; TAFTIPSI/internal-standard normalization and
  four-parameter concentration-response fitting.

These fields are **INHERITED_VERIFIED through BRADSHAW p17/ref22**, not borrowed
from Tinworth or Hryczanek because the programmes are related. Temperature,
preincubation and tested concentration range remain **NOT_CONFIRMED**. Caco-2 or
hepatocyte temperatures are not assigned to biochemical or reporter assays.

Page 17 **Cellular Antigen Presentation Assay** directly establishes HeLa,
endogenous ERAP1, ER-targeted LEQLESIINFEKL precursor, SIINFEKL presentation on
mouse H-2Kb/beta2m, 40 hours, 25.D1.16/APC and iQue flow cytometry. It describes
pharmacological-control normalization at 50 uM final assay concentration, rather
than the historical KK control. The control compound's identity is not inferred
from Tinworth compound 6. GFP controls transduction; Zombie Violet and the 95%
threshold establish 0.5% DMSO tolerance, not viability at every compound exposure.

The endpoint is **cellular antigen-presentation pharmacology**, not occupancy,
direct engagement, chemical-genetic dependency, or human HLA-B27 efficacy.
HeLa ERAP1 allotype, ERAP2 and endogenous HLA remain unconfirmed.

## Numerical reconciliation and bounded eligibility

All **79 existing BRADSHAW potency summaries** retain their existing measurement
IDs, original SMILES, pIC50 operators and values. SI S60/Table S2 supplies
compound-level N-in-mean and SD for 39 compounds; blank fields remain blank.
General main-table statements `n>=2` (and Table 6 `n>=3`) do not manufacture
compound-specific N for rows missing from S60.

Important exceptions preserved:

| Measurement | Primary source detail | Treatment |
|---|---|---|
| Compound 21 biochemical | Main p9/Table2: one additional pIC50 >9.29; SI mean9.0, N5, SD0.26 | Exact mean and censored occasion both retained; excluded from fitting subset |
| Compound 22 cellular | SI/main N1; SD absent | Singleton, not a replicated exact observation; excluded from fitting |
| Compound 28 cellular | Main5.3 vs SI/CSV5.4, N1; four additional occasions <4.3 | Source conflict and censoring retained; neither value silently selected; excluded |
| Compound 33 cellular | N2 mean6.6; five additional occasions <4.3 | Mixed exact/censored occasions retained; excluded |
| Compound 44 cellular | N7 mean6.6; one additional occasion <4.3 | Mixed exact/censored occasions retained; excluded |
| Compounds 1/2/4 where represented | No compound-level SI N/SD | No invented N; excluded from predictive-fitting subset |

SD is in **pIC50 space**, not an IC50 standard deviation. Conversion is the existing
`IC50[nM]=10**(9-pIC50)` with reversed censoring inequality. Individual measurements
cannot be reconstructed from a published mean/N/SD. No bound becomes an exact value.
Visual transcription of main tables is frozen separately from automated SI extraction;
graph heights are not digitized and unbound cellular estimates are not pooled with
total cellular potency.

Conservative BRADSHAW subsets require known N>=2, consistent main/SI/CSV means and
no additional censored occasions. Existing policy rerun:

| Dataset | Exact compounds | Murcko scaffolds | Existing numerical gate | Scientific status |
|---|---:|---:|---|---|
| Hap2/YTAFTIPSI biochemical | 38 | 24 | MODEL_ELIGIBLE | MODEL_ELIGIBLE_WITH_CONDITIONS |
| HeLa antigen-presentation cellular | 31 | 19 | MODEL_ELIGIBLE | MODEL_ELIGIBLE_WITH_CONDITIONS |

No model was trained. Tested salt/form uncertainty persists. Publication date is
not measurement date; temporal split feasibility is **NOT_ESTABLISHED**. Scaffold
splitting, duplicate/identity safeguards and applicability-domain evaluation would
precede training. No validation performance, prospective utility or disease prediction
is claimed. The historical **MODEL NOT BUILT** artifact remains unchanged.

Tinworth's separate existing numerical-policy diagnostics were rerun; duplicate
structure and/or small-size failures remain. They are SAR-only, not pooled with
BRADSHAW, and the two cellular normalization schemes remain separate.

## Allotype/substrate context and localized uncertainty

Compound 40's panel is preserved separately: allotypes 1–10, YTAFTIPSI and
EAAGIGILTV, with their distinct enzyme concentrations listed in the frozen context.
EAAGIGILTV product is AGIGILTV. Figure 16 specifies pIC50 <4 for YTAFTIPSI columns
4 and 6–10; these are not exact pIC50 4 observations. The graphic heading itself
prints YFATIPSI, whereas caption, Results and Experimental Section state YTAFTIPSI;
this typography discrepancy is not used to invent a second substrate or extract
precise numeric graph values. Potency and maximum response are context dependent.

The authors did not progress this series as a preclinical candidate series because
of allotype/substrate dependence and potency/exposure limitations. Potent tool
compounds are not candidate-quality therapeutics.

| Inference | Remaining limitation | Consequence |
|---|---|---|
| Internal BRADSHAW biochemical SAR | Source-specific conditions and replicate exceptions | Comparable within the defined Hap2/YTAFTIPSI series; conditional fitting exclusions |
| Biochemical vs cellular | Different endpoint/system | Descriptive pairing only; not comparable as one pooled endpoint |
| BRADSHAW vs Tinworth biochemical | Common explicit Liddle chain, unknown temperature/preincubation/range/form | PARTIALLY_COMPARABLE method family; no numeric interchangeability or pooling |
| BRADSHAW vs historical Maben | Different substrate/assay/preparation and compounds | NOT_COMPARABLE quantitatively; no engagement transfer |
| Allotype/substrate panel | Different enzyme/substrate contexts and maximum responses | Context-specific characterization; no collapsed ERAP1 potency |
| Human therapeutic translation | HLA-B27×ERAP1×ERAP2, desired peptide state, window and clinical benefit unestablished | No claim of axSpA efficacy or protective immunopeptidome |

Comparability categories are transparent curated inferences, not an invented generic
numeric engine. The existing strict selectivity rule is replayed through the parent
package; mismatched ERAP2/IRAP substrates still produce **no ratio or bound**.
Unknown experimental fields block only inferences that require them. They do not
invalidate the directly observed Hap2/YTAFTIPSI method identity or the current
compound-specific engagement question. Stage A's existing identity requirements
are unchanged and now pass; its required families are complete.

## Stage B: actual inputs, causal scope and scientific layers

The canonical state is loaded, not invented from a prompt. The existing engine
receives source-scoped biochemical summaries, representative BRADSHAW tool21/40
reporter readouts, Tinworth's separate reporter schemes/CT26/CIA context, existing
immunopeptidome/allotype/rat-model claims, original baseline records and the already
mapped structural identifiers. All 34 historical integrated claims remain linked in
the context registry; six additional source assertions round-trip as actual immutable
domain Claims. Record-window readouts link to those claims or existing parent IDs.

Population association, PK estimates, FOCIS abstract material and sponsor engagement
statements are not silently upgraded into direct cellular occupancy. Existing
programme-level immune and disease-model observations remain source/context limited.
The engine's `disease_relevance` label concerns its current categorical evidence layer,
not demonstration of efficacy in human axSpA; `clinical_translation` remains separate.
An executed sensitivity test removes the newly projected CIA/rat disease observations
and confirms the critical uncertainty and next experiment remain unchanged.

The mandatory machine-readable causal diff contains eight dimensions. Changes in
structural/chemical/cellular entries mean **expanded evidence coverage**, not an
assertion that these properties were absent in v1 or that they establish clinical
benefit. Learning changed at admission/eligibility level, not model-training status.
Critical uncertainty, next experiment, strategy identifiers and historical Maben
engagement remain stable with explicit reasons and unchanged rule references.

Layer-specific assessment:

- **Structural tractability:** mapped ligand-bound experimental regulatory-site
  structures inform design, not cellular occupancy.
- **Chemical tractability:** multiple measured chemotypes/programmes support
  modulation of defined ERAP1 preparations. No universal allotype/substrate claim.
- **Cellular pharmacology:** reporter and peptide-repertoire changes are observed;
  no equivalence to direct target engagement.
- **Disease translation:** models, associations and early reports do not establish
  therapeutically useful ERAP1 modulation in human axSpA.
- **QUESTION_PARTIALLY_ADVANCED:** a defined modulation-context question is justified
  as a programme-level hypothesis framework, but does not replace the historical
  compound-specific experiment selected by this engine.
- **Corrector hypothesis: PLAUSIBLE_BUT_INSUFFICIENT.** Allotype/substrate and
  inhibitor-versus-KO differences motivate testing desired processing states, but
  identify neither a validated protective state nor a clinically optimal magnitude.

## Decision View

### WHAT WE KNOW

ERAP1's regulatory site has experimentally observed chemical matter and mapped
structures. BRADSHAW's primary biochemical endpoint is now securely identified.
Later programmes alter cellular antigen presentation/peptide repertoires under
specified contexts. Modulation is allotype/substrate dependent.

### WHAT WE DON'T KNOW

Whether the historical phenotype-producing compounds directly engage ERAP1 at
the cellular exposures used; whether each compound phenotype is ERAP1-dependent;
whether comparable selectivity excludes alternative explanations. The desirable
processing state and therapeutic benefit in defined human disease context remain open.

### CRITICAL UNCERTAINTY

`uncertainty:target_engagement`, selected by unchanged `DECISION-GAP-001/002` and
`DECISION-CRIT-001`, not manually shifted downstream.

### NEXT DISCRIMINATING EXPERIMENT

`decision:exp:chemical-genetic-engagement`: matched engagement and phenotype readouts
at phenotype-active exposures in validated WT/null/rescue cells, preserving compound,
allotype/HLA context, exposure and toxicity controls. It remains a proposed experiment;
none was performed by this computational reassessment.

### WHY THIS EXPERIMENT NEXT

Biochemical activity + phenotype without direct engagement → on-target/off-target/
indirect explanations remain viable → matched engagement and chemical-genetic
comparison distinguishes them → existing outcome-to-consequence mapping:

- Engagement plus loss/rescue of phenotype → strengthen this compound/context strategy.
- Engagement but unchanged null-cell phenotype → weaken compound-specific ERAP1 attribution.
- Dependency without detectable engagement in a validated assay → revise the mechanistic model.
- Background-dependent engagement/dependency → investigate matched allotype/HLA context.
- Invalid null/rescue model or toxicity → uncertainty remains; validate and repeat.

These are conditional proposals generated by the existing engine, not evidence that
any outcome has occurred or that a treatment is effective.

## Required closure answers

| # | Question | Answer |
|---:|---|---|
| 1 | Main article authenticated? | Yes: complete file, title/authors/DOI/date/footer and SHA verified |
| 2 | Cutoff eligible? | Yes: publication2026-04-13; institutional access2026-10-05 |
| 3 | Biochemical identity established? | Yes: purified Hap2/YTAFTIPSI inhibition |
| 4 | Hap2 established? | Yes: direct main text/Figure4 and explicit ref22 |
| 5 | YTAFTIPSI established? | Yes: primary assay text and methods |
| 6 | RapidFire MS established? | Yes: direct p4 plus inherited protocol |
| 7 | TAFTIPSI product established? | Yes: direct p4 and ref22 |
| 8 | HeLa presentation established? | Yes; not occupancy |
| 9 | Main/SI/CSV consistent? | Reconciled, not universally concordant: compound28 conflict retained |
| 10 | N/SD traceable? | Where reported; exact row values and exceptions retained |
| 11 | Unknown fields? | Temperature, preincubation, dose range, tested form; reporter genotype/control identity |
| 12 | Globally decision material? | No for current question; block specified quantitative/translation inferences |
| 13 | Internal biochemical SAR comparable? | Yes, within defined context with exclusions |
| 14 | Quantitatively interchangeable with Tinworth? | No; partially comparable method family only |
| 15 | Quantitatively interchangeable with Maben? | No |
| 16 | Learning eligibility changed? | Yes: bounded BRADSHAW eligibility with conditions; no training |
| 17 | New Stage A? | A1 |
| 18 | Stage B executed? | Yes: existing engine with unchanged rules |
| 19 | DecisionState v2 created? | Yes, exploratory, predecessor-linked in new sibling package |
| 20 | Critical uncertainty changed? | No |
| 21 | Next experiment changed? | No |
| 22 | Historical Maben engagement unresolved? | Yes; later chemistry does not transfer |
| 23 | Therapeutic question advanced? | Partially as programme framework, not a clinical conclusion |
| 24 | Ready for independent review? | Yes with the explicit conditions below; not investigator-approved |

## Acceptance matrix

No aggregate score. PASS means the bounded audit requirement is fulfilled, not
that the biological claim is scientifically validated by an independent reviewer.

| Dimension | Status |
|---|---|
| Source authenticity | PASS |
| Provenance integrity | PASS |
| BRADSHAW assay identity | PASS |
| BRADSHAW assay completeness | PASS WITH CONDITIONS |
| BRADSHAW internal comparability | PASS |
| Cross-programme comparability | PASS WITH CONDITIONS |
| Numerical integrity | PASS WITH CONDITIONS |
| Chemical identity | PASS WITH CONDITIONS |
| Allotype/substrate context | PASS |
| Cellular endpoint integrity | PASS |
| Chemical Learning eligibility | PASS WITH CONDITIONS |
| Epistemic integrity | PASS |
| Decision causality | PASS |
| Offline reproducibility | PASS |
| External-review readiness | PASS WITH CONDITIONS |

Conditions for scientific review: pending curation of the primary/reference chain;
source-limited/preprint methods where the Tinworth final main remains inaccessible;
compound28 discrepancy and censored occasions preserved rather than resolved;
tested-form and experimental-detail limits; no quantitative cross-programme pooling;
no direct engagement transfer; no validated disease-protective peptide state;
temporal split/domain validation before any future model training.

## Reproduction and validation

From the integration checkout with the existing Python3.12 environment:

```sh
PYTHONPATH=. python scripts/reassess_erap1_bradshaw.py --replay
PYTHONPATH=. pytest -q tests/test_erap1_bradshaw_reassessment.py
```

Replay verifies parent bytes and every new manifest member, round-trips immutable
claims, regenerates method/numerical/eligibility artifacts, loads the canonical state
and executes the unchanged engine in a temporary store. It does not need the original
licensed PDFs or a network connection. Fresh authentication of primary files still
requires access to bytes with the recorded hashes; offline replay is not redistribution
of, or a substitute for reviewing, the main article.

Validation results and package-distribution checks are recorded in the companion
`erap1-bradshaw-final-validation-2026.json` after their execution. The existing global
Ruff debt is reported separately; it is not silently fixed in this bounded task.

## Git handoff

Ending HEAD remains the starting SHA; changes are uncommitted new files only.
Added: the replay/ingestion script, 27 scientific tests, this report, companion
validation record and the 15-file sibling package. Existing tracked files, historical
states, engine rules and commercial outputs are unchanged.

Recommended next Git action: review the new diff, then explicitly authorize a commit.
Proposed exact message:

`Resolve BRADSHAW assay provenance and record stable ERAP1 decision reassessment`

No automatic push or merge.

**BLOCKER RESOLVED — DECISION STABLE — READY FOR INDEPENDENT SCIENTIFIC REVIEW WITH CONDITIONS**
