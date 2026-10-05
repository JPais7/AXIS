# Phase 3.9 — model method audit

| Method | Learns | Input | Assumptions | Policy size | Validation | Baseline | Supports | Does NOT support |
|---|---|---|---|---|---|---|---|---|
| Training mean | the average activity | none | all compounds alike | any | — | is the baseline | a floor to beat | any structure claim |
| 1-nearest neighbour | the value of the most similar measured compound | Morgan r=2, 1024 bits, Tanimoto | similar structure → similar value, locally | ≥ 20 exact compounds | scaffold/random/temporal split | mean | local interpolation | similar activity as a rule |
| Similarity-weighted kNN (k=3) | a similarity-weighted local mean | as above | as above | ≥ 20 | as above | mean, 1-NN | smoothing among neighbours | extrapolation outside the training chemistry |
| Descriptor ridge | a linear trend on MW, Crippen logP, TPSA, HBD, HBA | standardised descriptors | linearity in those descriptors | ≥ 20, ≥ 5 scaffolds | as above + 5 seeds + 50 permutations + leave-one-scaffold-out | mean, 1-NN (≥ 10 % better) | a bounded trend inside the domain | a mechanism, potency of untested chemistry, selectivity, cellular activity |

* Eligibility is the first validation: below policy the model is **not built**.
* Applicability: max Tanimoto to training (≥ 0.5 inside; 0.3–0.5 near boundary; < 0.3
  outside) plus descriptor ranges; no calibrated numerical uncertainty exists.
* Cross-validation-style performance is not prospective validation; a prospective
  prediction is frozen and compared with a later measurement only through the outcome
  assessment.
* Library versions are recorded per model (Python, RDKit, NumPy, SciPy). Models are JSON,
  deterministic given dataset, split, seed and policy; floating-point output may differ
  across platforms in the last digits.
* The synthetic benchmark's signal is designed (activity = f(Crippen logP, TPSA) + noise),
  so a descriptor model beating the baseline there says nothing about any real target;
  the permuted-labels context must not materially beat the baseline over five seeds, and a
  single favourable scaffold split can flatter it (the audit exists because it did).
