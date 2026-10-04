# Phase 3.5 implementation report — experimental decision engine

Companion to [the design document](phase3-experimental-decision-engine.md).

> Updated by Phase 3.5A: rule counts (20 → 23), rule-set version (`axis-decision-1` →
> `axis-decision-2`), the `weakened` status definition and test totals changed during
> the acceptance audit. See [the acceptance report](phase35-scientific-decision-acceptance-report.md).

## 1–5. Baseline and commits

| Field | Value |
| --- | --- |
| `baseline_branch` | `codex/phase2-transfer` (verified: 9 commits ahead of `main`, 0 behind, merge base `881b54c696d8313344856e87f35b62b9ec4349d8`) |
| `baseline_commit` | `11458e28acd515320986f0f7662fc1f961ac4b4b` |
| `phase34_commit` | `11458e2` — "feat: add Phase 3.4 cellular pharmacology layer" |
| `implementation_commit` | `5d91472` — "feat: add Phase 3.5 experimental decision engine" |
| `final_head` | the commit containing this report (a report cannot cite its own hash; read `git log -1`). It is a docs-only commit on top of `5d91472`. |

Baseline checks before changing code: migrations 001–008 present and untouched;
Phase 3.4 domain, service, rules, storage, frozen package, report and review
packet inspected; the Evidence Store held **no** `Hypothesis` rows, four
intervention strategies, five open questions, five proposed experiments and
fourteen outcome scenarios. The Phase 3.4 suite was not run separately before changes; it was run in full
afterwards (below), and CI on `11458e2` showed macOS and Windows green.

Repository hygiene: unrelated analysis/benchmark/preprint material on the branch
was not touched. A stray `ruff format axis` reformatted unrelated modules once; it
was reverted before commit (`git diff --stat` shows only the Phase 3.5 files below
plus the schema-version assertions). Untracked `.DS_Store` files and
`docs/screenshots/phase2-hardening/` were preserved and are not part of this work.

### Phase 3.5 files

New: `axis/storage/migrations/009_experimental_decision.sql`,
`axis/domain/decision.py`, `axis/decision/{__init__,rules,service}.py`,
`axis/storage/decision.py`, `axis/cli/decision.py`,
`axis/resources/decision/erap1-axspa/v1/{manifest.json,manifest.sha256,README.md}`,
`web/src/decision.ts`, `web/tests/decision.{test,spec}.mjs`,
`tests/test_decision.py`, `scripts/verify_decision_wheel.py`,
`docs/phase3-experimental-decision-engine*.md`, `docs/screenshots/phase35/`.
Edited: `axis/api/server.py` (decision routes), `axis/cli/main.py`,
`axis/storage/store.py` (repository wiring), `web/src/main.ts`, `web/src/cellular.ts`,
`web/src/hardening.css`, `web/playwright.config.mjs`, rebuilt
`axis/resources/workspace/assets/*`. Mechanical: expected `schema_version` 8 → 9 in
existing tests and wheel scripts; `web/tests/cellular.spec.mjs` (route/heading
renamed) and `web/tests/workspace.spec.mjs` (outcome count 14 → 35, following the
Phase 3.4 precedent of adapting counts to additional imports).

## 6. Migration

`009_experimental_decision.sql`, additive; 001–008 unchanged. Tables:
`decision_explanations`, `decision_states`, `decision_uncertainties`,
`decision_uncertainty_gaps`, `decision_explanation_states`,
`decision_explanation_links`, `critical_uncertainty_assessments`,
`candidate_experiment_profiles`, `decision_experiment_gaps`,
`decision_experiment_discriminates`, `outcome_interpretations`,
`decision_consequences`, `decision_constraints`, `decision_events`. Foreign keys
reach `hypotheses`, `proposed_experiments`, `outcome_scenarios`, `open_questions`,
`claims` and the project/protein tables. Tested on a clean store and on a store
migrated 8 → 9, including read-only reopen.

## 7–8. Domain objects

New (`axis/domain/decision.py`): `CompetingExplanation`,
`ExplanationEvidenceLink`, `ScientificUncertainty`, `OutcomeInterpretation`,
`DecisionConsequence`, `CandidateExperimentProfile`, `DecisionConstraints`
(plus an investigator-declared `excluded_experiment_ids`), `DecisionState`.
Reused unchanged: `Hypothesis`/`HypothesisRevision`, `ProposedExperiment`,
`OutcomeScenario`, `OpenQuestion` (the Phase 3.4 evidence gaps),
`KnowledgeKind`. `CriticalUncertaintyAssessment` is stored in
`critical_uncertainty_assessments`; `DecisionTrace` is a read projection.

## 9. Decision rules

Twenty rules, version `axis-decision-1`, listed with inputs, outputs and
rationale in `axis/decision/rules.py` and fired-per-state in the trace. The
reference state fires all twenty.

