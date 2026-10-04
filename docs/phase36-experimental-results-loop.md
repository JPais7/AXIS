# Phase 3.6 — Experimental results loop

AXIS can now take an experiment that was actually performed through to a new,
auditable DecisionState:

```
DecisionState v1 → selected experiment → performed experiment → experimental result
→ QC → scenario match → proposed interpretation → scientific review
→ eligible evidence contribution → explicit rebuild → DecisionState v2 → causal diff
```

Nothing in that chain is automatic. Importing a result never changes the decision;
reviewing never rebuilds it. A new state exists only after `axis decision rebuild`
(or `DecisionService.rebuild`).

> No real laboratory result exists in this repository. Every result used to
> demonstrate the loop is **SYNTHETIC / TEST-ONLY** (`scientific_status:
> synthetic_test_fixture`, `not_real_experimental_evidence: true`). The production
> ERAP1 decision is unchanged.

## Epistemic separation

| Object | Meaning | Where |
|---|---|---|
| `ProposedExperiment` | AXIS or an investigator *proposes* an experiment | Phase 2/3.5 |
| `OutcomeScenario` | an *anticipated* outcome | Phase 2/3.5 |
| `PerformedExperiment` | it *was executed*; may implement a proposal or not | `performed_experiments` |
| `DesignDeviation` | how the execution differed from the proposal | `experiment_design_deviations` |
| `ExperimentalResult` | what was *observed*; class `experimental_result`; immutable | `experimental_results` |
| `ResultInterpretation` | what it *might mean*; `ai_suggestion` or `researcher_hypothesis` | `result_interpretations` |
| `ScenarioMatchAssessment` | observation vs anticipated scenarios | `scenario_match_assessments` |
| `ScientificReview` | one reviewer's explicit decision; append-only | `scientific_reviews` |
| evidence contribution | an *eligible* interpretation folded into one edge and scope | decision input |
| `DecisionState` | the decision framing given the evidence represented | Phase 3.5 |

The domain objects (`axis/domain/results.py`) are target-neutral; HLA, allotype and
disease live in `context` and `facets` data, never in names. A test enforces it.

## Import format

A result package is a directory: `manifest.json`, `manifest.sha256`, and the raw or
processed artifacts it references. The manifest lists artifacts (path, media type,
role, sha256), performed experiments (scope, context, controls, measured edges,
endpoints, QC, deviations, proposal link), results (one per observation, with raw and
processed artifact ids, transformations and analysis method/version, replicate
summary, statistics, categorical **facets**) and interpretations. Validation fails
loudly on: unknown project, experiment, compound or artifact; an endpoint the
experiment does not declare; a missing `measures_edges`; an epistemic class other
than `experimental_result`; a modified artifact (checksum); a synthetic package
without `--allow-synthetic`; an altered manifest. Import is one transaction and
idempotent; identical content is a no-op, changed content under the same identity is
an integrity conflict.

Artifacts are references (path, sha256, media type, size) — raw files never go into
database rows. `axis experiment result verify-artifacts` re-hashes them.

Not implemented: a CSV/TSV *result-table* importer (TSV files are supported as
artifacts, not as result rows), instrument connectors, statistical recomputation.
Supplied statistics and uncertainty are preserved verbatim (`42 ± 18` stays `42 ± 18`);
none is computed.

## Quality control and eligibility

QC is categorical (controls, technical validity, replicate quality, assessment) and
has no score. Eligibility is decided by pure, versioned rules
(`axis/experiments/policy.py`, [audit](phase36-result-rule-audit.md)):

* `RESULT-QC-001` technical failure / non-interpretable QC → ineligible; a failed
  positive control is never a biological negative;
* `RESULT-REV-001` rejected, conflicting or needs-revision → excluded in every mode;
* `RESULT-REV-002` pending → eligible only in `exploratory` mode, labelled;
* `RESULT-EDGE-001` an interpretation may update only an edge the experiment declares
  it measures;
* `RESULT-CTX-001` a contribution keeps its scope and context;
* `RESULT-SUP-001` superseded or withdrawn results are not current evidence;
* `RESULT-DEV-001` a limiting deviation adds a caveat, an invalidating one excludes.

Eligibility states: `eligible`, `eligible_with_caveat`, `pending_review`,
`ineligible_qc_failure`, `ineligible_edge_not_measured`, `ineligible_design_deviation`,
`superseded`, `withdrawn`, `rejected`, `review_conflict`, `needs_revision`.
*Completed* is not *interpretable*: the experiment lifecycle has separate terminal
states `completed_interpretable`, `completed_non_interpretable`, `failed_technical`,
and the first two require a matching QC of a performed experiment.

## Scenario matching

Anticipated scenarios carry frozen categorical *signatures*
(`scenario-signatures` package, AI-suggested, review pending). An observation carries
categorical facets. Per scenario: `matches` (all facets agree), `partially_matches`
(some agree), `contradicts`, `ambiguous`; overall additionally
`outside_predefined_scenarios` and `non_interpretable`. There are no probabilities
and an observation that matches nothing is **never force-fitted**: it is stored, an
`unexpected_result` uncertainty (`DECISION-RESULT-003`) is raised and review is
requested.

## Review

