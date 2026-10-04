# Phase 3.5A — acceptance matrix

Section numbers refer to the acceptance prompt. "Result" is what was actually
executed on the final tree. `T` = `tests/test_decision.py`,
`A` = `tests/test_decision_acceptance.py`, `W` = `web/tests/decision.test.mjs`,
`P` = `web/tests/decision.spec.mjs` (Playwright).

| § | Requirement | Rule / test | Expected behaviour | Result |
|---|---|---|---|---|
| 5 | Decision derived, not displayed | A `test_production_decision_equals_a_pure_recomputation`, `test_recommendation_is_a_function_of_evidence_rules_and_candidate_design` | Recomputing from stored inputs reproduces the state; changing evidence, constraints or candidate mappings changes the recommendation (3 distinct outcomes incl. none) | pass |
| 7 | No hidden target logic | A `test_no_target_specific_branch_in_decision_logic`; source grep (see report §24) | No comparison with ERAP1/UniProt ids in logic; no hard-coded explanation ids | pass |
| 8 | Every rule enumerated | `docs/phase35-decision-rule-audit.md`; A `test_zz_every_rule_fired…` | 23 rules, each with condition, failure behaviour, tests; each fires in ≥1 scenario | pass |
| 9 | Rule purity | A `test_rules_are_pure_and_deterministic_without_network` | Inputs not mutated, repeat output identical, sockets/httpx disabled | pass |
| 10, 48 | Evidence change ≠ rule change | A `test_evidence_change_and_methodology_change_are_distinguishable` | Evidence-only change → cause `["evidence"]`; rules-only change → `["methodology"]` | pass |
| 12 | CF1 resolve the winner | A `test_cf1_…` | Engagement resolved; another uncertainty becomes critical | pass |
| 13 | CF2 remove support | A `test_cf2_…` | Removed ids vanish from links; removing the phenotype gives `assay_translation` and no stale recommendation | pass |
| 14 | CF3 contradiction | A `test_cf3_…` | On-target *weakened* (not "uncertain"), off-target gains a supporting link, contradiction listed in position | pass |
| 15 | CF4 no cellular phenotype | A `test_cf4_…` | Critical `assay_translation` (DECISION-TRANS-001); no recommendation; message says no unblocked candidate | pass |
| 16 | CF5 engagement without phenotype | A `test_cf5_…` | DECISION-BRIDGE-002; no engagement uncertainty; differs from CF4/CF6 | pass |
| 17 | CF6 phenotype without engagement | A `test_cf6_…` | On-target only *partially supported*; off-target viable; engagement blocking | pass |
| 18 | CF7 selectivity resolved | A `test_cf7_…` | Off-target *weakened* not removed; engagement drops to decision_material | pass |
| 19 | CF8 incompatible selectivity | A `test_cf8_…` | 500 incompatible items resolve nothing; "Not assessed" vs "Not directly comparable" kept apart; no ratios | pass |
| 20 | CF9 different target | A `test_cf9_…` | Engine runs on a synthetic target; output contains none of ERAP1, HLA-B27, axSpA, immunopeptid… | pass (engine level) |
| 21 | CF10 no actionable uncertainty | A `test_cf10_…`, W `no actionable uncertainty…` | `critical = null`, no recommendation, "No next discriminating experiment is currently justified" | pass |
| 22–23 | Explanation grounding / AI boundary | T `test_explanation_without_grounds…`, `test_epistemic_boundaries…`; A `test_fixture_contains_wording_only…` | Ungrounded explanations not admitted; kinds `ai_suggestion` until explicit promotion | pass |
| 24 | Hypothesis audit | A `test_hypothesis_revision_is_used_and_never_substituted` | State carries stored revision and text; a new revision yields a new state | pass |
| 26–28 | Why A beat B; no lexical priority; low discrimination | A `test_input_order_never_changes_the_decision` (6 seeds), `test_ties_are_reported…`; T `test_replication_is_flagged_low_discrimination` | Shuffled inputs give identical decisions; ties reported, identifier only orders display; replication flagged | pass |
| 29–30 | Negative outcome / falsification | A `test_outcome_tree_text_is_conditional…`; rule DECISION-EXP-005 | Recommended experiment has a scenario weakening a preferred explanation | pass |
| 31 | What would change our mind | T `test_what_would_change_our_mind`; W; CLI smoke | Answer assembled from hypothesis→experiment→scenario→effect→consequence | pass |
| 32, 77 | Outcome tree semantics | A (same); P DOM-semantics block | Ordered list with `aria-label`, every branch "prospective — not observed", conditional text, no colour-only meaning, no heading skips, tables with caption and scoped headers | pass |
| 33–34 | No fake numbers | T `test_no_scores_or_probabilities_anywhere`; W score regex; A frontend test | No float, score, probability, entropy or information-gain key/value | pass |
| 35 | Selectivity epistemology | A `test_cf8_…` | Status classes preserved; absence ≠ selectivity | pass |
| 36–37 | Cellular / structural epistemology | A `test_layers_are_not_collapsed_and_structure_never_supports` | Only biochemical, exposure, HLA, immune supported; engagement, functional, disease, clinical not; structure never a link | pass |
| 38–39 | DG013A and Maben-2 identity | A `test_project_and_compound_isolation`, `test_chemical_identity_and_context_epistemology` | No DG013A compound id, no provider (`CHEMBL`) mapping anywhere in the state | pass |
| 40–42 | HLA, allotype, AS vs axSpA | A (same) | Only HLA-B*27:05 listed; Maben links say "Engineered HeLa H-2Kb / no HLA allele reported"; allotype unreported; disease/clinical not assessed; no "validated across" claims | pass |
| 43 | Statement classes | A `test_every_displayed_statement_has_an_epistemic_class` | Position, uncertainty, explanation, candidate, scenario all carry an allowed class | pass |
| 44–45 | Provenance drill-down, locators | A `test_every_link_terminates_in_a_stored_record_with_a_source_locator` | >30 links resolve to stored rows; assessment→experiment (source, locator)→readout (locator)→claim provenance | pass |
| 46 | State immutability | A `test_persisted_states_are_immutable_across_later_changes`; T `test_replay_is_idempotent_and_states_immutable` | v1 payload byte-identical after constraints, rule change, fixture replay | pass |
| 47 | Decision diff | A (§48 test); T `test_resolving_critical_uncertainty_promotes_another` | Diff names edges, uncertainties, critical, recommendation, cause | pass |
| 49–51 | Replay, network-off, LLM-off | A `test_llm_and_network_free_replay_is_identical…`; T `test_two_stores…`; wheel verifier | Two stores identical with sockets, httpx and `anthropic`/`openai` imports blocked; no such imports in `axis/decision` | pass |
| 52–53 | Fixture and checksum | A `test_fixture_contains_wording_only…`; T `test_package_checksum…`, tamper test | Wording only; corruption rejected; wheel ships the verified package | pass |
| 54 | Migration 009 | A `test_migrations_001_to_008_are_unchanged_and_009_is_additive`; T `test_migration_9_clean_and_legacy_upgrade` | 001–008 byte-identical to `11458e2`; 14 tables; no DROP/ALTER/DELETE/CASCADE; 8→9 and clean | pass |
| 55 | DB order independence | A `test_database_insertion_order_does_not_change_the_decision` | Cellular package imported in reversed order → identical evidence, explanations, uncertainties, candidates | pass |
| 56 | Duplicate replay | A `test_duplicate_replay_creates_no_duplicate_entities` | Row counts unchanged after re-import and rebuild | pass |
| 57–59 | Project / target / compound isolation | A `test_project_and_compound_isolation`; T `test_project_isolation_and_unknown_scope` | Other project cannot read the state; compound coverage per compound, not pooled | pass (limits §27) |
| 60–61 | Result boundary, closed loop | A `test_prospective_scenarios_and_proposals_never_count_as_evidence`, `test_closed_loop_with_a_synthetic_result…` | Scenarios never enter evidence; synthetic result is an `experimental_result` claim linked to a completed status; proposal row unchanged | pass |
| 62–64 | Review status and robustness | A `test_pending_review_is_visible_and_excluding_it_changes_the_decision`; W | 37 pending / 0 accepted shown above the decision; excluding them changes critical uncertainty and recommendation | pass |
| 65–66 | Sensitivity view | A (same); P robustness screenshot | Leave-group-out lists decisive evidence; no numbers | pass |
| 67–68 | Why not the other / wording | state `candidates[].reason`; W `Recommended next discriminating experiment` | Every alternative has a deterministic reason; "Best experiment" absent | pass |
| 69 | Constraints absent | T `test_cost_time_feasibility_are_not_invented` | "Feasibility not assessed…", cost "not provided", time "unknown" | pass |
| 71–73 | API/CLI/single engine | A `test_api_and_cli_use_the_same_engine`; T API/CLI tests; frontend test | One `engine.analyze`; GET never builds; frontend contains no rule logic | pass |
| 79 | Empty states | A `test_empty_candidate_and_explanation_sets_are_explicit`; T `test_api_get_never_builds…`; W | Explicit scientific empty states | pass |
| 80 | Error states | A `test_integrity_failures_fail_loudly`, `test_truncated_evidence_is_refused…`, scenario-without-consequence test | Corrupt package, bad importer, malformed scenario, truncated window, unknown project all fail with explicit errors | pass |
| 81 | Performance / scope | `evidence()` windows (3×100 cellular, 100 selectivity, 100 compounds) | Bounded, project/protein scoped; refuses truncation | pass |
| 85 | Gates | see report §26 | | pass except where stated |
| 87 | Screenshots | `docs/screenshots/phase35/` (26 files) | 13 captures × 2 widths | 9 of the 10 views required by §87 captured; the no-actionable-uncertainty state (10) is covered by a contract test and an engine test only, because no production data produces it |
