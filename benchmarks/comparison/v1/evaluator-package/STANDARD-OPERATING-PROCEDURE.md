# Standard operating procedure

## Roles and blinding

Each reviewer operates every workflow independently. Reviewers must not consult
each other or the `coordinator-reference` directory before both initial result
and assessment files are frozen. Use coded reviewer identifiers. Record all
deviations; do not repair an output after seeing a reference answer.

## Common environment and timing

Use the same computer and normal network connection for all workflows. Record OS,
hardware, workflow version or web access date, browser where relevant, and every
manual decision. One untimed familiarisation attempt per workflow is permitted.
For each measured task, start timing immediately before the first workflow action
after opening the required input and stop when all required exports are saved.
Include uploads and downloads; exclude the familiarisation attempt. Record failed
attempts. Measure output size as the sum of exported result files. Record peak
memory with the same OS tool where possible; if a hosted service prevents this,
record `measurement_unavailable_hosted_service` and the method attempted.

## Allowed operations

Use only the named workflow, its official documentation and the supplied files.
Do not use another workflow to repair, transform or transcribe results. The
`manual_statistics` condition may use a spreadsheet or one general-purpose
statistics environment, but every formula or command and software version must be
exported. Web workflows may be used only if their normal upload interface accepts
the supplied synthetic data. Record rejection of an input as a failed attempt.

## Required outputs

For every workflow and task, preserve a machine-readable result where the workflow
supports export, a plain-text methods record, and the corresponding row in
`result-template.tsv`. Task B must output one decision and rationale per study.
Task C must output gene, case mean, control mean, case-minus-control effect,
direction, raw p-value and Benjamini-Hochberg adjusted p-value. Use a two-sided
Welch t-test and define positive effects as higher in cases. Task D must output one
role per cohort, the unique primary-participant total, excluded duplicates,
excluded incompatible evidence and one bounded conclusion.

## Task A

Start from a new local environment or a private browser session. Follow only the
official installation/access instructions. Run the supplied AXIS synthetic demo
for AXIS; for hosted workflows, confirm access and record installation as
`not_applicable` only because no installation exists. Do not transfer AXIS demo
performance to another workflow.

## Rating

Apply `rating-rubric.tsv` literally to frozen evidence. `pass` requires the
stated evidence, and missing evidence is `fail`. `not_applicable` is restricted
to a criterion that is structurally irrelevant, never merely unsupported or
failed. Keep both initial assessments unchanged. Resolve disagreements later in
a separate consensus file with a rationale. Never calculate a weighted overall
score. These synthetic results evaluate workflow behaviour, not biomedical truth.
