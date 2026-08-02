# AXIS benchmarks

`PROTOCOL.md` freezes the intended comparison before results are collected.
The first local measurement is intentionally limited to the packaged synthetic
demo and cannot establish superiority over another tool.

Run ten repetitions from the repository root:

```shell
axis benchmark --repetitions 10 --warmups 1
```

The command writes an aggregate JSON report and a TSV file containing every
measured run. It reports environment, wall-clock time, Python allocation peak,
output size and check status. `tracemalloc` measures Python allocations rather
than total operating-system resident memory; the distinction is retained in
the outputs. `benchmark_demo.py` remains as a compatibility entry point and
uses the same implementation as the public command.

The first report produced by the public command is retained under
[`results/windows-v0.2.0-dev`](results/windows-v0.2.0-dev). It records ten
measured runs after one warmup on Windows; raw per-run timing values are kept
in TSV form alongside the aggregate JSON report.

The GitHub Actions matrix also runs the command on Ubuntu, Windows and macOS.
Successful workflow runs expose one 90-day artifact per operating system,
named `axis-benchmark-<os>-python-3.12`, containing only the aggregate report
and per-run TSV table.

## Guarded workflow comparison

Prepare identical synthetic tasks for AXIS, GEO2R, a manual statistical
workflow and NetworkAnalyst:

```shell
axis prepare-workflow-comparison
```

Give reviewers only `workflow-comparison/evaluator-package`. Keep
`coordinator-reference` hidden until two completed copies of
`assessment-template.tsv` have been frozen. Each reviewer must first follow
`STANDARD-OPERATING-PROCEDURE.md`, record the measured run in
`result-template.tsv`, and apply the criterion-specific rules in
`rating-rubric.tsv`. Unsupported or failed functionality is not labelled
`not_applicable`; that label is restricted to structurally irrelevant criteria.
Then combine the initial ratings:

```shell
axis summarize-workflow-comparison reviewer-a.tsv reviewer-b.tsv
```

The summary preserves both ratings, flags unresolved disagreements and writes
`consensus-template.tsv`. After resolving each disagreement against the frozen
reference and recording a rationale, run:

```shell
axis summarize-workflow-comparison reviewer-a.tsv reviewer-b.tsv \
  --consensus workflow-comparison-summary/consensus-template.tsv
```

The resulting article-ready count table deliberately does not calculate a weighted
overall score; speed cannot compensate for a failed scientific guardrail.
