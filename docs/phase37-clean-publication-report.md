# AXIS Phase 3.7 final pre-merge audit report

Date: 2026-10-04

Branch audited: `phase37-retrospective-validation-clean`

Publication SHA audited: `b15b2064530277bc8084a6d91e7596fd50d63caa`

Base at audit start: `origin/main` =
`1b7f6df386f45f16eb95350af6d6780c8797e561`

Merge base at audit start:
`1b7f6df386f45f16eb95350af6d6780c8797e561`

Topology at audit start: `origin/main...phase37-retrospective-validation-clean`
= `0 1`.

## Scope and hygiene

Included:

- target-neutral retrospective validation domain, temporal snapshots and deterministic assessment logic;
- additive migration `011_retrospective_validation.sql`;
- CLI workflow for sealed cases, snapshots, cutoff decisions, leakage audit, reveal, baseline import, blind packets, review and reports;
- read-only benchmark API;
- frontend retrospective validation workspace and tests;
- ERAP1 development benchmarks and synthetic-generic stress fixtures.

Excluded from this clean publication:

- unrelated DDX24 scripts, manuscripts and pilot documents;
- Europe PMC screening scripts and preprint/manuscript preparation work;
- lupus, TRM17/TCR, unrelated single-cell research, unrelated biological benchmarks and paper assets.

The only contamination-pattern hits in the Phase 3.7 diff were guardrail/report text or pre-existing lines in `axis/cli/main.py`; no unrelated research scripts or manuscript artifacts were added.

## Gate results

| Gate | Result | Command / evidence |
|---|---:|---|
| Branch topology | PASS | `git rev-list --left-right --count origin/main...HEAD` → `0 1`; merge-base `1b7f6df386f45f16eb95350af6d6780c8797e561` |
| Contamination path audit | PASS | `git diff --name-status origin/main...HEAD`; no unrelated DDX24/lupus/TRM17/TCR/preprint work in added paths |
| Empty frontend test-file audit | PASS | `web/tests/validation.spec.mjs` = 1889 bytes; `web/tests/validation.test.mjs` = 3898 bytes; both meaningful tests |
| `verify_structure_wheel.py` audit | PASS | Kept because schema 011 raises installed-wheel schema expectation from 10 to 11 |
| Schema-version audit | PASS | Phase 3.7-related assertions expect schema 11; legacy wheel verifiers still expecting 10 are pre-existing outside this publication |
| Phase 3.7 Python tests | PASS | Python 3.12.13; `PYTHONPATH=. /Users/joaopais7/axis-validation/bin/python -m pytest tests/test_retrospective.py` → `60 passed in 12.68s` |
| Full Python suite | PASS | `PYTHONPATH=. /Users/joaopais7/axis-validation/bin/python -m pytest` → `552 passed, 2 skipped in 131.36s` |
| Ruff scoped | PASS | `ruff check axis tests scripts/build_retrospective_erap1.py scripts/build_synthetic_retrospective.py scripts/fetch_temporal_availability.py scripts/verify_retrospective_wheel.py scripts/verify_structure_wheel.py` |
| Ruff global | PRE-EXISTING FAILURE | `ruff check .` still reports 285 legacy issues, beginning in `scripts/analyze_gse163314_ddx24.py`; outside Phase 3.7 scope |
| mypy | PASS | `mypy axis` → `Success: no issues found in 144 source files` |
| Migration audit | PASS | `011_retrospective_validation.sql` is additive; tests cover fresh DB, migrated schema 11 and read-only reopen |
| Temporal-isolation architecture | PASS | `load_records()` reads bounded records; benchmark service snapshots eligible records at T; `assemble_evidence()` is pure and receives only the snapshot records |
| Temporal-leakage behavior | PASS | Unit tests and CLI replay confirm leakage-invalid cases use `INVALID — TEMPORAL LEAKAGE` semantics |
| CLI smoke | PASS | Fresh DB executed `benchmark list/show/snapshot/run/leakage-audit/reveal/compare/blind-packet/report`; invalid reveal ordering failed safely; legacy no-subcommand `axis benchmark` ran |
| API smoke | PASS | Read-only routes for list, case, snapshot, run, audit, reveal, assessment, reviews and report returned; unknown case failed safely |
| Frontend install | PASS | Node `v26.9.0`, npm `11.19.1`; `npm ci` found 0 vulnerabilities |
| TypeScript | PASS | `npm run typecheck` |
| ESLint | PASS | `npm run lint` |
| Frontend unit tests | PASS | `npm test -- --run` → `50 passed` |
| Frontend build | PASS | `npm run build`; emitted tracked workspace assets from clean source |
| Playwright | PASS | Clean local server; `npx playwright test` with local Chromium executable → `21 passed (42.1s)` after initial environmental connection-refused retry |
| Manifest/checksum verification | PASS | ERAP1 manifest SHA `0fb3c3dedd1c507a820f45bafe95ae32753674323963745ff616819d1180291a`; synthetic manifest SHA `91b21ee28c454435085344036dc022f2d485ff8f3bdfbac16ad31d4bcdadb281` |
| Deterministic replay | PASS | Fresh-store replay of official ERAP1 and synthetic cases preserved stable semantic conclusions |
| ERAP1 benchmark replay | PASS | `erap1-axspa-t2011`, `t2014`, `t2016` replayed and revealed; all concluded future evidence did not test the decision, without therapeutic-overclaim |
| Generic synthetic benchmark | PASS | Official synthetic cases replayed: positive, negative, ambiguous, irrelevant and undated |
| Packaged multi-window files | PASS WITH CONDITIONS | `syn-generic-window-1/2/3` files are packaged but not registered in the manifest, so they are fixture resources, not CLI-published cases |
| Wheel build | PASS | `python -m build --wheel` built `axis_bio-0.2.1.dev0-py3-none-any.whl` |
| Installed-wheel retrospective replay | PASS | `scripts/verify_retrospective_wheel.py dist/axis_bio-0.2.1.dev0-py3-none-any.whl` → `installed wheel replays retrospective cases offline: OK` |
| Installed-wheel structure verification | PASS | `scripts/verify_structure_wheel.py` in fresh venv reported schema 11 and disabled network entry point |
| Offline replay | PASS | Wheel replay used frozen package resources and did not require OpenAI, Anthropic, Europe PMC, UniProt, PDB, ChEMBL or web requests |
| Scientific-claim wording | PASS | `docs/phase37*` avoids prospective, clinical or generalized drug-discovery claims |

