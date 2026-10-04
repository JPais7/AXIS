# Cellular pharmacology and translational evidence

Phase 3.4 adds performed cellular observations without changing historical Claims or pharmacology measurements. The existing Perturbation bridges intervention and experiment. ProposedExperiment continues to represent future work, never a performed result.

## Evidence classes, not a score

AXIS keeps independent categorical states for exposure, biochemical activity, direct cellular engagement, functional modulation, HLA/MHC antigen-presentation phenotype, immune phenotype, disease phenotype and clinical effect. States are supported, contradicted, mixed, insufficient, not assessed or not applicable. No occupancy, permeability, therapeutic index, validation score or compound ranking is calculated.

Combining source inputs is deterministic: opposed supported/contradicted inputs produce mixed; assessed states remain distinct from missing and inapplicable. A project-wide projection is an inventory across contexts, **not a demonstrated causal chain**. Compound-scoped projections do not borrow another compound's cellular evidence.

Direct engagement requires explicit direct cellular interaction classification and target-proximal readouts. A downstream phenotype cannot qualify. Functional involvement and target dependency are separate from physical engagement. The current slice deliberately leaves proximal catalytic modulation insufficient and chemical target dependency uncertain rather than promoting phenotype into engagement.

## Context and identity

BiologicalContext embeds existing ClaimContext and adds cell line, HLA allele/expression, disease status, donor context, allotype and a separate MHC allele. HLA-B27 status does not invent a subtype. rs30187/rs27044 or K528R do not determine an entire allotype. Engineered expression is not endogenous expression. Mouse H-2Kb is not a human HLA allele.

Canonical protein identity anchors the scoped project, not a verified cellular protein construct or allele. Unknown experiment-specific material remains unknown. DG013A remains a reported perturbagen without CompoundIdentity; no ChEMBL/PubChem/structural bridge is fabricated. Maben compounds 2/3 have explicit existing compound and measurement links.

Nominal concentration, duration, dosing, vehicle, controls, readout, method, genotype, HLA context, source locator and limits remain inspectable. Unknown fields render “Not reported”. Cellular IC50 stays in its original assay; no biochemical/cellular ratio is interpreted as permeability or binding.

## Phenotypes and disease context

Published peptide-length changes are bounded aggregate ImmunopeptidomeObservation records; there is no raw MS ingestion or reconstructed peptide abundance. The current 11–13-mer observation retains its silencing, cell and HLA context. No numeric distribution is invented.

HC-10-reactive free-heavy-chain signal and measured disulfide-linked dimers are separate endpoints. Neither is renamed inflammation or disease improvement. KK10-specific CTL recognition is an immune phenotype in a viral antigen assay, not arthritogenic peptide rescue. The AS CD4+ coculture retains the source's ankylosing spondylitis terminology and patient-derived component; engineered APCs are not patient APCs. IL-17A appears only in the reviewed source-backed coculture readout. No unmeasured cytokine is inserted.

The source audit contains additional patient PBMC/KIR3DL2 observations that this deliberately small package does not import as new independent claim rows. Absence here means unrepresented/not assessed in this slice, not absence from literature. No source-level clinical interpretation is promoted into an AXIS therapeutic finding.

## Concordance

Genetic-versus-chemical comparison checks reported cell/system, species, HLA allele/expression, genotype/allotype, disease context, assay, endpoint and duration. Missing matching genetic or temporal context prevents a direct concordance verdict. Matched synthetic contexts demonstrate concordant and discordant outcomes in tests. Real imported comparisons remain not comparable under these conservative rules.

Opposite directions in Chen and Tran are inspectable but are not forced into a universal contradiction across incompatible systems. Comparisons expose the two experiments/readouts and rule rationale. Project comparison is bounded to 20 experiments, 100 readouts and 20 returned comparisons; it is not an exhaustive review.

## Storage and provenance

Migration 008 is additive; migrations 001–007 remain unchanged. Focused immutable repositories store experiments, readouts, categorical assessments, aggregate immunopeptidome observations and links to existing OpenQuestions. Foreign keys plus scope checks validate perturbation, compound, claim and measurement membership. Import is checksum-verified and transactional; replay is idempotent and conflicting identifiers roll back.

TargetEngagement, TargetDependency and DiseaseRelevance are facets of one immutable CellularAssessment rather than parallel duplicated tables. Performed cellular experiment and proposed discovery experiment are deliberately separate. Concordance and evidence-chain aggregation are deterministic bounded read projections, not stored primary measurements or expert-accepted verdicts.

Each readout references an existing source Claim or BioactivityMeasurement. Source publication identifiers and figure/method locators are retained; the package audit distinguishes newly re-inspected full text from previously frozen abstract/curation. AI-assisted extraction and assessment decisions remain pending expert review.

## Gaps and proposed experiments

Four explicit missing-engagement gaps link experiment context, compound where resolved, perturbation and the existing OpenQuestion/ProposedExperiment systems. Three outcome scenarios preserve competing explanations: engagement with dependency/phenotype alignment; phenotype without detectable engagement; engagement without phenotype. None predetermines an on-target conclusion.

Proposal context is a candidate design requiring researcher feasibility and assay review, not a ready laboratory protocol. Disease-relevant HLA/genetic context and appropriate controls require separate validation. Current Decision displays the imported evidence states and gaps; it does not rank a “best” compound or automatically choose a clinically useful intervention.

## Explicit import and read API

After importing discovery, target identity and Phase 3.3 pharmacology:

```sh
axis --database study.duckdb cellular import-package --project AXIS-DD-ERAP1-CURATED-001 --protein '<imported protein ID>'
```

Reads use `/api/projects/{project}/targets/{protein}/cellular` and subroutes:
`experiments`, `experiments/{id}`, `readouts`, `assessments`, `immunopeptidome`, `engagement`, `evidence-chain`, `concordance`, `gaps`, `decision`, `review-packet`.

Collections accept bounded pagination; applicable routes accept compound scope. Unsupported filters and unknown/out-of-scope records are rejected. GET never performs literature search, source download or provider retrieval. Read projections disclose truncated windows.

Cellular Evidence, HLA phenotype, genetic/chemical comparison, Decision and next-experiment views share source/measurement drawers and accessible text states. Existing Chemistry compound detail links to its scoped cellular evidence. Review decisions are exported separately in `phase3-cellular-scientific-review-packet.json` and are not auto-accepted.

## Limits and next step

This is a small source-informed, AI-assisted slice, not a systematic review or validated clinical engine. Exact DG013A substance, chemical dependency, exposure schedules and ERAP1 allotypes are incompletely resolved. Off-target contributions cannot be excluded. Data in generic cell lines cannot establish efficacy across axSpA, and patient-derived ex vivo immune response does not establish disease improvement.

Review extraction, contexts, identity links, engagement, dependency, phenotypes, disease relevance and concordance independently before accepting any assessment. Further work should address the actual engagement/dependency gaps through an experimental decision workflow; no molecular design, clinical development or automatic Phase 3.5 is included.
