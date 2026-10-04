# Phase 3.5 — Experimental decision engine

AXIS can now say which unresolved question limits the current therapeutic
hypothesis, which competing explanations remain plausible, and which candidate
experiment would best separate them. It does **not** say the hypothesis is true,
rank compounds, or decide a development strategy.

> A `DecisionState` is the decision framing *given the evidence currently
> represented in AXIS*. It is not scientific truth. All wording of explanations
> and candidate experiments is an AI suggestion pending researcher review, and no
> experiment has been performed.

## Design in one paragraph

A **deterministic core** (`axis/decision/rules.py`, `axis/decision/service.py`)
reads the Evidence Store and derives evidence links, explanation statuses,
uncertainties, the critical uncertainty and the recommendation. An
**AI-suggested edge** — the wording of four competing explanations and six
candidate experiments with their outcome scenarios — is imported from a frozen,
checksummed package (`axis/resources/decision/erap1-axspa/v1`). The package holds
no evidence, statuses or recommendation. An explanation enters a state only if a
rule can ground it in current evidence. GET requests never build, never search
the web and never call a model.

## Objects

| Object | Where | Notes |
| --- | --- | --- |
| `DecisionState` | `decision_states` | Immutable, versioned, `supersedes_id`; id derives from the evidence digest. |
| `CompetingExplanation` | `decision_explanations` | AI suggestion (`ai_suggestion`); can be promoted explicitly. |
| `ExplanationEvidenceLink` | `decision_explanation_links` | `supports`, `contradicts`, `leaves_unresolved`, `context_limits`, each with rule id and rationale; per state. |
| `ScientificUncertainty` | `decision_uncertainties` (+ `decision_uncertainty_gaps`) | Category, status, relevance, resolvability, fired rules, reasons; per state. |
| `CriticalUncertaintyAssessment` | `critical_uncertainty_assessments` | Selection, per-criterion reasons, and why every alternative lost. |
| `CandidateExperimentProfile` | `candidate_experiment_profiles` | Extends the existing `ProposedExperiment`; purpose, role, proximity, controls, prerequisites, requirements. |
| `OutcomeScenario` | `outcome_scenarios` (existing) | Reused; every candidate has supportive, negative, alternative and non-interpretable scenarios. |
| `OutcomeInterpretation` | `outcome_interpretations` | Scenario × explanation effect: `strengthens`, `weakens`, `does_not_discriminate`, … |
| `DecisionConsequence` | `decision_consequences` | Conditional (`If …`) next action and any new uncertainty. |
| `DecisionConstraints` | `decision_constraints` | Investigator-entered resources only; append-only versions. |
| `decision_events` | append-only | Explicit promotion and experiment status changes. |
| Graph links | `decision_experiment_gaps`, `decision_experiment_discriminates` | `EvidenceGap → addressed_by → Experiment → discriminates → CompetingExplanation`. |

The existing `Hypothesis`/`HypothesisRevision`, `ProposedExperiment`,
`OutcomeScenario` and `OpenQuestion` are reused; no parallel system exists. The
repository held no stored hypothesis, so the decision package creates one
through the existing `HypothesisRepository` (draft, AI-drafted working
formulation of the project objective).

## Rules

`axis/decision/rules.py` defines versioned rules (`axis-decision-1`), each with a
stable id, version, description, inputs, output and rationale: `DECISION-GAP-001`
and `-002`, `DEP-001`, `SEL-001`, `CTX-001`, `REPRO-001`, `BRIDGE-001`, `DIS-001`,
`CLIN-001`, `STRUCT-001` (uncertainties); `EXPL-001`, `EXPL-010`…`013`
(explanations); `CRIT-001` (critical selection); `EXP-001`…`004` (discrimination,
interpretability, recommendation, low-discrimination flag). Every state records
the rules that fired.

There are **no** numeric scores, probabilities, information-gain, entropy or
confidence values anywhere in the decision layer; a test walks the payload to
enforce this.

### Explanation status (DECISION-EXPL-001)

Read from link relationships only:
`supports` and `contradicts` → *weakened*; only `contradicts` → *contradicted*;
`supports` with open items → *partially supported*; `supports` alone →
*supported*; `leaves_unresolved` only → *viable*; `context_limits` only →
*unresolved*; no link at all → the explanation is **not admitted**. Absence of
evidence produces an unresolved link, never a contradiction.

### Uncertainty vocabulary

Relevance: **decision_blocking** (no defensible strategy decision until
resolved), **decision_material** (would change the decision), **informative**,
**peripheral**. Status: `open`, `partially_resolved`,
`resolved_for_current_decision` (never plain "resolved"), `superseded`,
`not_actionable`. Resolvability: `directly_testable`, `indirectly_testable`,
`requires_multiple_experiments`, `currently_not_testable`, `unknown`.

