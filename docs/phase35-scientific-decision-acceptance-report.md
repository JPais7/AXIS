# Phase 3.5A — scientific decision acceptance report

Question: does the AXIS Decision Engine make reproducible, defensible and fully
traceable decisions from stored evidence, or does it render plausible-looking
recommendations?

## Release verdict

**PASS WITH CONDITIONS.**

The recommendation is a real function of stored evidence, versioned rules,
investigator input and the frozen candidate designs: counterfactual evidence,
constraints and design mappings each change it (tested), and the chain
evidence → rule → uncertainty → explanation → experiment → outcome → consequence is
reconstructable for every row (§6). No hidden target-specific *decision branch* was
found. It is not a plain PASS because the audit also found where the answer rests
on authored judgement and where it is not yet general (§27–29). It is not a FAIL
because those dependencies are explicit, tested and displayed, not hidden.

Conditions before broader target use are in §27. Software acceptance here says
nothing about whether ERAP1 modulation is a valid therapeutic strategy (§28).

## 1. Baseline

| Field | Value |
|---|---|
| `baseline_branch` | `codex/phase2-transfer` |
| `baseline_commit` | `fb821ee` (local = `origin/codex/phase2-transfer`) |
| merge base with `main` | `881b54c696d8313344856e87f35b62b9ec4349d8`; 11 ahead, 0 behind (verified through the GitHub compare API) |
| `phase34_commit` | `11458e2` |
| `phase35_commit` | `5d91472` (engine) and `fb821ee` (report) |
| `acceptance_commit` / `final_head` | the commit that contains this file; its parent is `fb821ee` (a document cannot cite its own hash — read `git log -1`) |

Pre-existing, not touched: untracked `.DS_Store` files and
`docs/screenshots/phase2-hardening/`; the branch also carries unrelated lupus,
TRM17/TCR, single-cell and DDX24/preprint history, recorded here as pre-existing
branch contamination for later release engineering (cherry-pick/split/rebase).
GitHub Actions on `fb821ee`: Windows and macOS green; Ubuntu 403 tests passed and
failed only the pre-existing `mypy` unused-ignore in `axis/pharmacology/chemistry.py`.

**Documentation claim checked.** The prompt said `docs/phase3-experimental-decision-engine.md`
might be empty. It is not (10 429 bytes on the remote at `fb821ee`). It has been
corrected and extended for the engine as it is now (13.7 kB).

## 2. Phase 3.5 commit and 3. Acceptance commit

See §1. The acceptance commit contains the hardening below, 45 new acceptance tests,
the rule audit, the matrix, the regenerated screenshots and this report. Not pushed
unless stated by the conversation.

## 4. Architecture inspected

Read in full: `domain/decision.py`, `decision/{rules,service}.py`,
`storage/decision.py`, `cli/decision.py`, `api/server.py` decision routes,
migration 009, the decision package, `tests/test_decision.py`,
`web/src/decision.ts`, both web tests, both Phase 3.5 documents, and the consumed
layers (`domain/{discovery,cellular,pharmacology}.py`, `cellular/{rules,service}.py`).
Execution paths were traced by running, not inferred from names
(`scripts/audit_decision_trace.py`).

**Structural change made by the audit:** the scientific logic that lived inside one
large `build()` method was extracted into a pure `axis/decision/engine.py::analyze`
(explicit inputs → analysis). The service loads inputs and persists; CLI, API and UI
all call the same path. This is what made counterfactuals, order-shuffling and
sensitivity analysis possible.

## 5. Rule inventory

23 rules, rule set `axis-decision-2` (fingerprint recorded in every state). Full
per-rule table with condition, evidence dependencies, failure behaviour and covering
tests: [`phase35-decision-rule-audit.md`](phase35-decision-rule-audit.md). Every rule
is a function in `rules.py`/`engine.py`; a test fails if any rule never fires in the
scenario battery. Added during the audit: `DECISION-TRANS-001`,
`DECISION-BRIDGE-002`, `DECISION-EXP-005`.

## 6. Production ERAP1 decision trace (`AXIS-DD-ERAP1-CURATED-001`)

