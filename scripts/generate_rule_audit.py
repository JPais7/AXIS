"""Regenerate docs/phase35-decision-rule-audit.md from the live rule registry."""
# ruff: noqa: E501

from pathlib import Path

from axis.decision import rules

EXTRA: dict[str, tuple[str, str, str]] = {
    # id: (condition, failure behaviour, covering tests)
    "DECISION-GAP-001": (
        "biochemical edge supported AND >=1 supported compound phenotype; status "
        "from the engagement edge (supported/contradicted -> resolved for current "
        "decision, mixed -> partially resolved, otherwise open)",
        "Not fired without both inputs; never infers engagement from phenotype.",
        "test_decision.py::test_uncertainty_missing_engagement_conflict_selectivity_context; "
        "acceptance::cf1, cf3, cf6",
    ),
    "DECISION-GAP-002": (
        "GAP-001 open AND no directly comparable selectivity comparison",
        "With comparable selectivity the uncertainty stays decision_material.",
        "acceptance::cf6, cf7, cf8",
    ),
    "DECISION-TRANS-001": (
        "biochemical edge supported AND no supported compound phenotype AND "
        "engagement not supported",
        "Not fired when any phenotype or engagement exists.",
        "acceptance::cf4",
    ),
    "DECISION-DEP-001": (
        "compound phenotype AND (genetic dependency supported OR compound "
        "dependency uncertain/not assessed)",
        "Resolved only by supported compound dependency with none uncertain.",
        "test_decision.py::test_resolved_gap_changes_status_and_critical; acceptance::cf1",
    ),
    "DECISION-SEL-001": (
        "compound phenotype exists; resolved only if >=1 comparable AND none "
        "unresolved",
        "Raw measurement counts never resolve it; 'Not assessed' and 'Not directly "
        "comparable' are reported separately.",
        "acceptance::cf7, cf8",
    ),
    "DECISION-CTX-001": (
        "contexts present; open if target allotype unreported in every experiment "
        "OR any experiment lacks the disease-relevant context",
        "Resolved only when allotype reported and no unmatched context.",
        "test_decision.py::test_uncertainty_missing_engagement_conflict_selectivity_context; "
        "acceptance::cf10",
    ),
    "DECISION-REPRO-001": (
        "genetic readouts with the same endpoint from >1 source with both "
        "increase and decrease",
        "Not fired for a single source or a single direction.",
        "test_decision.py::test_uncertainty_missing_engagement_conflict_selectivity_context; "
        "acceptance::cf10",
    ),
    "DECISION-BRIDGE-001": (
        "any functional assessment 'insufficient'",
        "Explanation 'indirect_pathway' is not admitted when absent.",
        "test_decision.py::test_explanation_without_grounds_is_rejected_and_excluded",
    ),
    "DECISION-BRIDGE-002": (
        "engagement supported AND no supported compound phenotype AND no "
        "functional insufficiency",
        "Not fired when a phenotype exists.",
        "acceptance::cf5",
    ),
    "DECISION-DIS-001": (
        "always emitted; informative while engagement/dependency/translation is "
        "open, otherwise decision_material; resolved if the disease edge is supported",
        "Disease relevance is never inferred from molecular phenotype.",
        "acceptance::cf10, layers test",
    ),
    "DECISION-CLIN-001": (
        "always emitted as not_actionable / peripheral",
        "Excluded from criticality by status and resolvability.",
        "test_decision.py::test_non_actionable_uncertainties_are_not_selectable",
    ),
    "DECISION-STRUCT-001": (
        "project has structural evidence",
        "Structure never creates an explanation link.",
        "acceptance::test_layers_are_not_collapsed_and_structure_never_supports",
    ),
    "DECISION-EXPL-001": (
        "link relationships only: contradicts+(supports|open) -> weakened; "
        "contradicts -> contradicted; supports(+open) -> partially_supported or "
        "supported; unresolved-only -> viable; context-only -> unresolved",
        "No links -> ValueError; the explanation is not admitted.",
        "test_decision.py::test_explanation_status_from_links; acceptance::cf3, cf7",
    ),
    "DECISION-EXPL-010": (
        "compound phenotype exists",
        "Not admitted without a compound phenotype.",
        "acceptance::cf2, cf4",
    ),
    "DECISION-EXPL-011": (
        "compound phenotype exists",
        "Comparable selectivity adds a contradicting link but never removes it.",
        "acceptance::cf3, cf7",
    ),
    "DECISION-EXPL-012": (
        "functional assessments 'insufficient'",
        "Not admitted without them.",
        "test_decision.py::test_explanation_without_grounds_is_rejected_and_excluded",
    ),
    "DECISION-EXPL-013": (
        "allotype unreported OR unmatched-context experiments OR source disagreement",
        "Not admitted when contexts are matched and sources agree.",
        "test_decision.py::test_context_limited_explanation; acceptance::cf10",
    ),
    "DECISION-CRIT-001": (
        "eligible = open/partially resolved AND testable; lexicographic over "
        "relevance, viable explanations affected, resolvability, candidate "
        "available, distinct next actions",
        "No eligible uncertainty -> selected null with an explicit message; exact "
        "ties reported in tied_with.",
        "test_decision.py::test_selection_*; acceptance::cf1, cf10, order tests",
    ),
    "DECISION-EXP-001": (
        "a scenario strengthens one viable explanation and weakens another",
        "No separated pair -> low_discrimination.",
        "test_decision.py::test_discrimination_unit",
    ),
    "DECISION-EXP-002": (
        "four criteria: >=3 interpretable scenarios, proximal endpoint, negative "
        "control, stated confounder",
        "No controls at all -> unknown.",
        "test_decision.py::test_interpretability_rule_levels",
    ),
    "DECISION-EXP-003": (
        "candidates considered for the critical uncertainty; blocked excluded; "
        "keys falsification, pairs, distinct actions, interpretability, "
        "proximity, prerequisites",
        "All blocked/none considered -> no recommendation with a reason; ties "
        "reported, identifier is display order only.",
        "acceptance::order tests, ties, function-of-inputs",
    ),
    "DECISION-EXP-004": (
        "EXP-001 yields no separated pair",
        "Role is labelled low discrimination, never mechanism discrimination.",
        "test_decision.py::test_replication_is_flagged_low_discrimination",
    ),
    "DECISION-EXP-005": (
        "an interpretable scenario weakens a currently preferred explanation",
        "Non-falsifying candidates rank after falsifying ones.",
        "acceptance::test_outcome_tree_text_is_conditional...",
    ),
}


