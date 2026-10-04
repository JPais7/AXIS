"""Pure decision analysis: explicit inputs in, a decision analysis out.

``analyze`` reads no store, clock, network or randomness and never mutates its
input, so counterfactual states, ordering tests and sensitivity analysis can reuse
exactly the code path that produces a persisted ``DecisionState``.
"""

import copy
import json
from dataclasses import replace
from typing import Any

from axis.decision import rules

Inputs = dict[str, Any]
Analysis = dict[str, Any]
WEAKENING = {
    "weaken_current_strategy",
    "deprioritize_current_strategy",
    "change_mechanistic_model",
    "stop_for_now",
}
STRENGTHENING = {"strengthen_current_strategy", "advance_to_next_evidence_layer"}
NO_EXPERIMENT = (
    "No next discriminating experiment is currently justified by the represented "
    "evidence and rules."
)
REVIEW_MESSAGE = (
    "This recommendation depends on evidence that has not yet received independent "
    "scientific acceptance."
)


EDGE_LABELS = {
    "exposure": "Cellular exposure",
    "biochemical": "Biochemical activity",
    "engagement": "Direct cellular target engagement",
    "functional": "Functional target modulation",
    "hla": "HLA / antigen-presentation molecular phenotype",
    "immune": "Immune phenotype",
    "disease": "Disease phenotype",
    "clinical": "Clinical effect",
}


def label(value: str) -> str:
    return value.replace("_", " ")


def _named(text: str, names: dict[str, str]) -> str:
    for identifier, name in names.items():
        text = text.replace(identifier, name)
    return text


def feasibility(
    profile: dict[str, Any], constraints: dict[str, Any] | None
) -> dict[str, Any]:
    if constraints is None:
        return {
            "level": "unknown",
            "missing": [],
            "note": "Feasibility not assessed against local resource constraints.",
        }
    if profile["experiment_id"] in constraints.get("excluded_experiment_ids", []):
        return {
            "level": "blocked",
            "missing": [],
            "note": "Investigator constraints exclude this experiment.",
        }
    pool = {
        "models": constraints["available_models"],
        "reagents": constraints["available_compounds"],
        "assays": constraints["available_assays"],
    }
    equipment = {v.casefold() for v in constraints["available_equipment"]}
    missing = [
        item
        for kind, items in sorted(profile["required"].items())
        for item in items
        if item.casefold() not in {v.casefold() for v in pool.get(kind, [])}
        and item.casefold() not in equipment
    ]
    if not missing:
        return {"level": "feasible_with_current_resources", "missing": [], "note": ""}
    covered = [
        m
        for m in missing
        if any(
            m.casefold() in c.casefold() or c.casefold() in m.casefold()
            for c in constraints["external_collaborations"]
        )
    ]
    level = (
        "external_collaboration"
        if len(covered) == len(missing)
        else "requires_new_capability"
    )
    return {
        "level": level,
        "missing": missing,
        "note": "Compared with investigator-entered resources.",
    }


