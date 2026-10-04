# Phase 3.7 implementation report

Baseline: origin/main `1b7f6df386f45f16eb95350af6d6780c8797e561`; branch
`phase37-retrospective-validation` (not based on `codex/phase2-transfer`; no lupus,
TRM17 or DDX24 material).

Added: `axis/domain/validation.py`, `axis/validation/{temporal,package,core,service}.py`,
`axis/storage/benchmarks.py`, migration 011, `axis/cli/benchmark.py`, API routes,
`axis/decision/evidence.py` (behaviour-preserving split of evidence assembly),
resources under `axis/resources/benchmarks/retrospective/`, builders
(`scripts/fetch_temporal_availability.py`, `build_retrospective_erap1.py`,
`build_synthetic_retrospective.py`), `scripts/verify_retrospective_wheel.py`,
`web/src/validation.ts`, tests (`tests/test_retrospective.py`, web unit + Playwright).

Validation: see final message for gate results. Pre-existing: 4 ruff UP038 findings on
main. Existing tests that hard-coded schema version 10 were updated to 11.

Not done: no independent (`validation`-kind) benchmark, no LLM baseline run, no
screenshot of the leakage-failure state (covered by node unit test and Python tests).
