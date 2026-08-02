# Standard operating procedure

## Roles and blinding

Each reviewer operates every in-scope workflow independently. Reviewers must not consult
each other or the `coordinator-reference` directory before both initial result
and assessment files are frozen. Use coded reviewer identifiers. Record all
deviations; do not repair an output after seeing a reference answer.

## Common environment and timing

Within each comparison, use the same computer and network for all workflows. Record OS,
hardware, workflow version or web access date, browser where relevant, and every
manual decision. One untimed familiarisation attempt per workflow is permitted.
For each measured task, start timing immediately before the first workflow action
after opening the required input and stop when all required exports are saved.
Include uploads and downloads; exclude the familiarisation attempt. Record failed
attempts. Measure output size as the sum of exported result files. Record peak
memory with the same OS tool where possible; if a hosted service prevents this,
record `measurement_unavailable_hosted_service` and the method attempted.

## Allowed operations

Use only the named workflow, official documentation and declared comparison
inputs. Do not use another workflow to repair or transcribe results.
`manual_statistics` may use a spreadsheet or one general-purpose statistics
environment; `manual_evidence_review` may use a spreadsheet or text editor.
Export every formula, command and version.

## Differential-expression comparison

Use `expression-study.tsv` and `expression-sample-groups.tsv`. Retrieve
GSE18781 through each workflow's normal GEO route. Run the same unadjusted
case-control contrast on GPL570 with the frozen 18 case and 25 control samples.
Report probe-level results with the workflow's standard moderated or classical
test and Benjamini-Hochberg adjustment. Batch-adjusted results are secondary and
must not replace the primary contrast. ExpressAnalyst replaces NetworkAnalyst
because the latter explicitly redirects transcriptomic tables there.

## Evidence-governance comparison

Use only `candidate-studies.tsv` and `cohort-evidence.tsv`. Compare AXIS with
a documented manual evidence review. Do not include GEO2R or ExpressAnalyst:
study eligibility, duplicate-participant detection and evidence-role separation
are outside this comparison's declared differential-expression scope.

## Required outputs

For every workflow and task, preserve a machine-readable result where the workflow
supports export, a plain-text methods record, and the corresponding row in
`result-template.tsv`. Task B must output one decision and rationale per study.
Task C must export probe identifier, effect or log fold-change, direction, raw
p-value and Benjamini-Hochberg adjusted p-value, plus the exact group assignment.
Task D must output one role per cohort, the unique primary-participant total,
excluded duplicates,
excluded incompatible evidence and one bounded conclusion.

## Task A

Start from a new local environment or private browser session. Follow official
installation/access instructions. For hosted workflows, installation is
`not_applicable` only because no local installation exists. Time Task C
separately; Task A access timing must not be presented as analysis speed.

## Rating

Apply `rating-rubric.tsv` literally to frozen evidence. `pass` requires the
stated evidence, and missing evidence is `fail`. `not_applicable` is restricted
to a criterion that is structurally irrelevant, never merely unsupported or
failed. Keep both initial assessments unchanged. Resolve disagreements later in
a separate consensus file with a rationale. Never calculate a weighted overall
score. The real-expression comparison is limited to one public contrast; the
synthetic governance comparison supports no biomedical claim.