Reproduce with `poetry run python scripts/audit_decision_trace.py` (clean in-memory
store, frozen resources only). Condensed:

| Stage | Input | Rule / transformation | Output | Provenance |
|---|---|---|---|---|
| Evidence | 9 biochemical measurements; 4 exposure, 9 HLA, 2 immune assessments | Phase 3.4 `aggregate` per edge | biochemical, exposure, HLA, immune **supported** | persisted measurement / assessment ids |
| Evidence | 11 engagement assessments (7 not applicable, 4 not assessed) | `aggregate` | engagement **not assessed** | `cellular_assessments` |
| Evidence | 11 functional assessments | `aggregate` | functional **insufficient** | same |
| Evidence | disease / clinical: no records | — | **not assessed** | — |
| Evidence | 18 selectivity assessments: 4 not assessed, 14 not directly comparable | Phase 3.3 comparability | 0 comparable | `selectivity_assessments` |
| Evidence | Chen vs Tran, surface free heavy chain after knockdown | opposite direction, different sources | 1 source disagreement | 3 readout ids |
| Gap | 4 engagement questions (Chen DG013A ×2, Maben 2, Maben 3) | Phase 3.4 import | open evidence gaps | `open_questions`, `cellular_gap_links` |
| Uncertainty | biochemical ✓, phenotype ✓, engagement not assessed, selectivity unresolved; 2 of 3 compounds have both biochemical and phenotype, DG013A identity unresolved | `DECISION-GAP-001` + `-002` | `target_engagement`: open, **decision_blocking**, directly testable | 20+ evidence refs |
| Uncertainty | genetic dependency supported, compound dependency uncertain | `DEP-001` | `target_dependency`: open, material | 10 refs |
| Uncertainty | 0/18 comparable | `SEL-001` | `selectivity`: open, material, indirectly testable | 18 refs |
| Uncertainty | allotype unreported; 4 experiments lack the disease-relevant context | `CTX-001` | `genetic_context`: open, material | context refs |
| Uncertainty | source disagreement | `REPRO-001` | `reproducibility`: open, material | readout refs |
| Uncertainty | functional insufficient | `BRIDGE-001` | `mechanistic_bridge`: open, material | 11 refs |
| Uncertainty | disease / clinical / structure | `DIS-001`, `CLIN-001`, `STRUCT-001` | informative; not actionable ×2 | edge refs |
| Explanation | 19 supports, 26 unresolved | `EXPL-010`, `-001` | on-target **partially supported** (ai_suggestion) | frozen wording + derived links |
| Explanation | 22 unresolved | `EXPL-011`, `-001` | off-target **viable** | — |
| Explanation | 11 unresolved | `EXPL-012`, `-001` | indirect pathway **viable** | — |
| Explanation | 1 unresolved, 4 context limits | `EXPL-013`, `-001` | context-dependent **viable** | — |
| Criticality | 8 uncertainties (9 with structure) | `CRIT-001` | `target_engagement` — decided on **decision relevance** (blocking vs material); no ties | 7 alternatives with reasons |
| Experiment | 4 candidates considered for engagement | `EXP-001…005` | chemical-genetic (3 pairs, falsifying, high) > engagement assay (2) > concentration alignment (1) > replication (0, low discrimination) | per-candidate reason |
| Outcome | 5 scenarios of the recommended experiment | frozen, prospective | on-target / off-target / indirect effects per scenario | `outcome_interpretations` |
| Consequence | same | frozen, conditional | strengthen · weaken · change model · investigate context · require replication | `decision_consequences` |

## 7. Critical uncertainty audit

Selected: **`uncertainty:target_engagement`** — "Do the phenotype-producing
compounds directly engage ERAP1 in cells at those exposures?" Selection was decided at
the first criterion: it is the only uncertainty raised to *decision_blocking*, by
`DECISION-GAP-002`, because selectivity is unresolved so an off-target explanation
cannot be excluded. The other seven were *not* decided by "lower priority" but by:

* target dependency, selectivity, genetic context, reproducibility, mechanistic
  bridge — *decision_material*, below *blocking*;
