# Phase 3.4 implementation report

Date: 2026-10-04. Software status: implemented and tested; scientific assessment status: **pending independent expert review**.

## 1–5. Baseline and migration

- Active checkout: `/Users/joaopais7/Documents/AXIS-visual-validation`.
- `baseline_branch: codex/phase2-transfer`
- `baseline_commit: 1e156fef19a28e413a2502ce9f150bd771e81179`
- Phase 3.3 publication: `1e156fe`, verified before implementation; not assumed to be on main.
- `implementation_commit: none`
- `final_head: 1e156fef19a28e413a2502ce9f150bd771e81179`
- Migration: additive `008_cellular_pharmacology.sql`; migrations 001–007 unchanged.
- Initial unrelated `.DS_Store` and `docs/screenshots/phase2-hardening/` were preserved and are outside this implementation.
- Inspected Phase 3.3 domain/repository/service/API/UI and frozen resources, existing curated source claims, performed perturbations and proposed experiment/question models. Baseline pharmacology tests: **39 passed** before new implementation.
- Existing Phase 3.1 identity and Phase 3.2 3QNF mappings remain intact; verified again through installed-wheel regression replay.

No commit or push has been performed for Phase 3.4.

## 6–7. Reused and new models

Reused: immutable Claim, ClaimContext, Perturbation, ProteinIdentity, CompoundIdentity, BioactivityMeasurement, OpenQuestion, QuestionLinks, ProposedExperiment, OutcomeScenario and provenance primitives.

Added BiologicalContext, performed CellularExperiment, ExperimentalReadout, CellularAssessment and bounded ImmunopeptidomeObservation. Engagement, dependency and disease relevance are explicit categorical facets of one immutable assessment record, avoiding duplicate experiment/assessment architectures. Concordance is a transparent deterministic assessment projection with its source inputs and rule version; it is not a new primary measurement table.

The existing discovery experiment model represents proposals. The performed cellular model is deliberately distinct: a proposed experiment cannot supply an observed readout. Disease-specific interpretations remain contextual; no HLA-B27 assumption is built into generic chemical identity.

## 8. Source audit

Four referenced primary publications; **no additional publication corpus** was necessary to demonstrate this slice. This is not a systematic literature review.

| Publication | Access and treatment |
| --- | --- |
| Chen 2016, PMID 26130142, DOI 10.1136/annrheumdis-2014-206996 | Primary full-text XML re-inspected: methods, results and figure captions; existing claim links retained |
| Chen 2014, PMID 24504800, DOI 10.1002/art.38249 | Existing frozen primary abstract/context; no new full-text verification claimed |
| Tran 2016, PMID 27107845, DOI 10.1016/j.molimm.2016.04.002 | Existing frozen source curation retained; renewed full-text XML request returned HTTP 500 |
| Maben 2020, PMID 31841350, DOI 10.1021/acs.jmedchem.9b00293 | Existing Phase 3.3 primary-source chemistry, assays and cellular measurements |

Chen XML: SHA-256 `4425070f24b7407603c80c8562e75f42dda2886a9ed156b69b6c0292db3d5bca`, matching the historical snapshot. Curation-session retrieval timestamp `2026-10-04T14:51:18+00:00`; [Europe PMC full text](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC4853590/fullTextXML). No article XML/PDF/figures are redistributed. Supplements were not retrieved. Primary-source extraction remains AI-assisted, not expert-accepted fact.

The audit additionally found published PBMC and KIR3DL2 results, but did not import them as new independent claim rows in this small slice. Their absence from the package must not be interpreted as absence from the publication or literature. The historical six-source disease-evidence banner describes the Phase 2 corpus; this cellular package references its own four-source subset/extension including Maben.

## 9–13. Experiments, perturbations and contexts

**11 experiment/context records, 11 readouts, 37 categorical assessments, one aggregate immunopeptidome observation.** These are not eleven independent studies or cohorts.

