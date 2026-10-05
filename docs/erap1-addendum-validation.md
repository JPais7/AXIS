# ERAP1 bounded addendum: validation and publication record

Assessment: 5 October 2026. Branch:
`codex/erap1-recent-evidence-addendum-2020-2026`.
Baseline: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
Scientific status: **pending independent review**, not expert acceptance.

## Local checks

| Check | Observed result |
|---|---|
| Addendum-specific tests | 24 passed |
| Full Python suite | 715 passed, 2 skipped, 227.96 seconds |
| Strict mypy | Success, 163 source files |
| Ruff: axis/tests and every new script/builder | All checks passed |
| Global Ruff vs baseline | 462 baseline / 462 current; identical diagnostic fingerprints, zero introduced/removed |
| Build | Wheel and sdist built successfully |
| Clean installed-wheel audit | PASS, isolated venv, wheel-only `--no-deps --no-index` installation |
| Offline replay | Network socket denied, isolated Python, non-repository cwd; exactly equals source audit |
| Resource checksums | 20 files checked, zero integrity errors |
| Historical refresh caches | Excluded from wheel |
| Original v1/canonical decision/learning resources | No diff from baseline |
| Commercial provenance | Eight CM statements link to impacts, assertions, experiment/context and locators; registry/baseline facts separate |
| PDF verification | Executive 3 pages, full 20 pages; all pages rendered/visually inspected, revised question header inspected again |
| Deterministic PDF rebuild | Same hashes before the intentional question-header revision |
| Frontend/TypeScript/ESLint | Not run: no frontend files touched |
| Whitespace / patch integrity | `git diff --check` passed |

The wheel check exercises the stdlib frozen-package audit, **not** the entire CLI
dependency installation. The complete source application's suite is separately
tested. Offline audit reproduces frozen classifications/impact references and
integrity, not wet-lab results, full literature screening, or canonical engine
reassessment. The two skipped tests are pre-existing optional reproducibility tests.

Global Ruff is not globally clean; inherited findings remain explicitly acknowledged.
Nothing was suppressed to hide new warnings. Current changes pass the CI-scoped
`ruff check axis tests` command.

Resource manifest SHA-256:
`d0006dd9836d84408c45fc8165efe8a6120ad1b167d771fb18ab892d96535235`.
PDF/traceability hashes are pinned in
`reports/commercial/erap1-axspa/v1.1/manifest.json`.

## Environment and reproducible commands

Local test environment: macOS 26.6.2 arm64, Python 3.12.13; pytest 9.1.1,
Ruff 0.16.10, mypy 2.4.0, build 1.6.1.
Separate PDF authoring environment: ReportLab 4.4.9, pypdf 6.10.0, Poppler rendering.
PDF tooling is not added to AXIS runtime dependencies.

```sh
python -m pytest tests/test_evidence_addendum.py -q
python -m pytest -q
python -m mypy axis
python -m ruff check axis tests
python scripts/verify_addendum_wheel.py
python -m axis.evidence_addendum
```

The retrieval scripts are bounded authoring helpers, not required for installed
offline replay. Original article XML is intentionally not distributed. Frozen
inputs and source locators permit review without treating live re-search as the
same historical retrieval. SHA-256 is integrity checking, not authenticity proof.

## Publication / CI

Publish only the named branch. No merge to main and no canonical DecisionState v2.
After publication, validate the exact pushed commit using the **AXIS checks**
workflow (Python 3.12, Ubuntu/Windows/macOS). The authoritative final SHA, run URL
and observed outcome are returned in the completion message; consult GitHub for
subsequent reruns rather than treating this pre-publication record as a CI result.

Historical terminal status is preserved:
`INSUFFICIENT REFRESH COMPLETENESS TO ASSESS`.
The bounded addendum verdict is `VALID_BOUNDED_PACKAGE_PENDING_REVIEW`.
These are different claims and must not be conflated.