## 10. Evidence inputs

Assembled read-only by `DecisionService.evidence` from the Evidence Store:
cellular evidence chain (eight edges), cellular assessments and readouts,
chemical–genetic comparisons, 18 selectivity assessments, evidence gaps, project
structures, intervention strategies. Digest of the canonical form identifies the
state. Reference values: biochemical, exposure, HLA and immune edges
*supported*; functional *insufficient*; engagement, disease, clinical *not
assessed*; 0 of 18 selectivity comparisons comparable; 6 of 6 chemical–genetic
comparisons not comparable; one source disagreement (surface free heavy chain:
decrease in Chen vs increase in Tran after ERAP1 knockdown).

## 11. Competing explanations (reference state)

| Explanation | Status | Links |
| --- | --- | --- |
| On-target ERAP1 modulation | partially supported | 19 supports, 26 unresolved |
| Off-target activity | viable | 22 unresolved |
| Indirect pathway | viable | 11 unresolved |
| Context-dependent effect | viable | 1 unresolved, 4 context limits |

No explanation is contradicted; none was ungrounded in this state.

## 12. Uncertainties (reference state)

Nine: target engagement (open, **decision-blocking**, rules GAP-001/002), target
dependency, selectivity, genetic context, reproducibility, mechanistic bridge
(open, decision-material), disease relevance (open, informative), clinical
translation and structural mechanism (not actionable, peripheral).

## 13. Critical uncertainty

`uncertainty:target_engagement` — "Do the phenotype-producing compounds directly
engage ERAP1 in cells at those exposures?" Derived, not hard-coded: biochemical
activity and a compound phenotype are supported, engagement is not assessed, and
selectivity is unresolved so an off-target explanation remains viable (GAP-002
raises it to blocking). Every other uncertainty is listed with the criterion on
which it lost; the rules are tested to select a different uncertainty once
engagement is supplied as supported.

## 14–17. Candidate experiments

Six AI-suggested candidates (frozen package):

| Experiment | Considered for | Pairs separated | Interpretability | Outcome in reference state |
| --- | --- | --- | --- | --- |
| Matched-genotype chemical–genetic experiment with engagement readout | engagement, dependency | 3 | high | **rank 1 — recommended** (5 distinct next actions) |
| Cellular engagement measurement | engagement | 2 | high | rank 2, 4 distinct next actions |
| Engagement/phenotype concentration alignment | engagement | 1 | moderate | rank 3 (characterization) |
| Repeat the reported phenotype with more replicates | engagement, reproducibility | **0** | low | rank 4, **low discrimination**, role replication |
| Matched allotype × HLA-B27 panel | genetic context, reproducibility | 1 | moderate | not compared for this uncertainty |
| Chemically distinct ERAP1 probe | selectivity, dependency | 1 | moderate | not compared; probe not established |

The recommendation is a *framing* for researcher review, with its prerequisites
exposed (validated compound identity, an engagement readout and an ERAP1-null
and rescue model are all `not_established` in the corpus).

## 18–19. Outcome scenarios and consequences

Each candidate has supportive, negative, alternative (where appropriate) and
non-interpretable scenarios — 21 in total — with per-explanation effects and a
conditional consequence (`If …`). Negative results are informative; technical
failure is a separate, non-discriminating scenario that opens a new uncertainty.
All are labelled prospective. For the recommended experiment: engagement plus
dependence → strengthen the strategy for the tested context; persistent phenotype
in ERAP1-null cells → weaken it; dependence without engagement → change the
mechanistic model; background-dependent behaviour → investigate context; invalid
model → require replication.

## 20–21. Trace, history and diff

The state stores the trace (20 rules, candidate reasons, critical-selection
reasons and 33-node, 57-edge graph in which every edge states its basis) and a
diff against the previous state. Tests create v1, then change constraints, status
events, promotions and the evidence itself, and verify v1 is untouched, v2
supersedes it, and the diff names the changed edge, uncertainty, critical
uncertainty and recommendation.

## 22. Frozen fixture

`axis/resources/decision/erap1-axspa/v1`, sha256
`7704249a99c0b449f721a67b0647f2448a0aed76a225ef320fb61fded5057618`. It holds
wording and mappings only; evidence IDs are references into the existing stores.

## 23–25. Interfaces

* API: seven read routes (see the design document); GET never builds, never
  calls a model and never uses the network (tested with sockets and `httpx`
  disabled). No mutation route exists.
* CLI: nine `axis decision` subcommands; investigator actions are CLI/service
  only.
* UX: Decision workspace with all twelve requested views, keyboard-operable
  section links, drawers for explanation evidence and candidate experiments,
  text-equivalent outcome tree and graph.

## 26–27. Tests and offline replay

