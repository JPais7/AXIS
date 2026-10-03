# Permuted-label negative control

This control reuses the two prepared adult whole-blood SLE cohorts but shuffles
case-control labels independently inside each cohort using seed `20260806`.
Sample identifiers and group sizes are preserved. The analysis runs in an
isolated data root so it cannot overwrite the positive benchmark.

The expected result is `not_passed` under the unchanged interferon criteria.
A positive-control `passed` result after permutation is a control failure and
must trigger investigation. One permutation does not estimate a false-positive
rate; a future extension should run many seeds and report the empirical pass
frequency.

That extension has now been executed with 100 seeds and is documented in
`CALIBRATION-100-PERMUTATIONS.md`.
