# Bounded AddendumDecisionImpact, not DecisionState v2

Canonical baseline `decision-state:1:cebbae3880aeec90` is unchanged.
**Decision unchanged based on accessible curated evidence.**
All interpretation here is `axis_inference`, `pending_review`; no inaccessible
report was treated as scientific adjudication. The historical failed refresh remains
`INSUFFICIENT REFRESH COMPLETENESS TO ASSESS`.

## Before / recent accessible evidence / after

| Layer | Current AXIS | Recent accessible evidence | Updated interpretation |
|---|---|---|---|
| Target–disease | Indexed AS biology, no validated therapy | Human association and rat perturbation | Biology stronger; therapy separate |
| Genetics | Historical association | Taiwanese haplotypes, public European meta-analysis | More context; ancestry and reused cohorts matter |
| HLA interaction | B27-related phenotypes | B27-stratified humans, B27/B7 model comparison | Strengthened, not all HLA/all axSpA |
| Allotype context | Unresolved context | Recombinant and expression-matched studies | Stronger requirement; SNP/allotype labels not interchangeable |
| Mechanism | Partial peptide/FHC bridge | Folding, CD8 responses, broader pathways | Richer, not one universally causal pathway |
| Perturbation | Mixed genetic/chemical effects | Germline loss, KO/inhibitor divergence | Loss/inhibition/allosteric modulation not equivalent |
| Structure | Open 3QNF context | Conformational work, four regulatory-site complexes | More observations, not cellular occupancy/druggability |
| Chemistry | Three indexed Maben compounds | Cyclohexyl acid tools | More options, no automatic identity substitution |
| Biochemical pharmacology | Context-fragmented activity | Allotype/substrate-sensitive assays | Assay-specific, not universal pooled potency |
| Cellular phenotype | Engineered perturbation | PBMC/CD8/cancer-cell contexts | Patient phenotype is not clinical response |
| Cellular engagement | Baseline not assessed directly | No integrated exposure-matched baseline-compound test | Still unresolved; inaccessible reports not adjudicated |
| Target dependency | Drug-specific gap | Genetic perturbation, parallel inhibitor comparisons | Matched chemical-genetic dependency not demonstrated |
| Selectivity | Unresolved/non-comparable | Sparse ERAP2/IRAP new-series counter-screen | Partially informative, NOT DIRECTLY COMPARABLE |
| Translation | No indexed disease rescue | Rat incidence benefit, divergent GI effects | Partial modification, not human remission/reversal |
| Clinical | No efficacy indexed | EAST1 registration, no posted results | Development exists, no efficacy established here |

## Competing explanations

On-target: baseline `partially_supported` → better biologically contextualized, but
compound attribution unresolved. Tran and cyclohexyl studies support plausibility,
not baseline compound occupancy or dependency.

Off-target: `viable` → `viable`. Limited counter-screens in a different series do
not resolve the selectivity of the baseline perturbagens.

Indirect: `viable` → viable and more explicit. Proteome/ROS pathways provide
alternative routes, not proof of the AS compound mechanism.

Context: `viable` → strengthened as a constraint. Allotype, HLA, ERAP2, substrate,
compartment and organ endpoint can alter interpretation. None of the four
explanations is eliminated because another received support.

## Critical uncertainty and experiment

Critical uncertainty `uncertainty:target_engagement` → same identifier,
**REFINED** interpretation, not RESOLVED/REPLACED. Demonstrate direct or validated
proximal cellular ERAP1 engagement at phenotype-producing exposure in defined
allotype/HLA/ERAP2 context, distinguishing intracellular folding from surface FHC.

Recommended `decision:exp:chemical-genetic-engagement` → same priority,
**REFINED_EXPERIMENT**. Retain WT/null/rescue, vehicle and matched dose/time;
measure engagement and phenotype together. Specify full allotype, HLA-B27 subtype,
ERAP2 and substrate; test viability, interference and genuinely established inactive
analogue. Identity/form and a validated proximal assay are prerequisites. Lifelong
KO must not stand in for partial inhibition. Broader model validation follows
mechanism discrimination rather than substituting for it.