def _explanations(
    inputs: Inputs,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    ev = inputs["evidence"]
    promoted = set(inputs.get("promoted", []))
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for definition in sorted(inputs["explanations"], key=lambda d: d["id"]):
        links = rules.explanation_links(ev, definition["ground"], definition["id"])
        if not links:
            excluded.append(
                {
                    "id": definition["id"],
                    "reason": "no grounded evidence link in the current evidence "
                    "state; not admitted to the DecisionState",
                }
            )
            continue
        rows.append(
            {
                "id": definition["id"],
                "label": definition["label"],
                "statement": definition["statement"],
                "ground": definition["ground"],
                "knowledge_kind": "researcher_hypothesis"
                if definition["id"] in promoted
                else definition["knowledge_kind"],
                "status": rules.explanation_status(links),
                "links": [
                    {
                        "relationship": link.relationship,
                        "evidence_type": link.evidence_type,
                        "evidence_id": link.evidence_id,
                        "rule_id": link.rule_id,
                        "rationale": link.rationale,
                    }
                    for link in sorted(
                        links,
                        key=lambda k: (k.relationship, k.evidence_type, k.evidence_id),
                    )
                ],
                "rule_ids": [
                    rules.GROUND_RULES[definition["ground"]],
                    "DECISION-EXPL-001",
                ],
            }
        )
    return rows, excluded


def _candidate(
    raw: dict[str, Any],
    viable: set[str],
    statuses: dict[str, str],
    constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    scenarios = sorted(raw["scenarios"], key=lambda s: s["scenario_id"])
    interpretations = {
        s["scenario_id"]: {e: v["effect"] for e, v in s["effects"].items()}
        for s in scenarios
    }
    kinds = {s["scenario_id"]: s["kind"] for s in scenarios}
    categories = sorted({s["consequence"]["category"] for s in scenarios})
    profile = raw["profile"]
    return {
        "experiment_id": raw["experiment_id"],
        "title": raw["title"],
        "profile": profile,
        "status": raw.get("status", "proposed"),
        "result_claim_id": raw.get("result_claim_id"),
        "epistemic_kind": raw.get("knowledge_kind", "ai_suggestion"),
        "discrimination": rules.discrimination(interpretations, viable),
        "falsification": rules.falsification(interpretations, kinds, statuses),
        "interpretability": rules.interpretability(profile, list(kinds.values())),
        "distinct_consequences": len(categories),
        "consequence_categories": categories,
        "feasibility": feasibility(profile, constraints),
        "cost": profile.get("cost") or "not provided",
    }


def _position(
    ev: rules.Evidence, uncertainties: list[Any]
) -> dict[str, list[dict[str, Any]]]:
    supported, contradicted, unresolved = [], [], []
    for edge, value in sorted(ev["edges"].items()):
        row = {
            "edge": edge,
            "statement": f"{EDGE_LABELS.get(edge, label(edge).capitalize())} is "
            f"{label(value['state'])}.",
            "refs": [["edge", edge], *[["id", i] for i in sorted(value["ids"])[:6]]],
            "epistemic_kind": "axis_inference",
        }
        if value["state"] == "supported":
            supported.append(row)
        elif value["state"] in ("contradicted", "mixed"):
            contradicted.append(row)
    for edge, scopes in sorted(ev.get("scoped_edges", {}).items()):
        for key, entry in sorted(scopes.items()):
            row = {
                "statement": f"{EDGE_LABELS.get(edge, label(edge))} for {key}: "
                f"{label(entry['state'])} (experimental result"
                + (", replicated" if entry.get("replicated") else "")
                + ").",
                "edge": edge,
                "scope": key,
                "refs": [["interpretation", i] for i in entry["contribution_ids"]],
                "epistemic_kind": "experimental_result",
                "review_states": sorted(set(entry["review_states"])),
                "caveats": entry["caveats"] + entry["review_caveats"],
            }
            if entry["state"] == "supported":
                supported.append(row)
            elif entry["state"] in ("contradicted", "mixed"):
                contradicted.append(row)
    for item in ev.get("source_disagreements", []):
        contradicted.append(
            {
                "statement": "Sources disagree on the direction of "
                f"{item['endpoint']} after perturbation "
                f"({' vs '.join(sorted(item['directions']))}).",
                "refs": [["readout", i] for i in sorted(item["readout_ids"])],
                "epistemic_kind": "axis_inference",
            }
        )
    for u in uncertainties:
        if u.status in ("open", "partially_resolved"):
            unresolved.append(
                {
                    "statement": u.question,
                    "refs": [
                        ["uncertainty", u.id],
                        *[list(r) for r in u.evidence_refs[:4]],
                    ],
                    "epistemic_kind": "axis_inference",
                }
            )
    return {
        "supported": supported,
        "contradicted": contradicted,
        "unresolved": unresolved,
    }


def _change_mind(
    hypothesis_id: str,
    recommended_id: str | None,
    raws: list[dict[str, Any]],
) -> dict[str, Any]:
    weaken, strengthen = [], []
    for raw in sorted(
        raws, key=lambda r: (r["experiment_id"] != recommended_id, r["experiment_id"])
    ):
        for s in sorted(raw["scenarios"], key=lambda s: s["scenario_id"]):
            cons = s["consequence"]
            row = {
                "hypothesis_id": hypothesis_id,
                "experiment_id": raw["experiment_id"],
                "scenario_id": s["scenario_id"],
                "category": cons["category"],
                "statement": cons["statement"],
                "explanation_effects": [
                    {"explanation_id": e, "effect": v["effect"]}
                    for e, v in sorted(s["effects"].items())
                    if v["effect"] != "does_not_discriminate"
                ],
                "prospective": True,
                "epistemic_kind": "ai_suggestion",
            }
            if cons["category"] in WEAKENING:
                weaken.append(row)
            elif cons["category"] in STRENGTHENING:
                strengthen.append(row)
    return {
        "question": "What result would make us reconsider the current strategy?",
        "would_weaken": weaken,
        "would_strengthen": strengthen,
        "label": "prospective / hypothetical — no result has been observed",
    }


def _recommendation(
    selected: Any,
    recommended: dict[str, Any] | None,
    raws: dict[str, dict[str, Any]],
    critical: dict[str, Any],
) -> dict[str, Any] | None:
    if selected is None or recommended is None:
        return None
    raw = raws[recommended["experiment_id"]]
    profile = recommended["profile"]
    scenarios = [
        {
            "scenario_id": s["scenario_id"],
            "kind": s["kind"],
            "outcome": s["outcome"],
            "interpretation": s["interpretation"],
            "explanation_effects": [
                {
                    "explanation_id": e,
                    "effect": v["effect"],
                    "rationale": v["rationale"],
                }
                for e, v in sorted(s["effects"].items())
            ],
            "consequence": s["consequence"],
            "prospective": True,
            "epistemic_kind": "ai_suggestion",
        }
        for s in sorted(raw["scenarios"], key=lambda s: s["scenario_id"])
    ]
    return {
        "heading": "Recommended next discriminating experiment",
        "conditional_on": "current evidence, current rules and current constraints",
        "question": selected.question,
        "why_now": f"{label(selected.category)} is the "
        f"{label(selected.decision_relevance)} uncertainty: "
        + "; ".join(critical["reasons"][:1] + list(selected.reasons)),
        "experiment_id": raw["experiment_id"],
        "title": raw["title"],
        "experiment": raw["intervention_description"],
        "biological_context": raw["experimental_system"],
        "controls": {
            "negative": profile["controls_negative"],
            "positive": profile["controls_positive"]
            or ["No validated positive control identified in the curated corpus."],
        },
        "primary_endpoint": profile["primary_endpoint"],
        "secondary_endpoints": profile["secondary_endpoints"],
        "outcome_scenarios": scenarios,
        "limitations": profile["limitations"],
        "knowledge_kind": raw["knowledge_kind"],
        "status": recommended["status"],
        "tied_with": recommended["tied_with"],
        "why_this_experiment": {
            "uncertainty": selected.question,
            "explanations_separated": [
                list(pair) for pair in recommended["discrimination"]["separated_pairs"]
            ],
            "falsifying_scenarios": recommended["falsification"]["weakening_scenarios"],
            "why_current_evidence_cannot_answer": "; ".join(selected.reasons),
            "why_outcome_changes_decision": " ".join(
                s["consequence"]["statement"] for s in scenarios[:3]
            ),
            "remains_unresolved": profile["limitations"],
        },
    }


def _graph(a: Analysis, inputs: Inputs) -> dict[str, Any]:
    hyp = inputs["hypothesis"]
    nodes: list[dict[str, str]] = [
        {"id": hyp["id"], "type": "Hypothesis", "label": hyp["title"]}
    ]
    edges: list[dict[str, str]] = []
    seen = {hyp["id"]}

    def node(identifier: str, kind: str, text: str) -> None:
        if identifier not in seen:
            seen.add(identifier)
            nodes.append({"id": identifier, "type": kind, "label": text})

    for e in a["explanations"]:
        node(e["id"], "CompetingExplanation", e["label"])
        edges.append(
            {
                "from": e["id"],
                "to": hyp["id"],
                "kind": "competes_for",
                "basis": "Alternative explanation of the same evidence.",
            }
        )
    for u in a["uncertainties"]:
        node(u["id"], "ScientificUncertainty", u["question"])
        for gap in u["source_gap_ids"]:
            node(gap, "EvidenceGap", gap)
            edges.append(
                {
                    "from": gap,
                    "to": u["id"],
                    "kind": "informs",
                    "basis": "Cellular evidence gap behind this uncertainty.",
                }
            )
        for expl in u["affected_explanation_ids"]:
            edges.append(
                {
                    "from": u["id"],
                    "to": expl,
                    "kind": "affects",
                    "basis": "Rule " + ", ".join(u["fired_rules"]),
                }
            )
    for c in a["candidates"]:
        node(c["experiment_id"], "Experiment", c["title"])
        for gap in c["profile"]["addressed_gap_ids"]:
            node(gap, "EvidenceGap", gap)
            edges.append(
                {
                    "from": gap,
                    "to": c["experiment_id"],
                    "kind": "addressed_by",
                    "basis": "Candidate experiment is linked to this gap.",
                }
            )
        for pair in c["discrimination"]["separated_pairs"]:
            for expl in pair:
                edges.append(
                    {
                        "from": c["experiment_id"],
                        "to": expl,
                        "kind": "discriminates",
                        "basis": "Outcomes move this explanation opposite to "
                        "another viable one.",
                    }
                )
    return {"nodes": nodes, "edges": edges}


def canonicalize(value: Any) -> Any:
    """Sort every set-like list so that input order can never matter."""
    if isinstance(value, dict):
        return {k: canonicalize(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted(
            (canonicalize(v) for v in value),
            key=lambda v: json.dumps(v, sort_keys=True, default=str),
        )
    return value


def _allowed(state: str, mode: str) -> bool:
    """DECISION-REVIEW-001: which review states may inform a decision in this mode."""
    if state in ("accepted", "accepted_with_caveat"):
        return True
    return state == "pending" and mode == "exploratory"


def _review_filter(
    inputs: Inputs,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    """Apply the review policy to candidate designs and scenario mappings."""
    review = inputs.get("review") or {}
    mode = review.get("mode", "exploratory")
    mappings = review.get("mappings", {})
    designs = review.get("designs", {})
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    pending_mappings = 0
    pending_designs = 0
    for raw in sorted(inputs["candidates"], key=lambda r: r["experiment_id"]):
        design = designs.get(raw["experiment_id"], "pending")
        if not _allowed(design, mode):
            excluded.append(
                {
                    "object": raw["experiment_id"],
                    "type": "candidate_design",
                    "state": design,
                }
            )
            continue
        pending_designs += design == "pending"
        copy_ = copy.deepcopy(raw)
        for scenario in copy_["scenarios"]:
            for explanation, effect in list(scenario["effects"].items()):
                key = f"{scenario['scenario_id']}|{explanation}"
                state = mappings.get(key, "pending")
                if effect["effect"] == "does_not_discriminate":
                    continue
                if not _allowed(state, mode):
                    excluded.append(
                        {"object": key, "type": "scenario_mapping", "state": state}
                    )
                    scenario["effects"][explanation] = {
                        "effect": "does_not_discriminate",
                        "rationale": f"mapping excluded by review policy ({state})",
                    }
                else:
                    pending_mappings += state == "pending"
        kept.append(copy_)
    return (
        kept,
        excluded,
        {
            "mode": mode,
            "policy_id": review.get("policy_id", "decision-review-policy-v1"),
            "pending_mappings_used": pending_mappings,
            "pending_designs_used": pending_designs,
        },
    )


def analyze(inputs: Inputs, *, with_sensitivity: bool = True) -> Analysis:
    """Derive the full decision analysis from explicit inputs (pure)."""
    raw_inputs = {**inputs, "evidence": canonicalize(inputs["evidence"])}
    ev = rules.apply_contributions(raw_inputs["evidence"])
    inputs = {**raw_inputs, "evidence": ev}
    constraints = inputs.get("constraints")
    kept, review_excluded, review_dependencies = _review_filter(inputs)
    raws = {r["experiment_id"]: r for r in kept}
    rows, excluded = _explanations(inputs)
    viable = {e["id"] for e in rows if e["status"] != "contradicted"}
    statuses = {e["id"]: e["status"] for e in rows}
    by_ground = {e["ground"]: e["id"] for e in rows}
    uncertainties = [
        replace(
            u,
            affected_explanation_ids=tuple(
                sorted(by_ground[g] for g in u.affected_grounds if g in by_ground)
            ),
        )
        for u in rules.derive_uncertainties(ev)
    ]
    candidates = [
        _candidate(raws[k], viable, statuses, constraints) for k in sorted(raws)
    ]
    info: dict[str, dict[str, int]] = {}
    categories = {c for cand in candidates for c in cand["profile"]["considered_for"]}
    for category in sorted(categories):
        considered = [
            c for c in candidates if category in c["profile"]["considered_for"]
        ]
        info[category] = {
            "count": len(considered),
            "consequences": len(
                {x for c in considered for x in c["consequence_categories"]}
            ),
        }
    critical = rules.select_critical(uncertainties, viable, info)
    names = {e["id"]: e["label"] for e in rows}
    critical["reasons"] = [_named(r, names) for r in critical["reasons"]]
    selected = next((u for u in uncertainties if u.id == critical["selected"]), None)
    ranked: list[dict[str, Any]] = []
    if selected is not None:
        ranked = rules.rank_candidates(
            [
                c
                for c in candidates
                if selected.category in c["profile"]["considered_for"]
            ]
        )
    recommended = next(
        (
            c
            for c in ranked
            if c["excluded"] is None and not c["discrimination"]["low_discrimination"]
        ),
        None,
    )
    considered_ids = {c["experiment_id"] for c in ranked}
    for place, item in enumerate(ranked, start=1):
        item["rank"] = place
        if item["excluded"]:
            item["reason"] = item["excluded"]
        elif item is recommended:
            item["reason"] = (
                "recommended: "
                + "; ".join(
                    [
                        f"separates {len(item['discrimination']['separated_pairs'])} "
                        "pair(s) of viable explanations",
                        "able to weaken a preferred explanation"
                        if item["falsification"]["falsifying"]
                        else "cannot weaken any preferred explanation",
                        f"{item['distinct_consequences']} distinct next actions "
                        "across outcomes",
                        f"interpretability {item['interpretability']['level']}",
                        f"{label(item['profile']['target_proximity'])} endpoint",
                    ]
                )
                + (
                    "; tied on every scientific criterion with "
                    + ", ".join(item["tied_with"])
                    + " (identifier order is a display convention only)"
                    if item["tied_with"]
                    else ""
                )
            )
        elif recommended is None:
            item["reason"] = (
                "not recommended: separates no pair of viable explanations under the "
                "accepted outcome mappings (low discrimination)"
            )
        else:
            deciding = next(
                (
                    i
                    for i, (x, y) in enumerate(
                        zip(recommended["rank_key"], item["rank_key"], strict=True)
                    )
                    if x != y
                ),
                None,
            )
            item["reason"] = (
                "not recommended: tied with the recommended experiment on every "
                "scientific criterion; identifier order is a display convention only"
                if deciding is None
                else "not recommended: lower on " + rules.CANDIDATE_CRITERIA[deciding]
            ) + (
                "; separates no pair of explanations (low discrimination)"
                if item["discrimination"]["low_discrimination"]
                else ""
            )
            if item["tied_with"] and deciding is not None:
                item["reason"] += (
                    "; tied on every scientific criterion with "
                    + ", ".join(item["tied_with"])
                    + " (identifier order is a display convention only)"
                )
    for item in candidates:
        if item["experiment_id"] not in considered_ids:
            item["rank"] = None
            item["tied_with"] = []
            item["reason"] = (
                "not compared: considered for "
                + ", ".join(label(c) for c in item["profile"]["considered_for"])
                + ", not for the critical uncertainty"
                if selected is not None
                else "not compared: no critical uncertainty is currently selected"
            )
        item["low_discrimination"] = item["discrimination"]["low_discrimination"]
        item.pop("rank_key", None)
        item["role_label"] = (
            "low discrimination — "
            + label(item["profile"]["role"]).replace(
                "mechanism discrimination", "not mechanism discrimination"
            )
            if item["low_discrimination"]
            else label(item["profile"]["role"])
        )
    candidates.sort(key=lambda c: c["experiment_id"])
    recommendation = _recommendation(selected, recommended, raws, critical)
    uncertainty_rows: list[dict[str, Any]] = [
        {
            "id": u.id,
            "category": u.category,
            "question": u.question,
            "status": u.status,
            "decision_relevance": u.decision_relevance,
            "resolvability": u.resolvability,
            "rationale": u.rationale,
            "fired_rules": list(u.fired_rules),
            "reasons": list(u.reasons),
            "source_gap_ids": list(u.source_gap_ids),
            "affected_explanation_ids": list(u.affected_explanation_ids),
            "evidence_refs": [list(r) for r in u.evidence_refs],
            "epistemic_kind": u.epistemic_kind,
            "scope_type": u.scope_type,
            "scope_id": u.scope_id,
            "scope_breakdown": [list(b) for b in u.scope_breakdown],
        }
        for u in sorted(uncertainties, key=lambda u: u.id)
    ]
    fired = sorted(
        {r for u in uncertainty_rows for r in u["fired_rules"]}
        | {r for e in rows for r in e["rule_ids"]}
        | {
            "DECISION-CRIT-001",
            "DECISION-EXP-001",
            "DECISION-EXP-002",
            "DECISION-EXP-003",
            "DECISION-EXP-004",
            "DECISION-EXP-005",
        }
    )
    promoted = set(inputs.get("promoted", []))
    statuses_in = inputs.get("statuses", {})
    review = ev.get("review", {"pending_expert_review": 0, "accepted": 0})
    analysis: Analysis = {
        "position": _position(ev, uncertainties),
        "explanations": rows,
        "excluded_explanations": excluded,
        "uncertainties": uncertainty_rows,
        "critical": critical,
        "critical_uncertainty_id": critical["selected"],
        "candidates": candidates,
        "recommended_experiment_id": recommended["experiment_id"]
        if recommended
        else None,
        "recommendation": recommendation,
        "no_experiment_message": None
        if recommendation
        else NO_EXPERIMENT
        if selected is None
        else "A critical uncertainty exists but no unblocked candidate experiment "
        "with accepted discriminating outcome mappings is available for it.",
        "what_would_change_our_mind": _change_mind(
            inputs["hypothesis"]["id"],
            recommended["experiment_id"] if recommended else None,
            list(raws.values()),
        ),
        "constraints": {
            "id": constraints["id"] if constraints else None,
            "note": None
            if constraints
            else "Feasibility not assessed against local resource constraints.",
        },
        "review": {
            "pending_expert_review": review.get("pending_expert_review", 0),
            "accepted": review.get("accepted", 0),
            "message": REVIEW_MESSAGE
            if review.get("pending_expert_review", 0)
            else None,
        },
        "provenance": {
            "ai_generated": sorted(
                [e["id"] for e in rows if e["knowledge_kind"] == "ai_suggestion"]
                + [c["experiment_id"] for c in candidates]
            ),
            "investigator_approved": sorted(
                promoted | {k for k, v in statuses_in.items() if v != "proposed"}
            ),
            "deterministic_rules": fired,
        },
        "rationale": f"Critical uncertainty: {label(selected.category)}."
        if selected
        else "No open, testable uncertainty remains in the current evidence state.",
    }
    analysis["trace"] = {
        "evidence_considered": {
            "edges": {k: v["state"] for k, v in sorted(ev["edges"].items())},
            "selectivity": ev.get("selectivity"),
            "concordance": ev.get("concordance"),
            "compound_coverage": ev.get("compound_coverage"),
        },
        "rules_fired": [
            {
                "id": r,
                "version": rules.RULES[r].version,
                "description": rules.RULES[r].description,
            }
            for r in fired
        ],
        "uncertainties_generated": [
            {
                "id": u["id"],
                "status": u["status"],
                "relevance": u["decision_relevance"],
                "rules": u["fired_rules"],
            }
            for u in uncertainty_rows
        ],
        "explanations_affected": {
            u["id"]: u["affected_explanation_ids"] for u in uncertainty_rows
        },
        "explanations_not_admitted": excluded,
        "candidates_considered": [
            {
                "experiment_id": c["experiment_id"],
                "rank": c["rank"],
                "reason": c["reason"],
                "low_discrimination": c["low_discrimination"],
                "falsifying": c["falsification"]["falsifying"],
            }
            for c in candidates
        ],
        "critical_selection": critical,
        "outcome_logic": "Experiment -> OutcomeScenario -> OutcomeInterpretation "
        "-> CompetingExplanation -> DecisionConsequence (all prospective).",
        "ranked_for_critical": [c["experiment_id"] for c in ranked],
    }
    analysis["graph"] = _graph(analysis, inputs)
    analysis["effective_evidence"] = {
        "edges": {k: v["state"] for k, v in sorted(ev["edges"].items())},
        "scoped_edges": ev.get("scoped_edges", {}),
        "engagement_rollup": ev.get("engagement_rollup"),
        "gap_ids": ev.get("gap_ids", []),
    }
    analysis["review_mode"] = inputs.get("review", {}).get("mode", "exploratory")
    analysis["review_dependencies"] = review_dependencies | {
        "pending_contributions": sorted(
            c["id"]
            for c in ev.get("contributions", [])
            if c["review_state"] == "pending"
        ),
        "review_excluded": review_excluded,
    }
    analysis["results"] = {
        "contributions": ev.get("contributions", []),
        "ledger": inputs.get("results_ledger", []),
        "unexpected": ev.get("unexpected_results", []),
        "synthetic": any(c.get("synthetic") for c in ev.get("contributions", []))
        or any(x.get("synthetic") for x in inputs.get("results_ledger", [])),
    }
    if with_sensitivity:
        analysis["sensitivity"] = sensitivity(raw_inputs, analysis)
    return analysis


def _outcome(a: Analysis) -> dict[str, Any]:
    return {
        "critical": a["critical_uncertainty_id"],
        "recommended": a["recommended_experiment_id"],
        "explanations": {e["id"]: e["status"] for e in a["explanations"]},
        "uncertainties": {
            u["id"]: (u["status"], u["decision_relevance"]) for u in a["uncertainties"]
        },
    }


def _blank(ev: rules.Evidence, *keys: str) -> None:
    for key in keys:
        ev[key] = []


def _edges_off(ev: rules.Evidence, *edges: str) -> None:
    for edge in edges:
        if edge in ev["edges"]:
            ev["edges"][edge] = {"state": "not_assessed", "ids": []}


def _remove_biochemical(e: rules.Evidence) -> None:
    _blank(e, "biochemical_ids")
    _edges_off(e, "biochemical")


def _remove_compound_phenotype(e: rules.Evidence) -> None:
    _blank(
        e,
        "compound_phenotype_ids",
        "compound_dependency_uncertain_ids",
        "compound_dependency_supported_ids",
    )
    _edges_off(e, "hla", "immune")


def _remove_selectivity(e: rules.Evidence) -> None:
    e["selectivity"] = {
        "total": 0,
        "comparable": 0,
        "unresolved_ids": [],
        "comparable_ids": [],
    }


def _remove_comparable_selectivity(e: rules.Evidence) -> None:
    if e.get("selectivity"):
        e["selectivity"].update(comparable=0, comparable_ids=[])


def _remove_pending_review(e: rules.Evidence) -> None:
    _blank(
        e,
        "compound_phenotype_ids",
        "genetic_phenotype_ids",
        "genetic_dependency_ids",
        "compound_dependency_uncertain_ids",
        "compound_dependency_supported_ids",
        "functional_insufficient_ids",
        "gap_ids",
    )
    e["source_disagreements"] = []
    _edges_off(e, "hla", "immune", "engagement", "functional", "exposure")


def ablations(ev: rules.Evidence) -> list[tuple[str, str, rules.Evidence]]:
    """Evidence groups removed one at a time: (key, description, mutated copy)."""
    groups: list[tuple[str, str, Any]] = [
        ("biochemical", "all biochemical activity evidence", _remove_biochemical),
        (
            "compound_phenotype",
            "all compound-treated cellular phenotype evidence",
            _remove_compound_phenotype,
        ),
        (
            "genetic_dependency",
            "genetic-perturbation dependency evidence",
            lambda e: _blank(e, "genetic_dependency_ids"),
        ),
        (
            "engagement",
            "direct engagement evidence",
            lambda e: _edges_off(e, "engagement"),
        ),
        ("selectivity", "all selectivity assessments", _remove_selectivity),
        (
            "comparable_selectivity",
            "the comparable selectivity assessments",
            _remove_comparable_selectivity,
        ),
        (
            "source_disagreement",
            "the cross-source disagreement",
            lambda e: e.update(source_disagreements=[]),
        ),
        (
            "functional",
            "the functional-modulation insufficiency",
            lambda e: _blank(e, "functional_insufficient_ids"),
        ),
        ("gaps", "the recorded evidence gaps", lambda e: _blank(e, "gap_ids")),
        ("structure", "structural evidence", lambda e: _blank(e, "structure_ids")),
        (
            "pending_review_cellular",
            "all cellular assessments pending expert review",
            _remove_pending_review,
        ),
    ]
    for result_id in sorted({c["result_id"] for c in ev.get("contributions", [])}):
        groups.append(
            (
                f"result:{result_id}",
                f"the experimental result {result_id}",
                lambda e, rid=result_id: e.update(
                    contributions=[
                        c for c in e["contributions"] if c["result_id"] != rid
                    ]
                ),
            )
        )
    groups.append(
        (
            "results_pending_review",
            "all experimental-result contributions still pending review",
            lambda e: e.update(
                contributions=[
                    c
                    for c in e.get("contributions", [])
                    if c["review_state"] != "pending"
                ]
            ),
        )
    )
    out: list[tuple[str, str, rules.Evidence]] = []
    for key, text, mutate in groups:
        mutated = copy.deepcopy(ev)
        mutate(mutated)
        if mutated != ev:
            out.append((key, text, mutated))
    return out


def sensitivity(inputs: Inputs, base: Analysis) -> dict[str, Any]:
    """Categorical leave-group-out analysis: which evidence changes the decision?"""
    reference = _outcome(base)
    decisive, explanation_only, non_decisive = [], [], []
    for key, text, mutated in ablations(inputs["evidence"]):
        variant = analyze({**inputs, "evidence": mutated}, with_sensitivity=False)
        outcome = _outcome(variant)
        changes: list[str] = []
        if outcome["critical"] != reference["critical"]:
            changes.append(
                f"critical uncertainty: {reference['critical']} → {outcome['critical']}"
            )
        if outcome["recommended"] != reference["recommended"]:
            changes.append(
                f"recommended experiment: {reference['recommended']} → "
                f"{outcome['recommended']}"
            )
        for expl in sorted(
            set(reference["explanations"]) | set(outcome["explanations"])
        ):
            before = reference["explanations"].get(expl, "not admitted")
            after = outcome["explanations"].get(expl, "not admitted")
            if before != after:
                changes.append(f"explanation {expl}: {label(before)} → {label(after)}")
        row = {"group": key, "removed": text, "changes": changes}
        if outcome["critical"] != reference["critical"] or (
            outcome["recommended"] != reference["recommended"]
        ):
            decisive.append(row)
        elif changes:
            explanation_only.append(row)
        else:
            non_decisive.append(row)
    return {
        "method": "categorical leave-group-out; no probabilities",
        "decision_sensitive": decisive,
        "explanation_sensitive": explanation_only,
        "non_decisive": non_decisive,
    }
