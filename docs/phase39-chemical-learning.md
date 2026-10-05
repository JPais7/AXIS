# Phase 3.9 — Chemical learning engine

```
measurements → context-correct dataset → observed SAR → SAR hypotheses
→ eligibility gate → bounded model (only if justified) → frozen prediction
→ explicit next-compound rules → external result (Phase 3.6) → new dataset revision
→ new learning state (history never rewritten)
```

Observed SAR, inferred SAR, model predictions and experimental measurements are
different objects. A prediction is labelled `PREDICTION — NOT AN EXPERIMENTAL
MEASUREMENT` and has class `axis_inference`; it is never written to a measurement table.

## Datasets (`axis/learning/dataset.py`)

* One dataset per assay context (target, species, assay type, format, substrate,
  endpoint). Incompatible measurements offered together are refused; nothing is pooled.
* Concentration units are converted to nM only (µM, mM, M, pM); fold changes stay fold;
  an unconvertible unit excludes the measurement with its reason. Original value and unit
  are always kept next to the normalised ones.
* Inequalities are kept as `>`/`<` and are never exact values; they are excluded from
  fitting rather than substituted by their boundary.
* Replicates stay individual; the per-compound median of exact values is used for
  modelling; exact values more than 3× apart are flagged contradictory, kept, and
  excluded from fitting (never averaged away).
* Datasets are frozen with a checksum and revision; changed content is a new revision,
  an identical rebuild is a no-op, and a stored dataset cannot change.
* Cross-context comparability is explicit: `directly_comparable`,
  `comparable_with_conditions`, `not_directly_comparable`, `insufficient_context`.
  Endpoints (IC50/Ki/AC50) and biochemical/cellular readouts are never converted.

## SAR (`axis/learning/sar.py`)

Matched molecular pairs (RDKit `rdMMPA`, single cut, larger fragment = shared core,
changed fragment ≤ 13 heavy atoms; hydrogen replacements are not detected) produce
`OBSERVED SAR` statements that say only "within the compounds measured…, B had a lower
reported value than A". Algorithmic scaffold groups (Murcko) are not curated series.
Hypotheses (`axis_inference`, pending review) need ≥ 2 pairs of the same transformation
and carry supporting and contradicting observations and a falsification condition.

## Eligibility (`axis/learning/eligibility.py`)

Deterministic, generic, fingerprinted AXIS policy (not a statistical law): ≥ 20
exact-value compounds, ≥ 5 Murcko scaffolds, ≤ 50 % censored, ≥ 1 log10 of exact range,
valid and non-duplicate structures; series concentration and contradictions are
conditions. Conclusions `eligible`, `eligible_with_conditions`, `not_eligible`;
readiness `SAR_ONLY`, `MODEL_ELIGIBLE_WITH_CONDITIONS`, `MODEL_ELIGIBLE`,
`INSUFFICIENT_DATA` (no numeric maturity score). Not eligible → **MODEL NOT BUILT**.

## Models (`axis/learning/models.py`)

Training-mean baseline, 1-nearest-neighbour, similarity-weighted kNN, descriptor ridge
(numpy closed form; alpha from a three-value grid by inner CV). No scikit-learn, deep
learning or pickle: a model is plain JSON with a fingerprint over dataset checksum,
model, split, policy and library versions. Splits: random, scaffold, temporal, each
leakage-checked (same compound, duplicate structure, shared scaffold in a scaffold split,
training measurement after a test one). Reported separately: train and test metrics,
baseline comparison (a model must be ≥ 10 % better in MAE), overfit audit, stability over
five seeds, a 50-permutation label control, leave-one-scaffold-out. R² and Spearman are
suppressed below five test compounds. Uncertainty is qualitative; there is no model score.

## Predictions and applicability

`predict` refuses training compounds (circular), refuses `prospective` when the result
was already known, and stores an immutable prediction (model fingerprint, dataset
checksum, evidence cutoff, intent). Applicability from max Tanimoto to the training set
(≥ 0.5 inside, ≥ 0.3 near boundary, else outside; descriptor ranges can downgrade);
"inside the domain is not high confidence". Outcome assessment is graded
(`quantitatively_supported` … `contradicted`, `outside_applicability`, `non_comparable`,
`experimental_result_ambiguous`, `not_tested`) and never touches the prediction.

## Next compounds and learning state

Explicit rules `NEXT-001…007` assign exploitation, exploration, hypothesis
discrimination, model boundary, negative control and replication; there is no
acquisition score, conflicts are shown, and synthesis/purchase availability is never
asserted. `ChemicalLearningState` is versioned; its diff names the cause (new evidence or
dataset revision, model added) and prior predictions and models are never rewritten.

## Surfaces

CLI under `axis chemistry`: `dataset build|list|show`, `sar show|pairs`,
`model eligibility|train|list|show`, `prediction list|show`, `learning-state`,
`next-compounds`. Read-only API `…/chemical-learning[/datasets|comparability|sar|
eligibility|models|predictions|learning-state]` (GET never builds or trains). Workspace
page **Chemical Learning**. Migration `013_chemical_learning.sql` (10 tables, additive).
