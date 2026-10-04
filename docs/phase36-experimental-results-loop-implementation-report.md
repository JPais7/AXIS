# Phase 3.6 implementation report — experimental results loop

Design: [phase36-experimental-results-loop.md](phase36-experimental-results-loop.md) ·
rule audit: [phase36-result-rule-audit.md](phase36-result-rule-audit.md) and
[phase35-decision-rule-audit.md](phase35-decision-rule-audit.md).

## Release verdict

**PASS WITH CONDITIONS.** The loop is reproducible, review-aware and every decision
update is traceable to named results, review states and rules; production ERAP1 is
unchanged and no real result was invented. It is not a plain PASS because the loop
has only been exercised on **synthetic** data, the authored mappings and scenario
signatures it depends on are still unreviewed, and only engagement is
compound-scoped (see §33–35). It is not a FAIL: no result can change a decision
through a hidden or non-reproducible path (tested).

## 1–5. Baseline and commits

| Field | Value |
|---|---|
| `baseline_branch` | `codex/phase2-transfer` |
| `baseline_commit` | `ef0395157740c6404d0fdb11a586f5cf7c4ecdc2` (clean tree; 12 ahead of `main`, 0 behind, merge base `881b54c`; verified with the GitHub compare API) |
| `phase35_commit` | `5d91472` (engine), `fb821ee` (report) |
| `phase35a_commit` | `ef03951` (acceptance hardening, pushed) |
| `phase36_commit` / `final_head` | the commit that contains this file (read `git log -1`); its parent is `ef03951` |

Verified before starting: migration 009, `axis/decision/engine.py`, rule-set
fingerprinting, the frozen ERAP1 decision package, the Phase 3.5A acceptance tests
and report all exist. GitHub Actions on `ef03951`: Windows and macOS green; Ubuntu
448 passed and failed only the pre-existing Phase 3.3 `mypy` unused-ignore.

Hygiene: unrelated lupus/TRM17/DDX24/single-cell history and the untracked
`.DS_Store` / `docs/screenshots/phase2-hardening/` were not touched. A repository-wide
`ruff format` ran twice by mistake while working on this phase and reformatted
unrelated modules; both times it was reverted before any commit.

## 6. Migration

`010_experimental_results.sql`, additive (12 tables, no DROP/ALTER/DELETE/CASCADE);
001–009 are byte-identical to `ef03951` (tested). Tables: `experiment_artifacts`,
`performed_experiments`, `experiment_design_deviations`,
`experimental_quality_assessments`, `experimental_results`, `result_artifacts`,
`result_events`, `result_interpretations`, `scenario_signatures`,
`scenario_match_assessments`, `scientific_reviews`, `decision_result_links`.
Tested clean and 9 → 10, including read-only reopen.

## 7–8. Reused and new objects

Reused: `ProposedExperiment`, `OutcomeScenario`, `outcome_interpretations`,
`Provenance`, `KnowledgeKind.EXPERIMENTAL_RESULT`, `DecisionState` and its tables,
`Claim` (legacy completion path), the pharmacology compound registry (identity gate).
New (`axis/domain/results.py`, target-neutral): `ExperimentalArtifact`,
`PerformedExperiment`, `DesignDeviation`, `QualityAssessment`, `ExperimentalResult`,
`ResultInterpretation`, `ScenarioMatch`, `ScientificReview`. New modules:
`axis/experiments/{policy,results}.py`, `axis/storage/results.py`,
`axis/cli/experiment.py`, `web/src/results.ts`. `ExperimentalSample` was not needed
and was not built.

## 9–11. Import, provenance, artifact integrity

JSON-manifest packages with referenced artifacts; transactional, idempotent,
fail-loud validation (10 rejection cases parametrized in tests). Provenance kept:
experiment, scope, context, assay, controls, endpoint, artifacts with sha256, size,
media type, transformations (input→output, method, version), analysis method/version,
observer/recorder, timestamps. Corrupting an artifact is detected at validation and by
`verify-artifacts`; the same logical result with changed content is an integrity
conflict; a correction is a new superseding version (version gaps rejected);
withdrawal is an append-only event.

## 12. QC model

Categorical: control status, technical validity, replicate quality, assessment
(`interpretable` / `interpretable_with_caveat` / `non_interpretable`); no composite
score. Failed controls or an invalid assay cannot be marked interpretable.
Completed ≠ interpretable (lifecycle states, tested).

## 13. Review workflow

Five reviewable object types, append-only history, derived state with explicit
conflict, `accepted_with_caveat` requires a caveat, AI-identifying reviewers rejected.
Review policy `decision-review-policy-v1` with `exploratory` / `reviewed` modes,
recorded in each state and in the methodology fingerprint.

## 14. Scenario matching

Frozen signatures for all 21 anticipated scenarios (AI-suggested, review pending) and
a pure matcher (`axis-scenario-match-1`): matches / partially matches / contradicts /
ambiguous / outside predefined scenarios / non-interpretable. An unexpected result is
stored, creates an uncertainty and is never force-fitted.

