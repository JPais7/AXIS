# AXIS Phase 3.7 clean publication report

Date: 2026-10-04

Branch prepared: `phase37-retrospective-validation-clean`

Base: `origin/main` at `1b7f6df386f45f16eb95350af6d6780c8797e561`

Source branch inspected: `origin/phase37-retrospective-validation` at `9283f42e4d8a4de3fe1f5b4668892346fa8d1e02`

## Scope

This clean branch adds Phase 3.7 retrospective scientific validation and temporal
backtesting. It reconstructs the feature from the current `origin/main` rather
than merging the development branch.

Included:

- target-neutral retrospective validation domain, services and storage;
- additive schema migration `011_retrospective_validation.sql`;
- benchmark CLI subcommands for sealed cases, cutoff runs, leakage audits,
  reveal, baselines, blind review and reports;
- read-only API routes for benchmark inspection;
- retrospective validation workspace in the frontend;
- packaged ERAP1 development cases and synthetic-generic test cases;
- tests for temporal isolation, leakage prevention, negative/ambiguous evidence,
  baseline separation, blind review and UI honesty.

Excluded from this clean publication:

- DDX24 manuscripts, pilot documents, systematic-review scripts and Europe PMC
  screening scripts;
- unrelated single-cell, lupus, TRM17/TCR, biological-benchmark or paper-asset
  work;
- historical contaminated branches, including `phase37-retrospective-validation`
  and `codex/phase2-transfer`.

## Validation results

Passed:

- Phase 3.7 dedicated Python tests: `60 passed`;
- full Python suite: `552 passed, 2 skipped`;
- scoped Ruff on Phase 3.7-relevant Python files: passed;
- mypy on `axis`: passed for `144 source files`;
- frontend unit tests: `50 passed`;
- frontend ESLint: passed;
- frontend TypeScript typecheck: passed;
- frontend production build: passed;
- Playwright browser acceptance against a clean local server: `21 passed`;
- CLI/API smoke checks for benchmark listing, report and read-only API routes:
  passed;
- retrospective resource manifest checksum verification: passed;
- wheel build: `axis_bio-0.2.1.dev0-py3-none-any.whl`;
- installed-wheel structure verification: passed;
- installed-wheel retrospective offline replay: passed.

Known condition:

- repository-wide Ruff still reports pre-existing lint issues in legacy scripts
  outside Phase 3.7 scope, especially DDX24 and Europe PMC utilities. Scoped Ruff
  over the Phase 3.7 publication set passes.

## Publication verdict

PASS WITH CONDITIONS.

The Phase 3.7 feature is cleanly reconstructed on current `origin/main`, tested,
packaged and ready for review. The condition is that global legacy lint debt
remains outside the Phase 3.7 scope and should not be interpreted as a Phase 3.7
failure.
