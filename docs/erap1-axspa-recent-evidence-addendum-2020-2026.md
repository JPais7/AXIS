# ERAP1 × AS/axSpA: bounded recent-evidence addendum

Version v1, assessment date 5 October 2026. Window: 2020-01-01 to 2026-10-05.
Baseline main: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
Branch: `codex/erap1-recent-evidence-addendum-2020-2026`.

## Scope and independence

This is a targeted accessible-primary-evidence addendum, not a systematic review,
complete screening exercise, or independent expert acceptance. The earlier refresh
at `a3cbb37a5681a057dfe1c86c7e8686553d95c4b2` remains
`INSUFFICIENT REFRESH COMPLETENESS TO ASSESS`. This new package does not supersede
that conclusion or pretend to adjudicate inaccessible evidence.

Eight bounded Europe PMC searches (maximum 40 responses each, default API ordering)
plus nine identifier-verification queries yielded 176 deduplicated metadata records.
API truncation/default ordering can bias discovery toward recent/indexed material.
These 176 records were **not all scientifically screened**. Eighteen high-value
candidates were purposefully selected across biology, pharmacology and translation.
Selection is bounded, not random; ten sufficiently inspectable primary studies were
curated. Ten publications are not ten independent patient cohorts: some are cell,
protein or model experiments, and the genomic study reuses public biobanks.

ClinicalTrials.gov, Crossref/OpenAlex accessibility metadata, legitimate publisher
links and RCSB entry/polymer records supplement the retrieval. Every scientific
assertion is based on inspected primary methods/results, not an OA flag, an abstract,
a review or an HTTP 200 that contains only metadata. No copyrighted article body
is committed. Retrieval logs contain URLs, dates, identifiers and hashes; inspected
sections, experimental context and limitations accompany assertions.

## Selection and frozen package

Package: `axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1/`.
Its [study-selection table](../axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1/study-selection.md)
and `candidate-studies.json` document all 18 actions and rationales.

| Action | Publications/records |
|---|---:|
| INTEGRATE (addendum inclusion, **not expert approval or canonical import**) | 10 |
| CONTEXTUALIZE (trial registration, no efficacy results) | 1 |
| ALREADY_INDEXED | 1 |
| INSUFFICIENT_ACCESS | 4 |
| DO_NOT_INTEGRATE in this bounded version | 2 |

Ten newly integrated studies meet the methods/results criterion. One already-indexed
paper also has a sufficient baseline basis; one other full text was located but not
fully methodologically curated in this version. The registry is accessible for
registration facts, not clinical efficacy. These categories must not be conflated.

The package contains 21 `source_assertion` claims and ten `axis_inference` impact
assessments, all `pending_review`. `curation.json` is explicit manual AI-assisted
curation; the freeze script only constructs deterministic views, never classifies
scientific findings. `manifest.json` plus `manifest.sha256` freezes resource bytes.

## Scientific additions

Wang 2022 adds Taiwanese AS case-control association and a small HLA-B*27:04 AS PBMC
comparison (7 versus 4 donors). Sex imbalance, population-specific labels and the
absence of a significant B27-positive haplotype comparison limit generalization.
ERAP1-001/002 are local sequence labels, not automatically conventional Hap1/Hap2.
Tedeschi 2023 adds four-marker ERAP1/ERAP2 haplotypes and expanded antiviral/self-
cross-reactive CD8 responses. These are not complete allotypes, pathogenic proof,
direct immunopeptidomics or therapeutic validation; healthy responses also occur.

Tran 2023 adds germline ERAP1-loss perturbation in HLA-B27 transgenic rats:
arthritis incidence falls, but colon histology worsens; intracellular misfolding
and surface free-heavy-chain readouts diverge. Lifelong loss/prevention is not
pharmacological reversal, universal inhibition benefit, or human remission.

Hutchinson 2021, Temponeras 2024 and the 2025 expression-matched A375 study strengthen
allotype/substrate context. Protective allotype 10 is not simply inactive for all
substrates. A375 is not a B27-positive patient model; clone selection and replication
are retained as limitations. The 2025 A375/THP1 proteome study shows differing KO
versus inhibitor effects and broader cellular pathways, not a matched drug-in-null/
rescue dependency demonstration. Its compound 3 is **not** Maben compound 3.

