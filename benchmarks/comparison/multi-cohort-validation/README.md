# Multi-cohort AXIS–limma validation

This technical validation compares the unadjusted moderated AXIS group contrast
with native limma 3.68.4 under R 4.6.1. It covers four public GEO cohorts, three
platform contexts and 163 analyzed samples.

Across every study:

- all probe-level case-minus-control directions agreed;
- effect Spearman correlation was approximately 1.0;
- adjusted-p-value Spearman correlation was 1.0;
- top-100 overlap was 100/100;
- top-500 overlap was 500/500;
- maximum absolute effect differences were below 5.1e-12.

GSE73754 was rerun without covariates solely for this like-for-like technical
comparison. Its existing covariate-adjusted biological analysis was backed up
and restored byte-for-byte. The full regenerated comparison outputs remain in
the ignored local `.comparison-work` directory; this package retains executable
scripts, summaries and checksums.

These results validate numerical implementation for the frozen contrasts. They
do not establish biological truth, general superiority, or equivalence for
covariate-adjusted, paired, RNA-seq or single-cell models.