The addendum does not justify a new canonical compound-scoped state: it does not
establish relevant-exposure engagement/dependency for the baseline compounds.
This is not a forced repeated baseline score or a claim that all recent molecules
lack engagement. Inaccessible studies are excluded from that inference.

Chemical Learning: `MODEL NOT BUILT` → `MODEL NOT BUILT` for the unchanged indexed
Phase 3.9 dataset. Zero standardized measurements imported; no eligibility
recomputation justified. Eligibility for all recent chemistry is **NOT ASSESSED**,
not universally refused. No QSAR was trained merely because papers were found.

## Required scientific questions

| Question | Status | Rationale |
|---|---|---|
| Q1 Target–AS relationship | PARTIALLY SUPPORTED | New human association/model perturbation supports biology, not validated intervention |
| Q2 HLA-B27 interaction | SUPPORTED | Human stratification, CD8 subtype and model comparisons add context |
| Q3 Allotype importance | SUPPORTED | Complete sequence, HLA and substrate matter; SNP ≠ allotype |
| Q4 Preferred therapeutic direction | NOT DEMONSTRATED | Mixed model outcomes and substrate-dependent activity do not select universal inhibition |
| Q5 Biochemical pharmacology | SUPPORTED | Recombinant and cyclohexyl assays add context-specific evidence |
| Q6 Patient-derived cellular evidence | PARTIALLY SUPPORTED | PBMC/CD8 data add context; macrophage drug study not adjudicated |
| Q7 Cellular engagement | NOT DEMONSTRATED | No integrated relevant-exposure test for baseline compounds; phenotype/structure not engagement |
| Q8 Chemical-genetic dependency | NOT DEMONSTRATED | Parallel inhibitor/KO is not matched drug-in-null/rescue |
| Q9 Selectivity | PARTIALLY SUPPORTED | Sparse new-series counter-screen; no comparable ratio or baseline resolution |
| Q10 Model disease modification | PARTIALLY SUPPORTED | Germline loss lowers rat arthritis incidence, worsens colon histology; not reversal |
| Q11 Human clinical efficacy | NOT DEMONSTRATED | Trial registration exists; no AS/axSpA efficacy results identified in searched sources |
| Q12 Critical uncertainty changes | PARTIALLY SUPPORTED | REFINED context, same engagement priority, not resolved |
| Q13 Experiment changes | PARTIALLY SUPPORTED | REFINED_EXPERIMENT, same design/priority with explicit controls |
| Q14 Chemical Learning eligibility | NOT ASSESSED | No new standardized rows; baseline refusal unchanged |

Machine-readable full answers, claim references, 15-layer matrix and four explanation
updates are frozen in `decision-impact.json`. Ten study-level assessments have
claim links, affected layers/hypothesis/explanations/uncertainties/strategy/experiment,
categorical direction and rationale. These are not numerical evidence scores.

## Commercial impact and synthesis

v1.1 is justified for a **bounded recent accessible evidence update**, not a change
to validated treatment status. Use:

> The assessment incorporates a bounded addendum of recent primary studies from
> 2020–2026 for which sufficient methods and results were accessible for AXIS
> scientific curation.

> Additional potentially material literature was identified but not adjudicated
> where full methodological information was unavailable.

Independent scientific review pending. The full brief retains the AI-assisted
source/inference distinction. Its traceability maps new commercial conclusions
to inferences, atomic assertions, experiment/context, DOI and source locator.

Relative to the original six-paper corpus, the update adds patient-genotype/CD8
context, substrate-sensitive allotype behavior, divergent model outcomes, broader
cellular effects, new ligand-bound tools and trial-registration context.
Biological rationale and the need for a discriminating experiment become stronger.
Uniform inhibition and a simple FHC-normalization narrative become less defensible.
Compound-specific engagement and dependency at relevant exposure remain unresolved.
The next experiment stays valuable because it can falsify attribution and separate
mechanism from phenotype; its allotype/substrate/compartment controls become sharper.