## 15. Evidence-edge update

`DECISION-RESULT-001`: eligible contributions update their own edge and scope only.
Tested: no cascade to functional/HLA/immune/disease edges; an edge the experiment does
not declare is ineligible; contradictory results for one scope become `mixed`
(reproducibility uncertainty) and both are kept.

## 16. Compound scope

Engagement is rolled up over the phenotype-producing scopes (compounds 2 and 3,
perturbagen DG013A; compound 1 has no phenotype and is not required).
`DECISION-RESULT-002`: open → partial → complete; a compound-3 result leaves compound
2 and DG013A `not_assessed` and the uncertainty `partially_resolved`; project state
`incomplete`. A source-reported perturbagen never receives an invented chemical
identity (compound table count unchanged). **Only engagement is scoped**; dependency,
selectivity, context and reproducibility are still target-level.

## 17. DecisionState v1

Production ERAP1 rebuilt before any synthetic work: critical uncertainty
`target_engagement`, recommendation `decision:exp:chemical-genetic-engagement`,
explanation statuses (on-target partially supported; off-target, indirect, context
viable), engagement `not_assessed`, no result informing it, `synthetic: false` —
identical to Phase 3.5A (tested). The rule-set version moved to `axis-decision-3`, so
the methodology digest differs; evidence and conclusions do not.

## 18–19. Synthetic experiment and result

`axis/resources/experimental-results/synthetic/erap1-decision-loop/v1`: one performed
experiment implementing `decision:exp:engagement-assay` for compound 3, QC passed, one
result (signal 0.58 of vehicle in wild-type cells, none in target-depleted cells; raw
and processed TSV artifacts with checksums; vehicle-normalization transformation), one
interpretation. Every file and the manifest say `SYNTHETIC / TEST-ONLY`
(`scientific_status: synthetic_test_fixture`, `not_real_experimental_evidence: true`);
import requires `--allow-synthetic`. Variants (negative, technical failure,
unexpected, partial, deviation, conflict, correction, withdrawal) are generated inside
the tests.

## 20. Review decision

Test reviewer "Dr Example": result accepted; interpretation *accepted with caveat*
("synthetic system only") — a free-text name, not a real reviewer. Nothing is
accepted by default; none of the 84 mappings or 37 cellular assessments was reviewed.

## 21–22. DecisionState v2 and causal diff

Synthetic compound-3 result, exploratory, pending → v2: engagement `not_assessed →
incomplete`; engagement / compound 3 `not_assessed → supported`; rollup `open →
partial` (`DECISION-RESULT-001/002`); engagement uncertainty `open/decision_blocking
→ partially_resolved/decision_material`; critical uncertainty and recommendation
unchanged; answer *pending review*. After review: cause `review_status_change` (not new
evidence). Remaining scopes resolved by synthetic results for compound 2 and DG013A →
v4: rollup `complete`, engagement `supported`,
critical uncertainty `target_engagement → target_dependency` by `DECISION-DEP-001`
with triggering results named; the recommendation did not change (the same
chemical-genetic experiment is also considered for dependency); answer *yes*.
Evidence, review, investigator-input and methodology causes are separate (tested,
including a rule-version change with unchanged evidence).

## 23. Sensitivity

Each state lists decision-sensitive evidence by category, now including each result
and "results pending review". In v4 removing any of the three engagement results
reverts the critical uncertainty; in v2/v3 no single result changes it (engagement is
only partially resolved) — reported as non-decisive, not exaggerated. Withdrawal
returns v3 to the v1 scientific state while keeping v2 (tested).

## 24. Production ERAP1 regression

Tested above (§17) and in the browser: the production Decision page shows no
synthetic banner, "no performed experiment has been imported into it" and the pending
review banner; the Results page says no performed experiment or result exists.

## 25–27. API, CLI, UI

API (read-only, no mutation, bounded): `performed-experiments[/id]`, `results[/id]`,
`results/{id}/review`, `results/{id}/decision-impact`, `review-queue`,
`scenario-mappings`, `decision/diff`, `decision/timeline`. (The existing `experiments`
route is the Phase 2 proposal list, so the new one is `performed-experiments`.) CLI as
in the design document; no command hides a state change (`import` says
`decision_state_changed: false`). UI: Experiments / Results, Review, result drawer
(OBSERVED, INTERPRETATION, reviews, scenario match, QC, deviations, artifacts, impact
preview), decision timeline, engagement-by-scope, causal diff, persistent synthetic
banner. **Reviews are recorded through the CLI/service only; the UI shows them but does
not write them.**

## 28. Tests