## Scientific replay summary

- ERAP1 T2011: revealed; conclusion `future_evidence_did_not_test_the_decision`. AXIS did not infer treatment efficacy from structure-only evidence.
- ERAP1 T2014: revealed; conclusion `future_evidence_did_not_test_the_decision`. Later evidence did not resolve the decision question as framed.
- ERAP1 T2016: revealed; conclusion `future_evidence_did_not_test_the_decision`. Chemical/biochemical evidence was not treated as clinical efficacy or disease modification.
- Synthetic positive: `supported_by_future_evidence`.
- Synthetic negative: `weakened_by_future_evidence`.
- Synthetic ambiguous: `ambiguous`.
- Synthetic irrelevant: `future_evidence_did_not_test_the_decision`.
- Synthetic undated: `future_evidence_did_not_test_the_decision`, with undated evidence excluded.

## Independent review and baselines

Independent scientific review remains pending. The blind-review machinery is implemented and tested, but AXIS does not accept its own scientific performance.

No external literature-aware baseline was executed for release readiness. The baseline system preserves frozen baseline artifacts and distinguishes deterministic AXIS outputs from stochastic baselines.

## Pre-merge verdict

PASS WITH CONDITIONS.

Release blockers were not found: no temporal leakage into DecisionState(T), no repository contamination in the publication delta, no migration corruption, no checksum corruption, no Phase 3.7 regression, no package failure and no broken deterministic replay.

Conditions are scientific limitations rather than software blockers:

- retrospective validation only;
- small real benchmark set;
- ERAP1 cases are development benchmarks, not independent validation;
- no prospective experimental validation;
- no clinical validation;
- no general drug-discovery performance claim;
- independent expert scientific review pending.