def main() -> None:
    lines = [
        "# Phase 3.5A — decision rule audit",
        "",
        f"Rule set `{rules.RULES_VERSION}`, fingerprint `{rules.fingerprint()[:16]}`. "
        "Generated by `scripts/generate_rule_audit.py` from `axis.decision.rules.RULES`; "
        "every rule is a pure function in `axis/decision/rules.py` or "
        "`axis/decision/engine.py` (none lives only inside a service method). Purity "
        "(no clock, network, randomness, global state, no input mutation) and input-order "
        "independence are tested in "
        "`tests/test_decision_acceptance.py::test_rules_are_pure_and_deterministic_without_network` "
        "and `::test_input_order_never_changes_the_decision`.",
        "",
        f"{len(rules.RULES)} rules. `test_zz_every_rule_fired_in_at_least_one_scenario_in_this_module` "
        "fails if any rule is never exercised.",
        "",
    ]
    for rule_id, rule in rules.RULES.items():
        condition, failure, tests = EXTRA[rule_id]
        lines += [
            f"## {rule_id} (v{rule.version})",
            "",
            f"* **Description:** {rule.description}",
            f"* **Required inputs / evidence dependencies:** {rule.inputs}",
            f"* **Condition:** {condition}",
            f"* **Output:** {rule.output}",
            f"* **Rationale:** {rule.rationale}",
            f"* **Failure behaviour:** {failure}",
            f"* **Tests:** {tests}",
            "",
        ]
    Path("docs/phase35-decision-rule-audit.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