| Records | Intervention and readout | Source links |
| --- | --- | --- |
| 2 Chen silencing contexts | HeLa.B27 / C1R.B27 shRNA; reduced surface FHC signal | C08; Figure 2A–D |
| 2 Chen DG013A contexts | HeLa.B27 / C1R.B27; reduced surface FHC signal | C09; Figure 2E–H |
| 1 AS CD4+ coculture context | Source-separated genetic/chemical arms; Th17 expansion and IL-17A secretion | C10; Figure 4C–D |
| 1 Chen 2014 immunopeptidome context | Silencing; increased 11–13-residue peptide proportion | C06; primary abstract |
| 1 Chen 2014 variant context | K528R versus WT; reduced KK10-specific CTL recognition | C07; primary abstract |
| 2 Tran U937.B27 endpoints | shRNA; increased HC10-reactive FHC and separately measured disulfide-linked dimers | C12/C13; Figures 2/3 |
| 2 Maben chemical contexts | Compounds 2/3; engineered HeLa H-2Kb antigen-presentation cellular IC50 | Existing measurements 8/15; Figure 9D |

Historical perturbations P05, P09 and P13 are reused where appropriate. Separate Chen 2016 silencing, composite coculture, K528R and Maben interventions have explicit new performed perturbation records. Historical source Claims and Phase 3.3 measurements were not rewritten or duplicated as newly independent evidence; offline replay tests compare the original records before/after import.

Only Maben compounds 2 and 3 link to the existing resolved CompoundIdentity objects. DG013A remains a source-reported perturbagen, **not an invented chemical identity or selectivity/engagement measurement**. Compound 1 retains biochemical-only evidence; it does not borrow compounds 2/3 cellular results.

HLA-B*27:05 engineered Chen/Tran model context is retained where verified. Chen 2014 subtype remains unknown. Maben's **murine H-2Kb** is stored separately as MHC allele; HLA-B27 effects are explicitly unestablished. U937's endogenous HLA-B*18:01/B*51:01 caveat remains visible.

ERAP1 K528R and U937 rs30187/rs27044 heterozygosity are recorded; complete allotypes remain unknown. Missing genotype, duration, vehicle and dosing are “Not reported”, not inferred. Chen dose titration retains 10/100/1000 nM; Maben duration retains 16–24 h. No raw dose-response points are reconstructed.

## 14–19. Engagement, function, phenotypes and concordance

Direct cellular compound engagement is **not assessed** for the chemical experiments in this slice. Genetic interventions are not compound binding and are classified as not applicable for that question. No claim of literature-wide absence is made.

Proximal catalytic functional modulation remains insufficient in these selected readouts. Genetic perturbation provides contextual functional involvement/dependency support, but does not prove drug-specific ERAP1 dependency. Chemical dependency remains uncertain, and off-target contributions cannot be excluded.

Molecular evidence distinguishes peptide-length shifts, HC10-reactive FHC signal, disulfide-linked dimers and antigen presentation. Free heavy chains are not automatically homodimers. Immune evidence distinguishes viral KK10 CTL recognition and AS-derived CD4+ coculture response. H-2Kb antigen presentation is not an HLA-B27 phenotype.

Patient-derived AS CD4+ cells contribute an ex vivo immune context; engineered APCs remain engineered cells. This does not establish a disease-improvement endpoint. Neither the disease-phenotype nor clinical-effect edge is promoted from molecular/immune evidence.

Genetic-versus-chemical assessment exposes both experiments/readouts, context and rationale. Matching known species, system, HLA, genetic/allotype, endpoint, assay and duration is required before concordance. Actual comparisons are not comparable under the conservative rules. Synthetic matched contexts test concordant and discordant outcomes; different HLA context does not become a forced contradiction. Project-wide comparisons do not imply that Maben compounds share DG013A's HLA effects.

## 20–23. Gaps, questions, proposals and review packet

Four explicit missing-engagement gaps link compound where resolved, perturbation, experiment context and the engagement edge. They create records in the existing OpenQuestion and ProposedExperiment systems, with source-claim links where available. No second question model was added. No new validated disease hypothesis is manufactured.

Next candidate experiment: establish direct/proximal cellular ERAP1 engagement and genetic dependency in a matched context before attributing the phenotype to ERAP1. These are labelled **AXIS proposals**, not ready laboratory protocols or observed results. Controls include genetic depletion/rescue and orthogonal interventions, with separate viability evaluation. Every proposal has three competing outcome scenarios; no desired result is preselected.

Scientific review artifact: [review packet](phase3-cellular-scientific-review-packet.json). Eleven records include context, readouts and assessments, with independent pending decisions for source extraction, context, chemical identity link, engagement, dependency, phenotype, disease relevance and concordance. `automatic_acceptance: false`.

Frozen package: `axis/resources/cellular/erap1-axspa/v1/`. Manifest SHA-256:
**`1358a372dbab5430bf521ec09f22750e573cc22c862660107e191879e225649c`**.

## 24–25. API and UX

