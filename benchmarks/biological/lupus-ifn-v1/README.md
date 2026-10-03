# SLE type-I-interferon positive-control benchmark

This frozen benchmark asks whether AXIS can recover established interferon
biology in human systemic lupus erythematosus without pooling incompatible
tissues, cell populations, ages or treatment designs.

The listed GEO accessions are candidates, not approved inputs. Each must pass
the normal AXIS participant-, design- and provenance-level eligibility review.
The primary analysis is restricted to compatible peripheral whole-blood
case-control cohorts. Other contexts remain separate sensitivity or contextual
strata.

After eligible cohorts have been prepared and analysed, generate the normal
AXIS recurrence ranking and evaluate it without editing either frozen JSON file:

```shell
axis evaluate-biological-benchmark data/analysis/recurrence-ranking.tsv
```

A pass requires at least five of the twelve locked reference genes in the top
100, concordant higher expression in cases, and hypergeometric enrichment at
`p <= 0.05`. A failure is retained as a result rather than repaired by changing
the reference, thresholds or cohorts after inspecting the ranking.

This is a positive control. It cannot establish causality, diagnostic accuracy,
new SLE biology or superiority over another workflow.

The first frozen execution is documented in `EXECUTION-2026-08-06.md`; its
machine-readable outputs are under `data/analysis/benchmarks/lupus-ifn-v1`.
