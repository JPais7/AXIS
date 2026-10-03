# Calibration with 100 label permutations

The complete two-cohort genome-wide workflow was repeated 100 times using
seeds 20260806 through 20260905. Labels were shuffled within each cohort while
preserving samples and group sizes. Each run repeated differential expression,
cross-study recurrence ranking and the unchanged locked interferon evaluation.

## Results

- False positive benchmark passes: 0/100.
- Empirical false positive rate observed: 0%.
- Approximate 95% upper bound with zero events (rule of three): 3%.
- Median locked interferon genes in the top 100: 0.
- Maximum locked interferon genes in the top 100: 0.
- Recurrent genes under the two-study significance rule: 0 in every run.
- Runtime: 778 seconds on the recorded local environment.

The positive result (10/12 locked genes in the top 100) was therefore not
reproduced by any of these 100 within-cohort label permutations.

## Interpretation boundary

This supports specificity of the frozen benchmark under this permutation null
and provides no evidence of obvious label leakage. It does not prove a universal
false-positive rate of zero: the calibration covers two datasets, one null
mechanism and 100 deterministic seeds. The recurrence gate is stringent, and
its operating characteristics should later be tested in additional diseases and
under nulls that preserve or disrupt other forms of biological structure.
