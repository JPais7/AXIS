# Execution record — 6 August 2026

## Frozen question

Can AXIS recover the established type-I-interferon blood signature in human
systemic lupus erythematosus while preserving participant independence and
biological strata?

## Primary inputs

| Study | Role in this benchmark | Platform | Included cases | Controls | Participant rule |
|---|---|---|---:|---:|---|
| GSE49454 | adult whole-blood cohort 1 | GPL10558 | 58 | 20 | V1 only; later visits excluded |
| GSE61635 | adult whole-blood cohort 2 | GPL570 | 64 | 30 | V1 only; later visits excluded |

The analysis therefore contained 172 independent participants: 122 SLE cases
and 50 healthy controls. GSE49454 originally contained longitudinal visits;
GSE61635 contained repeated visits for some cases. The prepared matrices, not
only the analysis sheet, exclude later observations.

## Deliberately separate evidence

- GSE50772: PBMC, not pooled with whole blood.
- GSE65391: paediatric and longitudinal, sensitivity stratum only.
- GSE72509: whole-blood RNA-seq, separate assay stratum.
- GSE88884: baseline samples from two phase III trials, reserved as possible
  large external validation and not allowed to dominate the primary test.

## Result

The benchmark passed. Ten of twelve locked reference genes occurred in the top
100, all ten had the prespecified higher-in-case direction, and the
hypergeometric enrichment p-value was 4.3387106307582677e-23. OAS2 ranked 114
and SIGLEC1 ranked 148. The analysis ranked 24,995 gene records and identified
1,035 recurrent genes under the standard two-study rule.

## Quality and claim boundary

QC flagged two candidate outliers per cohort; they were not removed after
inspection of the benchmark result. Medication and activity are heterogeneous,
and GSE61635 is enriched for anti-RNP-positive SLE. This positive control shows
that AXIS can recover known interferon biology in this frozen two-cohort use
case. It does not establish diagnostic accuracy, causality, novel SLE biology,
or general superiority over other tools.
