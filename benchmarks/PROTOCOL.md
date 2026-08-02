# Predeclared AXIS comparison protocol

Protocol version: 1.0, dated 2 August 2026. Define and freeze the comparison
before collecting results.

## Question

Does AXIS preserve scientific eligibility, participant independence,
cross-study provenance and claim limitations more completely than a rapid
single-study workflow, without unacceptable local runtime or memory use?

The benchmark does **not** test whether AXIS produces smaller p-values or
replaces the statistical methods in limma, DESeq2 or edgeR.

## Comparators

1. AXIS release candidate using documented commands.
2. GEO2R for each eligible GEO series independently.
3. A scripted/manual workflow using established statistical packages.

Galaxy may be added as a fourth workflow only if the exact server, tool
versions and history export are frozen before execution.

## Frozen tasks

### Task A: synthetic installation check

Run the packaged AXIS demonstration. GEO2R is not applicable because the input
is a synthetic cross-cohort summary rather than a GEO Series.

### Task B: blinded study triage

Provide every workflow with the same candidate-accession list and public
metadata. The evaluator is blinded to the AXIS eligibility decisions. Record
whether each workflow identifies disease mismatch, tissue mismatch, treatment,
pooled samples, repeated participants and repository duplication.

### Task C: within-study expression analysis

Use the same predeclared sample groups and contrast. Compare gene identifiers,
effect direction, multiplicity correction, method record and ability to export
an executable analysis.

### Task D: cross-study claim construction

Ask each workflow to state which studies support a primary synthesis, which are
sensitivity-only and which must be excluded. Record whether incompatible raw
effects are pooled and whether the valid conclusion is bounded.

## Outcomes

Primary outcomes, scored by two reviewers where judgment is required:

- eligible participants counted correctly;
- duplicate participants/cohorts detected;
- incompatible studies kept out of the primary synthesis;
- inputs and outputs linked by provenance;
- complete executable or machine-readable method record;
- conclusion does not exceed association supported by the inputs.

Secondary outcomes:

- installation success without author intervention;
- wall-clock time;
- peak memory, with measurement method stated;
- output size;
- number of manual decisions;
- reviewer disagreements and their resolution.

## Scoring rules

Each primary outcome is `pass`, `fail` or `not_applicable`; never convert these
to a single weighted quality score. Runtime cannot compensate for a scientific
guardrail failure. Missing information is not assumed correct. Disagreements
are resolved by consensus after both initial ratings are preserved.

## Reporting

Report versions, operating system, hardware, dates, all deviations, failures
and raw assessment tables. Keep the synthetic benchmark separate from the
DDX24 biological result. Do not claim superiority until the protocol has been
executed by an independent reviewer.

The versioned synthetic evaluator package is generated with
`axis prepare-workflow-comparison`. Two frozen initial reviewer tables are
combined with `axis summarize-workflow-comparison`; unresolved disagreements
remain explicit until a separately documented consensus step.
