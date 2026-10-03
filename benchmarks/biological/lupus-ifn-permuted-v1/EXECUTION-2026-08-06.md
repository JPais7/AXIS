# Execution record — 6 August 2026

Case-control labels were shuffled independently inside GSE49454 and GSE61635
with the frozen seed `20260806`. Group sizes, samples, platforms, preprocessing,
gene mapping and reference genes were unchanged. The run used an isolated copy
of the prepared data and did not overwrite the positive-control outputs.

## Result

- Significant genes within GSE49454: 0.
- Significant genes within GSE61635: 0.
- Recurrent genes across both cohorts: 0.
- Locked interferon genes in the top 100: 0 of 12.
- Hypergeometric enrichment p-value: 1.0.
- Biological evaluator status: `not_passed`.
- Negative-control expectation met: `true`.

The highest-ranked locked gene was IFI27 at rank 639. All other locked genes
ranked below 6,000. This is the expected negative-control result and provides no
evidence of obvious label leakage in this deterministic permutation.

## Boundary

One permutation is not an empirical false-positive-rate analysis. It tests one
fixed null realization. A stronger future calibration should run many frozen
seeds and report the fraction that incorrectly meet the positive-control rule.
