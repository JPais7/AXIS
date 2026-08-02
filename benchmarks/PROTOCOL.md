# Predeclared AXIS scoped comparison protocol

Protocol version: 2.0, dated 2 August 2026. This replaces version 1.0 after the
internal pilot showed that a common synthetic matrix was not accepted by every
comparator and that differential-expression tools were being scored on
evidence-governance tasks outside their scope.

## Comparison 1: differential expression

Question: can each in-scope workflow execute and export the same unadjusted
case-control contrast?

Workflows are AXIS, GEO2R, a documented manual statistical workflow and
ExpressAnalyst. NetworkAnalyst is excluded because its current service directs
transcriptomic data tables to ExpressAnalyst.

The input is public accession GSE18781, platform GPL570. The 18 SpA cases and
25 healthy controls are frozen by GSM identifier in
`expression-sample-groups.tsv`. The primary model is the unadjusted
case-control contrast so all workflows receive an estimand they can implement.
Any batch-adjusted model is secondary and reported separately.

Outcomes are successful access, elapsed time, measurement method, manual
decisions, exact sample assignment, probe-level effect export, multiplicity
correction, complete method record and machine-readable output. Agreement is
described using pairwise effect correlation and prespecified top-100/top-500
overlap. No workflow is biological ground truth.

## Comparison 2: evidence governance

Question: can each in-scope workflow preserve study eligibility, participant
independence, evidence roles, provenance and bounded claims?

Workflows are AXIS and a documented manual evidence review. Inputs are the
synthetic candidate-study and cohort-evidence tables with frozen known traps.
GEO2R and ExpressAnalyst are excluded because these tasks do not test their
declared differential-expression purpose.

Outcomes are detection of disease and tissue mismatch, treatment, pooling,
repeated participants, repository duplication, correct unique-participant
counting, exclusion of duplicates and incompatible evidence, provenance and a
conclusion bounded to association.

## Shared execution and scoring

Two reviewers independently follow the generated standard operating procedure.
Each criterion is `pass`, `fail` or `not_applicable`; missing evidence is
`fail`. Initial ratings are frozen before consensus. Runtime cannot compensate
for a guardrail failure, no weighted overall score is calculated, and ranking
across the two comparisons is prohibited.

Report workflow versions or access dates, operating system, hardware, input
checksums, all deviations, failed attempts and raw tables. Comparison 1 is
limited to one public contrast. Comparison 2 is synthetic and supports no
biomedical claim. Neither comparison establishes general superiority.

Generate the package with `axis prepare-workflow-comparison` and combine two
frozen assessments with `axis summarize-workflow-comparison`.