`tests/test_decision.py`: 47 tests covering uncertainty (missing engagement,
conflicting evidence, unresolved selectivity, genetic and disease context,
resolved gap, non-actionable), explanation statuses and grounding, critical
selection (A blocks and is testable → selected; resolve A → another selected),
discrimination, outcome tree kinds, versioning and immutability, epistemic
boundaries and explicit promotion, constraints and feasibility, migration and
integrity, project isolation, API and CLI. **Two clean stores** import all frozen
resources, build independently with network access disabled and produce
byte-identical states; the same replay passes from an installed wheel
(`scripts/verify_decision_wheel.py`). No LLM or network dependency exists.

## 28. Browser validation

Playwright (existing strategy: `AXIS_BROWSER_EXECUTABLE` pointing at an
already-installed Chrome for Testing 147): **15 passed** — three new decision
tests (1440 and 1024 px full traversal with 12 screenshots each, plus keyboard
section navigation) and the 12 prior tests. No page errors, no remote requests,
no horizontal overflow. Screenshots: `docs/screenshots/phase35/` (overview,
critical uncertainty, competing explanations, explanation evidence drill-down,
comparison, recommended experiment, why-this-experiment, outcome tree, trace,
history/diff, non-discriminating experiment, unknown constraints). Manual visual
review covered critical uncertainty, comparison matrix, why-this-experiment,
outcome tree, evidence drill-down, constraints and the non-discriminating
experiment; three defects found that way (raw explanation ids in the critical-
reasons list, a `.;` join in the consequence summary, and a mismatched
consequence field in the candidate drawer) were fixed and re-verified.

## Validation gates

| Gate | Result |
| --- | --- |
| Full Python suite | **403 passed, 2 skipped** |
| Decision tests | 47 passed |
| Phase 3.3 / 3.4 regression (pharmacology, cellular) | passed (inside full suite) |
| Ruff, Phase 3.5 files | clean (`check` and `format --check`) |
| Ruff, whole repository | **285 pre-existing errors, unchanged by this work** (measured with Phase 3.5 stashed) |
| mypy (strict config) | no issues, 131 source files |
| TypeScript typecheck / ESLint | clean |
| Frontend contract tests | 30 passed (7 new) |
| Production build | built (existing >500 kB NGL chunk warning) |
| Wheel build and installed-wheel verification | passed, including resources and migration 009 |
| Migration 8 → 9, legacy and clean | passed |
| Two-store offline replay | passed (repository and installed wheel) |
| API and CLI smoke | passed |
| Playwright | 15 passed |
| `git diff --check` | clean |

## 29. Checks not executed

* GitHub Actions on the new commit (push not performed; the local tree has not
  been exercised on Windows/macOS/Ubuntu runners). The Phase 3.4 Ubuntu `mypy`
  failure (`type: ignore` in `axis/pharmacology/chemistry.py`) is pre-existing
  and was not addressed.
* Local runs used Python 3.14.6 and Node 26.9, not the project's declared Python
  3.12; the installed-wheel check ran in a Python 3.14 virtual environment.
* `npm ci` was not re-run (existing `node_modules` used).
* No Microsoft Edge run; Chrome for Testing was used.
* No expert scientific review of the explanations, candidate experiments,
  controls or outcome mappings.

## 30. Scientific limitations

The evidence base is six selected publications curated by AI-assisted
extraction, pending expert review. "Viable" and "partially supported" are
categorical readings of links, not credences. The outcome-to-effect mappings and
the choice of candidate designs encode domain judgement that is suggested, not
validated. The Chen/Tran direction disagreement is surfaced but not resolved. The
DG013A label is not resolved to a single substance, which limits any engagement
experiment. Structure is deliberately treated as unable to settle engagement.

## 31. Product limitations

Feasibility, cost and time are unknown until an investigator supplies
constraints; matching of requirements to resources is exact-string. Mutations are
CLI-only. There is no separate Ask AXIS interface in the repository; grounded
answers are available through `axis decision explain`. The graph is a list, not a
drawn diagram. Strategy comparison (catalytic vs allosteric vs allotype-specific)
was not implemented because the evidence does not support ranking.

## 32. Recommended next phase

**A — Experimental results loop**, then possibly **E — evidence acquisition**.
Phase 3.5 shows that the next scientific gain is not another layer of curated
inference: the decision turns on one unmeasured link (engagement) and on a
genuine source disagreement. The most valuable next capability is to import real
laboratory results as `experimental_result` claims, link them to a candidate
experiment's scenarios, and produce `DecisionState v2` with a diff — closing the
loop the architecture now prepares. Multi-target comparison (B), human
translational evidence (C) and chemistry orchestration (D) depend on that loop
or on an intervention hypothesis that is not yet justified. Phase 3.6 has **not**
been started.