* disease relevance — *informative* (downstream of unresolved dependency);
* clinical translation, structural mechanism — *not actionable* and not testable.

Audit finding: the choice rests entirely on `GAP-002`. Counterfactual CF7 shows that
with comparable selectivity engagement drops to *material* and the lexicographic
criteria below it take over; this is the intended behaviour but it means the
selectivity evidence (currently 0/18 comparable) carries the decision.

## 8. Competing explanation audit

All four are **frozen AI-suggested wording** (`ai_suggestion`; never source
assertions; no investigator acceptance implied). Whether each *enters* a state is
decided by rules from stored evidence; ungrounded ones are listed as not admitted
(tested; CF2/CF4/CF5). Status counts in §6. None is "established": the strongest is
*partially supported*, and every explanation shows what keeps it open.

## 9. Experiment-selection audit

Six frozen candidates (4 compared for this uncertainty). Each is traceable to its
gaps, discriminated explanation pairs, controls, endpoint, prerequisites (e.g. an
engagement readout and an ERAP1-null/rescue model are `not_established`),
feasibility ("not assessed"), scenarios and residual uncertainty. *Why A beat B* is a
stored sentence derived from the first differing criterion; ties are reported.
Order independence was proven with six random shuffles and a database-order test
(§15–17). **Audit finding fixed:** the old final tie-break was the identifier; it is
now reported as a tie and used for display order only.

## 10. Outcome-tree audit

Every scenario is `prospective`, lists explicit explanation effects, a conditional
`If …` consequence, and (for non-interpretable outcomes) the new uncertainty it
opens. Negative results are distinct from technical failure. The UI renders an
ordered list with an `aria-label`, repeats "prospective — not observed" per branch,
and asserts no probabilities.

## 11. Falsification audit

New rule `DECISION-EXP-005`: a candidate must have an interpretable scenario that
weakens a currently preferred explanation, or it ranks after those that do. The
recommended experiment has such scenarios (persists-without-ERAP1; dependence-without-
engagement). Honest note: in the reference fixture five of the six candidates satisfy it (even
replication, whose "fails to reproduce" outcome weakens every compound-based
explanation); only the allotype panel does not, and it is outside the comparison for
this uncertainty. The criterion therefore does not change the production ranking; it
is exercised by the synthetic tests. Low discrimination remains the operative guard
against replication.

## 12. Epistemic-boundary audit

Checked by tests on the production state: biochemical, exposure, HLA and immune are
*supported* while engagement, functional modulation, disease and clinical are not,
and no statement merges them; structure creates no explanation link and its
uncertainty is *not actionable*; no selectivity ratio field exists and "Not assessed"
and "Not directly comparable" stay separate; DG013A has no compound id and no
provider (ChEMBL) mapping exists anywhere in the state; Maben links state
"Engineered HeLa H-2Kb / no HLA allele reported"; the only HLA allele listed is
HLA-B\*27:05; ERAP1 allotype is *unreported*; no "validated across axSpA" claim; every
displayed statement carries one of the six epistemic classes.

## 13. Counterfactual tests

All TEST-ONLY mutations of a deep copy; production evidence never altered. CF1–CF10
pass (`phase35-acceptance-matrix.md`). Notable discoveries that required code
changes: CF4 initially had no rule and would have fallen to "disease relevance";
CF3 left a contradicted engagement *open*; CF7 left engagement *blocking* and the
off-target explanation unchanged. All fixed.

## 14. Generic-target test

`engine.analyze` runs on a synthetic target ("TGT-9", generic ids) and its
uncertainties, reasons and explanations contain none of ERAP1, HLA-B27, axSpA or
immunopeptidome. **Scope of this claim:** engine and rule level only. A full store-
level second target is *not* demonstrated: the importer is guarded to human ERAP1, and
the evidence assembler reads the Phase 3.4 cellular schema, which has HLA-specific
edges and context fields. See §27.

## 15. Deterministic replay, 16. Network-off, 17. LLM-off

