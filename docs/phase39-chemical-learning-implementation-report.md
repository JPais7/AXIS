# Phase 3.9 — implementation and acceptance report

## Git

| | |
|---|---|
| Branch | `phase39-chemical-learning` |
| Baseline `origin/main` | `93fb98e15d3d1ae4c47df183a9f1136b77d712e4` (Phase 3.8 merged; migration 012, `axis/computational`, both frozen computational packages and the Phase 3.8 acceptance docs verified present) |
| Merge base | `93fb98e15d3d1ae4c47df183a9f1136b77d712e4` |
| Implementation commit | `db4cd61e05dfd09c243cb51d4978a432dae8d9bb` (all local gates below were run on it) |
| Ahead / behind main | 1 / 0 at that commit; the documentation commit that adds this report follows |
| Merges | none |

## Architecture

`axis/learning/`: `dataset.py` (context-correct frozen datasets, comparability),
`sar.py` (matched pairs, scaffold groups, hypotheses), `eligibility.py` (the gate),
`models.py` (four small numpy/scipy models, splits, metrics, applicability),
`selection.py` (rules `NEXT-001…007`), `service.py` (explicit mutations, state).
Storage: `axis/storage/learning.py` (immutable puts) and
`013_chemical_learning.sql` (10 additive tables, no DROP/ALTER/UPDATE/DELETE;
migrations 001–012 byte-identical to `93fb98e`). CLI under `axis chemistry`; read-only,
project-isolated API under `/api/projects/{p}/chemical-learning`; workspace page
*Chemical Learning*. Phase 3.8 compound preparation, descriptors, scaffolds and
fingerprints are reused; no second compound, assay or evidence registry exists. No new
dependency (NumPy, SciPy and RDKit were already declared); scikit-learn was not added
because four small, fully inspectable estimators do not need it.

## Methods, versions and environment

Descriptor ridge, training-mean, 1-NN and weighted kNN (k=3); Morgan r=2, 1024 bits;
Butina not used here; RDKit 2025.09.3, NumPy 2.5.1, SciPy 1.18.0, Python 3.14.6
(project target 3.12; CI covers it), Node v26.9.0, macOS arm64. Policies are fingerprinted
(dataset, eligibility, model, selection). Model artifacts are JSON, never pickle.

## ERAP1 learning dataset (real indexed chemistry)

* 3 compounds (Maben compounds 1–3, identities untouched, including the unresolved
  stereochemistry/tested-form notes), 15 measurements, 7 assays across 3 targets.
* 9 frozen datasets, one per assay context: ERAP1 L-AMC IC50 (compounds 1, 2),
  ERAP1 L-AMC AC50 (compound 3, an activator, kept apart), ERAP1 L-AMC fold activity,
  ERAP1 WK10 IC50 (2), ERAP1 pNA Ki (2), ERAP1 LF9 Ki (1), ERAP1 HeLa presentation IC50
  (cellular, 2), ERAP2 R-AMC IC50 (2, both `> 200 µM`), LNPEP (mouse) L-AMC IC50 (2, both
  `> 200 µM`). Censored values stay `>` and are never boundary values.
* Directly comparable pairs of datasets: none (36 comparability assessments, all
  `not_directly_comparable`: different endpoint, substrate, target/species or biochemical
  versus cellular).
* Observed SAR: no matched molecular pair exists (no two compounds share a core); the
  only observed records are 15 algorithmic scaffold-group records. No SAR hypothesis is
  proposed. Contradictions: none.
* Eligibility: **not_eligible for all 9** (6 `SAR_ONLY`, 3 `INSUFFICIENT_DATA`); e.g.
  ERAP1 L-AMC IC50: 2 exact compounds (policy minimum 20), 1 Murcko scaffold (minimum 5),
  exact range 0.04 log10 (minimum 1). **MODEL NOT BUILT.** The same generic rules refuse
  the synthetic 3-compound context; no ERAP1 special case exists (tested).
* What would improve learnability, tied to these limits: more compounds measured in one
  assay context (for ERAP1, the most populated is L-AMC IC50), spanning several scaffolds
  and a wider activity range; a measured matched pair in that context; a directly
  comparable selectivity assay for ERAP2/IRAP; repeat measurements where a value is
  borderline. No minimum was invented to demand more compounds.

## Synthetic benchmark (SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE)