The cyclohexyl-acid 2024 study adds biochemical peptide trimming, HeLa presentation
and ligand-bound structures, not intact-cell occupancy. Four linked PDB entries
were released January 2025. Construct/reference conflicts and linker/tag mapping
prevent automatic allotype equivalence; conformation and missing-residue ranges
were not independently coordinate-validated. Maben 2021 adds solution/conformational
context; a docked pose is not an observed ligand-bound structure. Its 2023 correction
concerns acknowledgement of a facility, not changed experimental results.

The 2026 public-biobank AS meta-analysis adds genetic prioritization but no ERAP1
experimental knockdown or HLA-B27-conditioned validation. AS is not every axSpA
phenotype. Computational fine-mapping/cTWAS is not a drug-direction experiment.

## Chemistry and inaccessible material

`chemical-matter.json` records source-local identities, substrates/endpoints,
operators/units, tested-form uncertainty and source locators. Numeric entries are
source-level observations, **not standardized learning measurements**. Main-text
methods support the limited claims; uninspected SI/chemical form/construct gaps
prevent pooling. Compound 7 ERAP2/IRAP pIC50 `<4` values remain censored, n=1;
cross-substrate ratios are `NOT DIRECTLY COMPARABLE`. Seven chemical records are
not seven new verified molecules or seven new training rows.

Four cases remain outside assertion extraction:

- Babaie 2023: patient macrophage/NK report; compound, exposure and controls not verified.
- Wu 2025 MR (PMID 40349828): OA metadata now says hybrid, but inspected publisher/TDM
  routes yielded no scientific body. Circulating proteomic proxy is not intracellular
  activity or inhibition; instrument strength and pleiotropy methods remain uninspected.
- Corilagin 2025 (PMID 40680611): **POTENTIALLY_MATERIAL**,
  `INSUFFICIENT_FULL_TEXT_ACCESS_FOR_AXIS_ADJUDICATION`. Abstract-level screening,
  interaction, enzyme/active-site and HLA-B27 phenotype reports are stored separately.
  Intact-cell versus lysate/protein binding, exposure, selectivity, dependency and
  appropriate controls cannot be adjudicated. This does not block other accessible
  curation, nor does it resolve engagement.
- Carnosic-acid 2024: supplement-only historical inspection, main methods unavailable;
  no new accepted identity bridge, assertion or training import.

Legitimate access checks are documented in `material-access-check.json` and
`context-access.json`. Three Elsevier TDM responses were HTTP 200 but metadata only;
ACS returned 403. No access circumvention or invented methods were used.

## Clinical and decision boundaries

EAST1 `NCT07047703` is an ERAP1-directed phase I/II HLA-B27-positive axSpA registration
with no posted results in the frozen record. Other retrieved registry records also
had no posted results. Therefore: no AS/axSpA human interventional **efficacy results**
were identified in the searched sources. Do not claim that no trial exists. Sponsor
oncology reports were not promoted into AS evidence.

The bounded update strengthens biological rationale and context constraints, not a
universally preferred inhibition strategy. It produces `AddendumDecisionImpact`,
not canonical DecisionState v2: **decision unchanged based on accessible curated
evidence**. Priority remains cellular engagement plus chemical-genetic dependency;
experiment specification is refined. Original v1 resources/PDFs remain unchanged.
See [decision-impact assessment](erap1-axspa-recent-evidence-decision-impact.md).

## Reproduction and review

Run `python -m axis.evidence_addendum` from an installed wheel, without network.
This audits package integrity, claim eligibility and frozen impact references; it
does **not** rerun experiments, rescreen literature, prove scientific correctness,
approve claims or recompute the canonical decision engine. Cache paths and article
bodies are not required. SHA-256 detects byte changes, not adversarial authenticity.

Independent scientific review pending. New assertions/inferences require an external
scientific reviewer before acceptance. Commercial v1.1 is an explicitly bounded,
pending-review briefing, not a validated therapeutic recommendation. Validation
results and publication details are recorded in `erap1-addendum-validation.md`.