Two clean stores import the frozen discovery, protein identity, pharmacology,
cellular and decision packages (the structure package is not needed by the engine) and build byte-identical states with sockets and
`httpx` disabled and the `anthropic`/`openai` modules blocked; the same replay passes
from an installed wheel. No decision module imports a network or model library
(static test). Ids are digest-derived; the only non-semantic field is `created_at`,
which is injected in tests.

## 18. Migration integrity, 19. Package integrity

Migrations 001–008 are byte-identical to the Phase 3.4 commit; 009 is additive (14
tables, no DROP/ALTER/DELETE/CASCADE); deleting a referenced hypothesis, explanation
or proposed experiment is rejected by foreign keys; 8→9 and clean paths pass. The
package contains wording only (a test forbids statuses, rankings, recommendations or
evidence), corruption and a wrong importer version are rejected, a malformed scenario
fails, and the installed wheel ships the verified package.

## 20. Project / target / compound isolation

Project: a state cannot be read from another project; the demo project has no state.
Compound: coverage is reported per compound (compound 1: biochemical only, no
phenotype; compounds 2–3: both; DG013A: unresolved identity, not a compound).
**Limitation:** the *rules* still evaluate evidence at project/target level — they
report non-pooling and unresolved identity in the reasons but do not compute
uncertainty per compound (§27). A second real target could not be tested in-store.

## 21. Decision sensitivity (categorical)

Removing a group of evidence and recomputing gave:

* **Decision-sensitive:** biochemical activity (critical → target dependency);
  compound phenotype (critical → assay translation; recommendation → none; on-target
  and off-target not admitted); all cellular assessments pending review (critical →
  assay translation; recommendation → none).
* **Explanation-only:** functional insufficiency (indirect pathway not admitted).
* **Non-decisive** (single-group removal): genetic dependency, engagement, selectivity
  data as recorded, source disagreement, gaps, structure.

Interpretation: the whole recommendation rests on the cellular phenotype evidence.

## 22. Review-status sensitivity

37 cellular assessments are *pending expert review*, 0 accepted. This is shown above
the decision. Excluding them removes the recommendation (§21). No automatic policy
change was made.

## 23. API / CLI consistency

One engine. CLI `build`/`show`/`explain`/`experiments`/`history` and the API return
the same state (tested). GET routes are read-only, project-scoped, bounded (history
limit 1–100), make no provider or model call, and `/decision` returns an explicit
"not built" state. Evidence windows (3 × 100 cellular, 100 selectivity, 100
compounds) now **refuse** to run on truncated data instead of dropping records.

## 24. Frontend logic audit

`web/src/decision.ts` contains no ERAP1/HLA-B27/axSpA text, no rule comparisons, no
ranking beyond ordering by the server-supplied `rank`, no scores. Searches for
`probab|confiden|score|entropy|information gain|posterior|likelihood|percent` across
`axis/decision`, `axis/domain/decision.py` and `decision.ts` find only disclaimers
("no probabilities", "no numerical score"), asserted by tests.
Remaining ERAP1 text: the frozen **fixture** wording (allowed) and the Phase 3.4
evidence-edge labels. Remaining specificity in the engine: the schema names `hla`,
`hla_alleles` and the "disease-relevant (HLA) context" notion, inherited from the
Phase 3.4 evidence model — schema, not branching.

## 25. Accessibility

Playwright DOM checks at 1440 and 1024 px: no heading-level skips, every button/link
named, outcome tree is an ordered list with a label and per-branch text, table has a
caption and scoped headers, keyboard section navigation, Enter/Escape focus return,
no horizontal overflow, no remote requests. No automated axe-core audit was run
(library not installed); contrast was inspected visually, not measured.

## 26. Validation gates