Review is explicit, append-only and per object: `experimental_result`,
`result_interpretation`, `scenario_mapping` (`scenario|explanation`),
`candidate_design`, `evidence_assessment`. Decisions: `pending`, `accepted`,
`accepted_with_caveat` (requires the caveat), `rejected`, `needs_revision`. The state
is derived from each reviewer's latest decision: accept together with reject is a
**conflict** (no majority rule), a reviewer can change their own mind (both entries
stay), and a name that identifies AI is rejected — AI cannot accept its own science.
A result can be accepted while its interpretation is rejected.

**Review policy** `decision-review-policy-v1` is explicit data, part of the
methodology fingerprint. Two modes:

| Mode | accepted / accepted-with-caveat | pending | rejected / conflict / needs revision |
|---|---|---|---|
| `exploratory` (default) | used | used, labelled | excluded |
| `reviewed` | used | excluded | excluded |

The mode applies to result interpretations, to the 37 cellular assessments, to the 84
authored scenario→explanation mappings and to candidate designs
(`DECISION-REVIEW-001`). The state records the mode and how many pending mappings,
designs and interpretations it used. Under `reviewed` the production ERAP1 decision
has no cellular evidence and no recommendation, because nothing has been reviewed —
that is the accurate statement of where the science stands, not a defect.

## Evidence update

An eligible contribution touches **one edge and one scope** (`DECISION-RESULT-001`):
a compound, a source-reported perturbagen (e.g. DG013A, never given an invented
chemical identity), or the target. There is no cascade — an accepted engagement
result changes neither functional modulation, HLA phenotype, immune phenotype nor
disease edges (tested) — and no generalization to another compound, context, HLA
subtype or allotype.

Engagement is rolled up over the phenotype-producing scopes (`DECISION-RESULT-002`):
`open` → `partial` → `complete`. Project-level state becomes `incomplete` while
some required scope is undecided, and `supported` only when every required scope is.
The engagement uncertainty becomes `partially_resolved` (and `decision_material`)
after one compound is decided, and `resolved_for_current_decision` only when all are.
Opposite eligible results for one scope make that scope `mixed` and raise a
reproducibility uncertainty (`DECISION-REPRO-002`); both stay.

## DecisionState v2 and the causal diff

`rebuild` creates the next immutable state. Its digests separate **evidence**,
**review**, **investigator input** and **methodology** (rules, review policy,
candidate set, hypothesis revision), so a change can be attributed. The diff is a
scientific diff, not a JSON diff: causes (`new_experimental_evidence`,
`review_status_change`, `evidence_removed`, `methodology_change`,
`investigator_input_change`), evidence and scope changes with the rule, explanation
changes with the links that caused them, uncertainty changes, critical uncertainty and
recommendation changes with their rule path and triggering results, and
`decision_changed`: *yes*, *no*, *partially* or *pending review* — a valid result may
not change the decision. A change that rests only on interpretations still pending
review is reported as *pending review*.

* **Impact preview** (`axis experiment result impact`, `GET …/decision-impact`):
  "if this interpretation were accepted", computed by the real rules, never stored,
  labelled *Preview — not current decision*.
* **Sensitivity**: per-result removal and "results pending review" are ablation
  groups, so each state says which results are decision-sensitive.
* **Questions**: `what_did_experiment_teach`, `was_result_predicted`,
  `what_if_not_trusted`, `resolution_scope` answer only from stored records.

## Surfaces

CLI: `axis experiment result import-signatures | validate | import | show | list |
review | packet | impact | withdraw | verify-artifacts`, `axis decision rebuild | diff`.
Mutations are CLI/service only. API (read-only): `performed-experiments`, `results`,
`results/{id}`, `results/{id}/review`, `results/{id}/decision-impact`,
`review-queue`, `scenario-mappings`, `decision/diff`, `decision/timeline`. Workspace:
**Experiments / Results** (performed experiments, results ledger, decision timeline,
result drawer with OBSERVED / INTERPRETATION / review kept apart, scenario match, QC,
deviations, artifacts with checksums, impact preview), **Review** (pending,
conflicts, mapping queue) and, on **Decision**, the engagement-by-scope table, the
results informing the state and the causal diff. Synthetic data carry a persistent
text banner ("Synthetic test fixture — not real experimental evidence").

## Synthetic demonstration

`scripts/build_synthetic_loop_demo.py` builds a **separate** database: v1; a
synthetic engagement result for Maben compound 3 imported (exploratory, pending →
*partially resolved*, pending review); reviewed (*accepted with caveat*; a disputed
result left in *review conflict*; a failed-control result *ineligible*; an unexpected
result *outside the predefined scenarios*); then results for compound 2 and DG013A →
engagement *complete* → the critical uncertainty changes to target dependency
(`DECISION-DEP-001`), triggered by named results. `tests/test_results_loop.py` also
shows withdrawal reverting the scientific state without deleting history.

## Limits

* Software demonstrates the loop; **no real result has been imported**, so the
  scientific loop is validated only on synthetic data.
* Scenario signatures and the 84 mappings are AI-authored and unreviewed; matching and
  ranking are only as good as they are.
* Only engagement is compound/perturbagen-scoped; dependency, selectivity and the
  others remain target-level.
* Reviewer identity is a free-text name; there is no authentication.
* The decision integration still reads the Phase 3.4 cellular evidence schema
  (HLA-specific edges); the result model itself is generic.
* Evidence windows remain bounded to 100 records and the engine refuses larger sets.
* Not implemented, by design: LIMS/ELN, instrument control, docking, MD, QSAR,
  clinical recommendations, probabilities or information-gain figures.