51 invented compounds on 6 scaffolds, designed signal activity = f(Crippen logP, TPSA) +
noise, with censored values (`>` at the 90th percentile), replicates, one contradictory
compound, a second assay with a different substrate (never pooled), a permuted-labels
context and dates for a temporal reveal. Measured: the main context is eligible; the
3-compound substrate-2 context is refused; the descriptor model beats the mean and
nearest-neighbour baselines by more than 10 % on a scaffold split with no overfit flag; the
permuted-labels context does not materially beat the baseline averaged over five seeds
(and a single seed can flatter it, which is why single splits are never reported alone);
prospective predictions for later compounds are frozen; revealing them yields dataset r2,
a model, a new learning state whose diff names the cause, and unchanged historical
predictions. Genericity is tested: no target, compound or ERAP1 name appears in generic code.

## Validation (local, on `db4cd61`)

| Gate | Result |
|---|---|
| Phase 3.9 tests | 61 passed |
| Full Python | 691 passed, 2 skipped |
| Ruff, Phase 3.9 scope | all checks passed |
| Ruff, `axis tests` / global | 4 `UP038` (pre-existing) / 289, identical to main |
| mypy strict | no issues, 162 files |
| Frontend (clean `npm ci` copy) | `tsc`, `eslint`, 62 node tests pass; build passes |
| Playwright | `learning.spec`: ERAP1 state 2/2 (1440, 1024) and the synthetic full-loop test pass, each on its own demo database |
| Migration 013 | upgrade from a version-12 database keeps Phase 3.8 data; read-only reopen; 001–012 unchanged |
| Deterministic and offline replay | dataset checksum, model fingerprint, validation and SAR identical across clean stores with sockets blocked |
| Installed wheel | built from `db4cd61`, clean venv, offline: refusal, SAR, model, state and CLI pass |
| Resource checksums | pass; fixture rebuilt byte-identically |
| CLI / API smoke | in the 61 tests (refusals, full flow, GET purity, project isolation) |

Not executed: `decision.spec`, `results.spec`, `structure.spec`, `cellular.spec`,
`workspace.spec`, `pharmacology.spec` browser specs (they need separately provisioned
databases); the synthetic and ERAP1 learning specs were each run only against their own
database (the ERAP1 expectations fail on the synthetic database and vice versa, by design).

## Leakage audit

Same-compound, duplicate-structure, shared-scaffold (scaffold split) and
training-after-test (temporal) leakage are detected and invalidate a split; training
compounds cannot be predicted (circular); a prediction made after the result was known
cannot be `prospective`; fitting uses only the dataset's own measurements. Confirmed
leakage invalidates the evaluation; none was found in the shipped benchmarks.

## Limitations

Phase 3.9 does not establish prospective, clinical or general drug-discovery validity,
therapeutic efficacy, target engagement from QSAR, cellular activity from biochemical
models, selectivity without comparable measurements, causality from SAR correlations,
safety, ADME/PK, patent novelty, synthesizability, activity of untested compounds, or
superiority to medicinal chemists. A model can be statistically valid within its
benchmark and still be scientifically unhelpful outside its applicability domain. The
single-cut matched-pair method does not detect hydrogen replacements; the synthetic
signal is designed; ERAP1 remains too small and fragmented for any model; the policy
thresholds are AXIS policy, not statistical laws; Phase 3.7 temporal infrastructure was
not re-used for a chemistry backtest because no dated real ERAP1 measurements exist
(the synthetic temporal reveal uses its own cutoff).

## Scientific acceptance

1. Coherent datasets without pooling incompatible measurements: **SUPPORTED**.
2. Observed SAR vs inferred SAR vs prediction: **SUPPORTED**.
3. Refusing modelling when data are inadequate: **SUPPORTED** (ERAP1, small and
   all-censored datasets, duplicates, no diversity).
4. Eligible models compared with a simpler baseline under leakage-resistant validation:
   **SUPPORTED IN TESTED CASES** (synthetic only).
5. Every prospective prediction traceable to a frozen dataset, model, cutoff and
   applicability: **SUPPORTED**.
6. Next compounds chosen to reduce chemical uncertainty rather than highest predicted
   potency: **PARTIALLY SUPPORTED** (explicit rules and rationale categories exist and are
   tested; hypothesis discrimination is exercised only with synthetic hypotheses and no
   external result has arrived).
7. New evidence updates the learning state without rewriting history: **SUPPORTED**.

ERAP1: does Phase 3.9 establish a validated predictive QSAR model? **NOT DEMONSTRATED**
(refused, correctly). Product value — does AXIS now learn something explicit and auditable
from experimental chemistry that could change which compound is tested next:
**SUPPORTED IN TESTED CASES** (synthetic); for real ERAP1 chemistry the explicit,
auditable lesson is that the data are not yet learnable.

## Release verdict

PASS WITH CONDITIONS — remote CI is recorded below; no independent medicinal-chemistry
review; ERAP1 too small for modelling; no prospective experimental validation.