| Gate | Result |
|---|---|
| Full Python suite | **448 passed, 2 skipped** |
| Phase 3.5 tests | `test_decision.py` 47 + `test_decision_acceptance.py` 45 |
| Phase 3.4 / 3.3 regression | included in the full suite |
| Ruff, Phase 3.5 files | clean (one pre-existing `UP038` in `axis/api/server.py:25`) |
| Ruff, whole repository | **285 findings, identical to the pre-3.5 count** (pre-existing debt) |
| mypy | no issues, 132 files |
| TypeScript / ESLint | clean |
| Frontend contract tests | 34 passed |
| Production build | built (existing >500 kB NGL chunk warning) |
| Wheel build/install | passed; decision, cellular, pharmacology and structure verifiers pass from the installed wheel |
| Migrations 8→9, legacy, clean | passed |
| Two-store, network-off, LLM-off replay | passed (repository and installed wheel) |
| API / CLI smoke | passed (7 routes 200; CLI build/show/explain/history/experiments) |
| Playwright | **15 passed** at 1440 and 1024 |
| Manual visual inspection | overview, critical uncertainty, comparison, why-this-experiment, outcome tree, evidence drawer, robustness, constraints, non-discriminating drawer |
| `git diff --check` | clean |

**Not executed / limits of verification:** GitHub Actions on the acceptance commit;
Python 3.12 locally (runs used 3.14.6; CI uses 3.12); Node 26 rather than the pinned
engine; `npm ci`; Microsoft Edge (Chrome for Testing used); an axe-core audit; a
screenshot of the no-actionable-uncertainty state (no production data produces it;
covered by tests); any expert scientific review.

## 27. Unresolved issues / conditions for broader use

1. **Authored mappings decide the ranking.** Which experiment "separates" which
   explanations is encoded in AI-written scenario→effect mappings. A researcher must
   review them; flattening one candidate's mappings changes the recommendation
   (tested). Condition: independent review of the frozen candidate designs.
2. **Not yet demonstrably generic.** Engine/rules are target-neutral; the importer,
   the evidence assembler's cellular schema and one fixture are ERAP1/HLA-specific.
   Condition: a second real target through the full store before claiming generality.
3. **Project-level aggregation.** Rules do not evaluate per compound; they report
   non-pooling. Condition: compound-scoped uncertainties.
4. **The recommendation depends on pending-review evidence** (§22).
5. **Fixture inertness of the falsification criterion** (§11).
6. **Bounded evidence windows** (100) — the engine now refuses larger projects
   rather than paginating.
7. CI on the acceptance commit is pending; Ubuntu `mypy` debt from Phase 3.3 remains.

## 28. Scientific limitations

Six selected publications, AI-assisted extraction, no systematic review; the
Chen/Tran disagreement is surfaced, not resolved; DG013A remains an unresolved
label; this is not evidence that ERAP1 inhibition treats axSpA, that any compound is
clinically effective, that ERAP1 is a validated target, that engagement has been
shown, or that HLA-B27 molecular changes imply patient benefit.

## 29. Product limitations

Constraints, cost, time and feasibility are unknown unless entered; investigator
actions are CLI-only; there is no Ask AXIS interface in the repository (grounded
answers come from `axis decision explain`); the graph is textual; the
sensitivity analysis is group-level, not per record.

## 30. Defects found by the audit (all fixed unless listed in §27)

Hard-coded explanation ids and ERAP1/HLA-B27 wording in rules; input-order
dependence in disagreement fields and in the trace's copy of the evidence; silent
identifier tie-breaking; no way to tell evidence change from methodology change; no
rule for biochemical-only and engagement-without-phenotype states; a contradicted
engagement left "open"; resolved selectivity neither weakening off-target nor
relaxing the blocking flag; silent truncation at 100 records; a bare `KeyError` for
an incomplete scenario; review status not propagated; position statements lacking an
epistemic class and using a lower-cased edge label ("Hla").

## 31. Recommended Phase 3.6

**Experimental Results Loop.** The audit shows the engine is sound as a decision
*framework* but that every state is blocked on one unmeasured link and on unreviewed
authored judgement. The most valuable next capability is to import real laboratory
results as `experimental_result` claims, attach them to a candidate experiment's
scenarios and produce `DecisionState` v2 with a cause-attributed diff — which also
forces the review workflow for the candidate mappings (condition 1). Multi-target
generalization is the close second and should follow once a result has exercised
the loop. Phase 3.6 has **not** been started.