Read API: project/target-scoped cellular overview, experiments/details, readouts, assessments, immunopeptidome, engagement/evidence-chain, concordance, gaps, decision and review packet. Collections are bounded, applicable reads are compound-scoped, invalid filters/scopes are rejected. GET performs no literature/provider retrieval. Explicit CLI import is separate and transactional.

Cellular Evidence provides a text-accessible evidence ladder, source-input inspection and performed experiment details. Chemistry compound detail links to its own cellular chain. Genetic/chemical comparison shows a context table rather than forced reconciliation. Phenotype view retains source endpoints and classification. Decision and next-experiment views derive states and questions from imported records rather than hard-coding a successful therapeutic chain.

No numerical validation score or compound ranking. Unknown, insufficient, not-assessed and inapplicable states remain inspectable. Existing dialogs retain keyboard opening, Escape and focus return. Responsive views use four/two ladder columns at 1440/1024 widths; comparison tables scroll within their container when necessary.

## 26–29. Validation gates

| Gate | Result |
| --- | --- |
| Full Python suite | **356 passed, 2 skipped**; final run 22.04 s, existing data-dependent skips |
| New cellular tests | **36 tests**, included in full suite |
| Scoped Ruff: axis/tests/three wheel-verification scripts | Passed |
| Global Ruff | **Not passed: 281 findings in unchanged historical scripts**, reported separately |
| Strict mypy | Passed, 125 source files |
| TypeScript / ESLint | Passed |
| Frontend contracts | **23 passed**, including three new cellular contracts |
| Production build | Passed; existing large lazy NGL chunk warning remains |
| Wheel build/install | Passed into fresh install target on this computer; existing environment supplies dependencies |
| Installed-wheel frozen resources | Schema 8, final manifest checksum, 11/11/37 counts verified outside checkout |
| Two-store offline replay | Passed; network entry points disabled; experiments/context/readouts/assessments/chains/gaps/review packet deterministic |
| Migration 7→8 / legacy upgrades | Passed, including read-only refusal before migration and replay after upgrade |
| Immutable history / transaction conflict / scope checks | Passed |
| API smoke | Passed, scoped overview/detail/collections and isolation checks |
| Installed-wheel Phase 3.3 and Phase 3.2 regression | Passed; original frozen pharmacology and 3QNF checksums retained |
| Playwright | **12 passed**, including two new cellular acceptance traversals at 1440/1024; keyboard Enter/Escape/focus-return included |
| Visual acceptance | Live local UI inspection plus manual review of 20 PNGs at 1440×1000 and 1024×1000 |
| Git whitespace check | Passed |

Browser: existing Chrome for Testing 147.0.7727.15 selected through `AXIS_BROWSER_EXECUTABLE`; no browser installed or security protection bypassed. Historical question/proposal test selectors/counts were adapted to the additional imported records, not used to hide failed functionality. UI/source-package refinements were followed by repeat acceptance runs.

Twenty reviewed captures: `docs/screenshots/phase34/cellular-{1440,1024}-{overview,ladder,experiment,comparison,hla,missing-engagement,non-comparable,provenance,decision,next-experiment}.png`.

Not executed: independent second-computer/OS installation, Edge acceptance, systematic literature review, supplements/raw MS verification, new full-text verification of Chen 2014 or Tran, independent scientific/chemical review, laboratory replication, direct engagement measurement or clinical validation. Synthetic contradictory/mixed states test rendering/rules; no contradictory real experimental record was invented for a screenshot. This machine's wheel target is not independent installation validation.

## 30–31. Scientific limits and recommended next phase

The package is a deliberately small AI-assisted curation. Unknown substance identity, tested allotype, exposure duration and off-target contribution limit causal interpretation. A shared phenotype does not prove on-target drug action. Source assertions, AXIS assessments and future experiments remain epistemically separate. AS coculture observations cannot establish efficacy across axSpA or clinical remission.

Based on the actual engagement/dependency gaps, the recommended follow-up is **Option A — Experimental Decision Engine**: formalize competing explanations, feasible discriminating experiments, outcome-dependent updates and scientific reviewer decisions. First review the current extraction/classification packet; do not add patient stratification or structural design merely because the software can display molecules.

**Stop:** Phase 3.5, docking, molecular design, PK/PD, safety prediction and clinical development were not started. Implementation remains uncommitted; await review.

Methodological detail: [cellular pharmacology documentation](phase3-cellular-pharmacology.md).