### Critical uncertainty (DECISION-CRIT-001)

Only open or partially resolved, testable uncertainties are eligible. Ordering is
lexicographic over: decision relevance; number of viable explanations depending
on it; resolvability; whether any candidate experiment is available; number of
distinct next actions across those experiments' outcomes. The result carries the
reasons for the winner and, for every other uncertainty, the first criterion on
which it lost or why it was ineligible.

### Experiment comparison

For the critical uncertainty, candidates are compared on transparent dimensions
(there is no total): question addressed, explanation pairs separated, target
proximity, disease relevance, interpretability, required models and reagents,
unestablished prerequisites, complexity, time, cost, feasibility and remaining
uncertainty. The recommendation (DECISION-EXP-003) excludes blocked candidates,
then orders by pairs separated, distinct next actions, interpretability,
proximity, fewer unestablished prerequisites and identifier. Complexity and cost
never decide it.

* **Discrimination**: a pair of viable explanations is separated when one
  scenario strengthens one and weakens the other. A candidate separating no pair
  is labelled *low discrimination* with a non-mechanistic role.
* **Interpretability** is high with all four of: ≥ 3 interpretable scenarios, a
  direct/proximal endpoint, a negative control, a stated confounder addressed;
  moderate with two or three; low otherwise; unknown without any control.
* **Cost** is `not provided`, **time** `unknown` and **feasibility** `unknown`
  ("Feasibility not assessed against local resource constraints") unless the
  investigator enters constraints.

## Outcomes and consequences

Outcome scenarios and consequences are **prospective**: they describe what would
follow, conditionally, and are never presented as observed. Negative and
non-interpretable outcomes are distinct. `what_would_change_our_mind` lists, from
stored scenarios only, the results that would weaken or strengthen the strategy,
each linked to hypothesis, experiment, scenario, explanation effects and
consequence category.

## Investigator actions and the AI boundary

Mutations exist only in the CLI/service (`axis decision constraints`,
`select-experiment`, `promote-explanation`); there is no HTTP write path.
Promotion is explicit and recorded in an append-only event; nothing is promoted
automatically. An experiment can move `proposed → investigator_selected →
planned → in_progress → completed` (or `cancelled`), and `completed` is accepted
only with an existing `experimental_result` claim — a design is never a result.
A change in constraints, statuses or promotions produces a new `DecisionState`.

## Versioning and diff

A state is immutable. Rebuilding with an unchanged evidence digest (evidence,
rules version, constraints, statuses, promotions, candidate set) returns the
existing state. Otherwise a new version supersedes it with a human-readable diff:
edge state changes, uncertainty and explanation changes, critical uncertainty,
recommendation and constraints.

## Interfaces

CLI: `axis decision import-package | build | show | history | explain |
experiments | constraints | select-experiment | promote-explanation`.
`explain --question why_critical | evidence_against | why_not |
what_would_change_our_mind` answers only from the stored state. (No separate
"Ask AXIS" interface exists in this repository.)

API (read-only, project scoped, no filters): `/api/projects/{p}/decision`,
`/decision/history`, `/uncertainties`, `/explanations`,
`/candidate-experiments`, `/candidate-experiments/{id}`, `/decision-trace`.
`/decision` returns `state: null` with a message when nothing has been built.

Workspace: **Decision** is a first-class page: scientific position, critical
uncertainty card, competing explanations with evidence drill-down, recommended
experiment with *Why this experiment?*, comparison matrix, outcome tree (an
ordered text list), *What would change our mind?*, constraints, rule trace with a
textual graph, and history with diffs. The earlier cellular summary moved to
**Cellular decision view** (`/cellular-decision`).

## Closed loop preparation

The architecture is ready for `proposed experiment → performed experiment →
experimental result → evidence update → new DecisionState`, but the reference
project contains no performed Phase 3.5 experiment and none is invented.

## Limitations

* The reference decision rests on a small, AI-assisted curation of six
  publications; the sources are not systematically reviewed and the curated
  evidence is pending expert review.
* Explanation wording, candidate experiments, controls and outcome mappings are
  AI suggestions; the outcome→effect mappings encode scientific judgement that a
  researcher must review.
* The rule set is intentionally small and tuned to engagement, dependency,
  selectivity, context and reproducibility; other uncertainty types would need
  new rules.
* Feasibility, cost and time are unknown without investigator input.
* The decision concerns the *next experiment*, not which therapeutic strategy to
  develop. Strategy comparison is not performed.
* Not implemented, by design: wet-lab execution, literature ingestion, docking,
  molecular dynamics, virtual screening, QSAR, generative chemistry, PK/ADME/
  toxicity prediction, clinical or patient recommendations, portfolio valuation.