`tests/test_results_loop.py` — 49 tests: baseline regression, happy/partial/complete
loops, negative engagement, technical failure, unexpected and partial matches,
deviations, edge and context isolation, compound isolation and unresolved identity,
pending/accepted/rejected/caveat/conflict reviews, AI-reviewer guard, mapping review,
rejected assessments, correction, withdrawal, duplicate/conflicting import, artifact
corruption, 10 validation failures, domain validation, synthetic gate, immutability,
evidence-vs-rule causality, import-order independence, two-store replay, answers, API,
CLI, generic-target ledger, migration 9→10, lifecycle. Existing suites updated only for
the schema version (9 → 10), the rule-set version, and the `evidence` stub signature.
Frontend contract tests: 45 (11 new). Full Python suite: **497 passed, 2 skipped**.

## 29. Offline, LLM-off replay

Two clean stores import the frozen packages and the synthetic result, review, rebuild
and produce byte-identical v2 with sockets and `httpx` disabled and `anthropic` /
`openai` blocked. No module in `axis/experiments` imports a network or model library
(static test).

## 30. Installed-wheel replay

`scripts/verify_results_wheel.py` from an installed wheel: frozen resources and
migration 010 present and checksum-verified, import, review, explicit rebuild, v2,
causal diff, API routes, two-store equality, network and LLM off. The Phase 3.2–3.5
wheel verifiers also pass.

## 31. Browser validation

Playwright, Chrome for Testing 147 through `AXIS_BROWSER_EXECUTABLE`: **19 passed**
(15 earlier + 4). The loop spec runs against a *separate* synthetic database/server and
the production spec against the production database: 1440 and 1024 px traversals with
16 screenshots each (experiments overview, ledger, timeline, performed-experiment
detail, observed-vs-interpreted, scenario match, QC, non-interpretable result,
unexpected result with impact preview, review queue with conflict, mapping review,
decision v4 scope table, results informing the decision, three causal diffs), DOM
semantics (no heading skips, every control named, captions, no overflow), no remote
requests, no page errors, keyboard open/Escape/focus-return. Screenshots:
`docs/screenshots/phase36/`. Manually inspected: result drawer, decision scope table
and causal diff, review queue.

## 32. Checks not executed

GitHub Actions on the new commit; Python 3.12 locally (runs used 3.14.6); Edge; an
axe-core audit and contrast measurement; a screenshot of the `reviewed`-mode empty
decision (covered by tests); anything involving a real laboratory result or a real
reviewer. Global Ruff: 285 findings, identical to the pre-phase count (measured on a
clean worktree of `ef03951`); scoped files clean except one pre-existing `UP038` in
`axis/api/server.py`; four files carry a scoped `E501` ignore for long prose strings.
mypy: no issues, 138 files. TypeScript and ESLint: clean.

## 33. Scientific limitations

The loop is demonstrated only on synthetic data. Scenario signatures, scenario→
explanation mappings and the candidate designs are AI-authored; until a researcher
reviews them, `reviewed` mode yields no recommendation and `exploratory` mode says it
depends on pending review. Eligibility policy v1 is deliberately simple (no weighting
of reviewer expertise, no replicate-aware statistics). Statistics and uncertainty are
preserved, not interpreted; a p-value never sets an evidence state. Nothing here says
ERAP1 modulation is therapeutic or that any compound engages ERAP1.

## 34. Product limitations

Import is JSON-manifest only (no result-table importer, no connectors); reviewer
identity is unauthenticated free text; the UI does not write reviews; only engagement
is compound-scoped; the decision integration still assumes the Phase 3.4 cellular
schema and ERAP1 importer guard; evidence windows are bounded to 100 records (the
engine refuses larger sets rather than paginating); there is no Ask AXIS interface
(`axis decision explain` answers from stored records).

## 35. Phase 3.5A conditions

| Condition | Status |
|---|---|
| 1 authored mappings need review | Infrastructure delivered (mapping/design/assessment review, modes, dependency counts); **0 of 84 mappings reviewed** — open |
| 2 genericity beyond ERAP1 | Result model, policy and ledger demonstrated generically; decision integration and importer remain ERAP1/HLA-bound — **open** |
| 3 project-level uncertainties | Engagement now scoped and rolled up; the rest remain target-level — **partly addressed** |
| 4 recommendation depends on pending evidence | Now explicit: mode, counts, banners, `reviewed` mode, per-result and pending-review sensitivity — **addressed as visibility, not as resolution** |
| 5 falsification inert in production | Unchanged — open |
| 6 bounded windows | Unchanged (explicit refusal) — open |
| 7 CI / repository debt | Unchanged (Ubuntu mypy, global Ruff, branch contamination) — open |

## 36. Recommended Phase 3.7

**A — Multi-target generalization.** The loop works, but every layer above the result
model is still tied to one target's evidence schema, and condition 2 has now blocked
two phases. A second real target through evidence → decision → results will show
whether the architecture generalizes and will force the decision engine to consume a
declared evidence schema instead of the Phase 3.4 cellular tables. Experimental-data
connectors (B) are premature while no real result exists; the review of the existing
evidence and mappings is a human task that no software phase can substitute. Phase
3.7 has **not** been started.
