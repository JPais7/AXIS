"""Pure retrospective-validation logic: no store, clock, network or randomness.

Everything here is categorical. There is no AXIS score, probability or ranking of
cases; each dimension is reported on its own.
"""

import re
from typing import Any

from axis.decision import engine, rules
from axis.decision.evidence import assemble_evidence
from axis.domain.validation import (
    INVALID_LABEL,
    LEAKAGE_CATEGORIES,
)
from axis.experiments import policy
from axis.validation import temporal

EDGES = (
    "exposure",
    "biochemical",
    "engagement",
    "functional",
    "hla",
    "immune",
    "disease",
    "clinical",
)
OVERSTATEMENT = re.compile(
    r"\b(proven|proves|prove[sd]?|cures?|clinically validated|guarantee[sd]?|"
    r"effective in patients|demonstrates efficacy)\b",
    re.IGNORECASE,
)
PREFERRED = rules.PREFERRED_STATUSES


def scrub_template(
    template: dict[str, Any], window: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Drop template references to records that are not in the window.

    The frozen decision template was authored after the fact and its candidate
    profiles name gap records by identifier; only identifiers present in the window
    may remain. Returns the scrubbed template and how many references were removed.
    """
    present = _ids(window)
    removed = 0
    candidates = []
    for candidate in template["candidates"]:
        profile = dict(candidate["profile"])
        kept = [g for g in profile.get("addressed_gap_ids", []) if g in present]
        removed += len(profile.get("addressed_gap_ids", [])) - len(kept)
        profile["addressed_gap_ids"] = kept
        candidates.append({**candidate, "profile": profile})
    return {**template, "candidates": candidates}, removed


def engine_inputs(
    template: dict[str, Any], records: dict[str, Any], mode: str
) -> engine.Inputs:
    """The same input contract the production service builds, minus the store."""
    candidates = [dict(c) for c in template["candidates"]]
    mappings = {
        f"{s['scenario_id']}|{e}": "pending"
        for c in candidates
        for s in c["scenarios"]
        for e in s["effects"]
    }
    return {
        "evidence": assemble_evidence(
            records, mode=mode, assessment_reviews={}, ledger=[]
        ),
        "review": {
            "mode": mode,
            "policy_id": policy.POLICY_ID,
            "mappings": mappings,
            "designs": {c["experiment_id"]: "pending" for c in candidates},
        },
        "results_ledger": [],
        "explanations": template["explanations"],
        "hypothesis": template["hypothesis"],
        "candidates": candidates,
        "constraints": None,
        "promoted": [],
        "statuses": {},
    }


def decide(
    template: dict[str, Any], records: dict[str, Any], mode: str
) -> dict[str, Any]:
    scrubbed, _ = scrub_template(template, records)
    return engine.analyze(engine_inputs(scrubbed, records, mode))


def summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """The decision as stated at one time point: small, categorical, comparable."""
    uncertainties = {
        u["id"]: {
            "category": u["category"],
            "status": u["status"],
            "relevance": u["decision_relevance"],
            "refs": sorted({str(r[1]) for r in u["evidence_refs"]}),
            "edges": sorted({str(r[1]) for r in u["evidence_refs"] if r[0] == "edge"}),
        }
        for u in analysis["uncertainties"]
    }
    recommendation = analysis.get("recommendation") or {}
    return {
        "edges": dict(analysis["effective_evidence"]["edges"]),
        "explanations": {e["id"]: e["status"] for e in analysis["explanations"]},
        "uncertainties": uncertainties,
        "critical_uncertainty_id": analysis["critical_uncertainty_id"],
        "recommended_experiment_id": analysis["recommended_experiment_id"],
        "recommendation_question": recommendation.get("question"),
        "no_experiment_message": analysis.get("no_experiment_message"),
        "supported_statements": [
            s["statement"] for s in analysis["position"]["supported"]
        ],
        "rule_ids": sorted(set(analysis["provenance"]["deterministic_rules"])),
    }


def state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Scientific T -> T+1 difference over two summaries (not a JSON diff)."""
    edges = {
        e: [
            before["edges"].get(e, "not_assessed"),
            after["edges"].get(e, "not_assessed"),
        ]
        for e in sorted(set(before["edges"]) | set(after["edges"]))
        if before["edges"].get(e) != after["edges"].get(e)
    }
    explanations = {
        e: [
            before["explanations"].get(e, "absent"),
            after["explanations"].get(e, "absent"),
        ]
        for e in sorted(set(before["explanations"]) | set(after["explanations"]))
        if before["explanations"].get(e) != after["explanations"].get(e)
    }
    uncertainties = {
        u: [
            before["uncertainties"].get(u, {}).get("status", "absent"),
            after["uncertainties"].get(u, {}).get("status", "absent"),
        ]
        for u in sorted(set(before["uncertainties"]) | set(after["uncertainties"]))
        if before["uncertainties"].get(u, {}).get("status")
        != after["uncertainties"].get(u, {}).get("status")
    }
    critical = [before["critical_uncertainty_id"], after["critical_uncertainty_id"]]
    recommended = [
        before["recommended_experiment_id"],
        after["recommended_experiment_id"],
    ]
    changed = bool(edges or explanations or uncertainties) or (
        critical[0] != critical[1] or recommended[0] != recommended[1]
    )
    return {
        "edges": edges,
        "explanations": explanations,
        "uncertainties": uncertainties,
        "critical_uncertainty": critical if critical[0] != critical[1] else None,
        "recommended_experiment": recommended
        if recommended[0] != recommended[1]
        else None,
        "decision_changed": (
            "yes"
            if critical[0] != critical[1] or recommended[0] != recommended[1]
            else "partially"
            if changed
            else "no"
        ),
        "rules_fingerprint": rules.fingerprint(),
    }


def subset_by_source(
    future: dict[str, Any], sources: dict[str, str], source: str
) -> dict[str, Any]:
    chosen = {k for k, v in sources.items() if v == source}
    out: dict[str, Any] = {}
    for key, value in future.items():
        if key == "structure_ids":
            out[key] = [s for s in value if f"structure_ids:{s}" in chosen]
        elif isinstance(value, list):
            out[key] = [r for r in value if f"{key}:{temporal.rid(r)}" in chosen]
        else:
            out[key] = value
    return out


def _ids(records: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for value in records.values():
        if isinstance(value, list):
            found |= {temporal.rid(r) for r in value}
    return found


def relevance_of_source(
    template: dict[str, Any],
    window: dict[str, Any],
    source_records: dict[str, Any],
    state_t: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """What does this one future source actually test? Incremental over the window."""
    own = _ids(source_records)
    after_all = decide(template, temporal.merge(window, source_records), mode)
    with_source = summary(after_all)
    status_changed: dict[str, list[str]] = {}
    refs_added: dict[str, int] = {}
    for uid, after in with_source["uncertainties"].items():
        before = state_t["uncertainties"].get(uid)
        if before is None or before["status"] != after["status"]:
            status_changed[uid] = [
                before["status"] if before else "absent",
                after["status"],
            ]
        added = len(set(after["refs"]) & own)
        if added:
            refs_added[uid] = added
    edge_changes = {
        e: [state_t["edges"].get(e, "not_assessed"), with_source["edges"].get(e)]
        for e in with_source["edges"]
        if state_t["edges"].get(e, "not_assessed") != with_source["edges"][e]
    }
    critical = state_t["critical_uncertainty_id"]
    has_assessment = (
        bool(source_records.get("assessments"))
        or bool(source_records.get("biochemical_measurements"))
        or bool(source_records.get("selectivity"))
    )
    open_before = {
        u for u, v in state_t["uncertainties"].items() if v["status"] == "open"
    }
    unassessed = {"not_assessed", "not_applicable"}
    if critical and critical in status_changed:
        verdict = "changes_critical_uncertainty"
    elif status_changed:
        verdict = "changes_other_uncertainty"
    elif set(refs_added) & open_before:
        verdict = "adds_evidence_to_open_uncertainty"
    elif any(a in unassessed for a, _ in edge_changes.values()):
        verdict = "addresses_unassessed_edge"
    elif edge_changes:
        verdict = "adds_to_assessed_edge"
    elif not has_assessment:
        verdict = "non_interpretable"
    else:
        verdict = "does_not_test_decision_question"
    return {
        "relevance": verdict,
        "status_changes": status_changed,
        "evidence_added_to": refs_added,
        "touched_uncertainties": sorted(set(status_changed) | set(refs_added)),
        "edge_changes": edge_changes,
        "critical_selection_with_source": with_source["critical_uncertainty_id"],
        "records": len(own),
        "explanation_changes": state_diff(state_t, with_source)["explanations"],
    }


def conclusion_of(
    state_t: dict[str, Any],
    state_t1: dict[str, Any],
    relevance: dict[str, dict[str, Any]],
    leakage_valid: bool,
) -> dict[str, Any]:
    """Categorical conclusion; may be ambiguous, 'did not test' or invalid."""
    if not leakage_valid:
        return {
            "conclusion": "invalid_due_to_leakage",
            "label": INVALID_LABEL,
            "basis": [],
        }
    verdicts = {v["relevance"] for v in relevance.values()}
    listing = [f"{k}: {v['relevance']}" for k, v in sorted(relevance.items())]
    if not relevance or verdicts <= {"non_interpretable"}:
        return {
            "conclusion": "not_interpretable",
            "basis": ["future evidence could not be interpreted by the rules"],
        }
    if "changes_critical_uncertainty" not in verdicts:
        return {
            "conclusion": "future_evidence_did_not_test_the_decision",
            "basis": [
                "the critical uncertainty stated at the cutoff did not change status",
                *listing,
            ],
        }
    present = set(state_t["explanations"])
    preferred = {e for e in present if state_t["explanations"][e] in PREFERRED}
    moves = {
        e: (state_t["explanations"][e], state_t1["explanations"].get(e, "absent"))
        for e in present
        if state_t["explanations"][e] != state_t1["explanations"].get(e, "absent")
    }
    # Direction is judged on the explanations AXIS preferred at the cutoff and on
    # the evidence edges the critical uncertainty rests on; movement of the other
    # explanations is reported in the basis but does not set the verdict.
    downgraded = [
        e for e, (a, b) in moves.items() if e in preferred and _rank(b) < _rank(a)
    ]
    upgraded = [
        e for e, (a, b) in moves.items() if e in preferred and _rank(b) > _rank(a)
    ]
    critical = state_t["critical_uncertainty_id"]
    edges = state_t["uncertainties"].get(critical, {}).get("edges", [])
    edge_moves = {
        e: (state_t["edges"].get(e, "not_assessed"), state_t1["edges"].get(e))
        for e in edges
        if state_t["edges"].get(e, "not_assessed") != state_t1["edges"].get(e)
    }
    after = {b for _, b in edge_moves.values()}
    edge_dir = (
        "mixed"
        if "mixed" in after or {"supported", "contradicted"} <= after
        else "contradicting"
        if "contradicted" in after
        else "supportive"
        if "supported" in after
        else "none"
    )
    basis = [f"explanation {e}: {a} -> {b}" for e, (a, b) in sorted(moves.items())]
    basis += [f"edge {e}: {a} -> {b}" for e, (a, b) in sorted(edge_moves.items())]
    basis += listing
    if preferred and all(
        state_t1["explanations"].get(e) == "contradicted" for e in preferred
    ):
        name = "contradicted_by_future_evidence"
    elif downgraded and not upgraded or edge_dir == "contradicting" and not upgraded:
        name = "weakened_by_future_evidence"
    elif (upgraded or edge_dir == "supportive") and not downgraded:
        name = "supported_by_future_evidence"
    else:
        name = "ambiguous"
    return {"conclusion": name, "basis": basis}


def _rank(status: str | None) -> int:
    order = {"contradicted": 0, "viable": 1, "partially_supported": 2, "supported": 3}
    return order.get(status or "", -1)


# --- decision validity, calibration, claims ---------------------------------


def decision_validity(
    analysis: dict[str, Any], window: dict[str, Any]
) -> dict[str, Any]:
    """Structural checks: every cited record is in the window; nothing orphaned."""
    window_ids = _ids(window)
    record_refs = {
        "id",
        "gap",
        "readout",
        "cellular_assessment",
        "selectivity_assessment",
    }
    cited: set[str] = set()
    for u in analysis["uncertainties"]:
        cited |= {str(r[1]) for r in u["evidence_refs"] if r[0] in record_refs}
    for e in analysis["explanations"]:
        cited |= {
            str(link["evidence_id"])
            for link in e["links"]
            if link["evidence_type"] in record_refs
        }
    outside = sorted(c for c in cited if c not in window_ids)
    return {
        "result": "valid" if not outside else "invalid",
        "cited_outside_window": outside,
        "explanations_without_links": [
            e["id"] for e in analysis["explanations"] if not e["links"]
        ],
    }


def uncertainty_calibration(
    state_t: dict[str, Any],
    state_t1: dict[str, Any],
    relevance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tested = {u for v in relevance.values() for u in v["touched_uncertainties"]}
    open_t = {u for u, v in state_t["uncertainties"].items() if v["status"] == "open"}
    new_after = sorted(set(state_t1["uncertainties"]) - set(state_t["uncertainties"]))
    if not tested:
        verdict = "not_tested"
    elif tested <= open_t and not new_after:
        verdict = "anticipated"
    elif tested & open_t:
        verdict = "partially_anticipated"
    else:
        verdict = "not_anticipated"
    return {
        "result": verdict,
        "tested_uncertainties": sorted(tested),
        "open_at_cutoff_and_tested": sorted(tested & open_t),
        "tested_but_not_open_at_cutoff": sorted(tested - open_t),
        "new_uncertainties_after_reveal": new_after,
    }


def recommendation_relevance(
    state_t: dict[str, Any], relevance: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    critical = state_t["critical_uncertainty_id"]
    if not critical:
        return {"result": "no_recommendation_made", "critical": None}
    hit = sorted(
        k
        for k, v in relevance.items()
        if v["relevance"] == "changes_critical_uncertainty"
    )
    other = sorted(
        k
        for k, v in relevance.items()
        if v["relevance"]
        in {"changes_other_uncertainty", "adds_evidence_to_open_uncertainty"}
    )
    result = (
        "future_tested_the_critical_question"
        if hit
        else "future_added_evidence_on_other_open_questions"
        if other
        else "future_did_not_test_the_question"
    )
    return {
        "result": result,
        "critical": critical,
        "sources_testing_it": hit,
        "sources_adding_to_others": other,
        "recommended_experiment": state_t["recommended_experiment_id"],
    }


def overstated_claims(analysis: dict[str, Any]) -> dict[str, Any]:
    text = temporal.canonical(
        {
            "position": analysis["position"],
            "recommendation": analysis.get("recommendation"),
            "rationale": analysis["rationale"],
        }
    )
    hits = sorted({m.group(0).lower() for m in OVERSTATEMENT.finditer(text)})
    clinical = analysis["effective_evidence"]["edges"].get("clinical", "not_assessed")
    problems = hits + (["clinical edge asserted"] if clinical == "supported" else [])
    return {
        "result": "none_detected" if not problems else "overstatement_detected",
        "findings": problems,
    }


# --- baselines ----------------------------------------------------------------


def naive_baseline(window: dict[str, Any]) -> dict[str, Any]:
    """Transparent baseline: the edge with the least evidence is the next question.

    Counts informative cellular assessments per edge; ties break by the fixed
    edge order. It uses no rule, uncertainty model or explanation.
    """
    counts = {e: 0 for e in EDGES}
    informative = {"supported", "contradicted", "insufficient", "mixed"}
    for a in window.get("assessments", []):
        if a["edge"] in counts and a["state"] in informative:
            counts[a["edge"]] += 1
    counts["biochemical"] += len(window.get("biochemical_measurements", []))
    asked = sorted(EDGES, key=lambda e: (counts[e], EDGES.index(e)))[0]
    return {
        "baseline": "least-evidence-edge",
        "recommended_edge": asked,
        "evidence_counts": counts,
        "supported_edges": [e for e in EDGES if counts[e] > 0],
    }


def compare_to_baseline(
    state_t: dict[str, Any],
    baseline: dict[str, Any],
    relevance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Did each approach point at what the future evidence actually changed?

    Coarse, explicitly limited yardstick: the edges whose state the future changed
    and the uncertainties whose status it changed.
    """
    changed_edges = sorted({e for v in relevance.values() for e in v["edge_changes"]})
    changed_unc = {u for v in relevance.values() for u in v["status_changes"]}
    critical = state_t["critical_uncertainty_id"]
    critical_edges = (
        set(state_t["uncertainties"][critical]["edges"]) if critical else set()
    )
    axis_hit = bool(critical in changed_unc or critical_edges & set(changed_edges))
    base_edge = baseline.get("recommended_edge")
    base_hit = base_edge in changed_edges
    if not relevance:
        verdict = "indeterminate"
    elif axis_hit and not base_hit:
        verdict = "axis_pointed_at_what_changed_baseline_did_not"
    elif base_hit and not axis_hit:
        verdict = "baseline_pointed_at_what_changed_axis_did_not"
    elif axis_hit and base_hit:
        verdict = "both_pointed_at_what_changed"
    else:
        verdict = "neither_pointed_at_what_changed"
    return {
        "result": verdict,
        "axis_critical_uncertainty": critical,
        "baseline_edge": base_edge,
        "edges_changed_by_future": changed_edges,
        "note": "single case, coarse yardstick; says nothing about general value",
    }


# --- leakage audit ------------------------------------------------------------


def leakage_audit(
    *,
    availability: dict[str, Any],
    cutoff: temporal.TemporalCutoff,
    window_file: dict[str, Any],
    future_ids: set[str],
    future_sources: set[str],
    template: dict[str, Any],
    forbidden_tokens: dict[str, list[str]],
    outputs: list[Any],
    checksums_ok: dict[str, bool],
    future_opened_before_reveal: bool,
    baseline_frozen_before_reveal: bool,
) -> dict[str, Any]:
    """Fail closed: any finding makes the case INVALID."""
    findings: list[dict[str, str]] = []
    window = window_file["records"]
    sources = window_file["record_sources"]
    for record in temporal.record_ids(window):
        source = sources.get(record)
        ok, reason = (
            temporal.source_eligibility(availability, source, cutoff)
            if source
            else (False, "source_not_in_availability_table")
        )
        if not ok:
            findings.append(
                {"category": reason, "subject": record, "detail": source or ""}
            )
    for record in temporal.record_ids(window):
        if record in future_ids:
            findings.append(
                {"category": "future_record_in_window", "subject": record, "detail": ""}
            )
    text_template = temporal.canonical(template)
    future_text_targets = [("template", text_template)] + [
        (f"output[{i}]", temporal.canonical(o)) for i, o in enumerate(outputs)
    ]
    for source in sorted(future_sources):
        tokens = {source, source.split(":")[-1], *forbidden_tokens.get(source, [])}
        for where, text in future_text_targets:
            for token in sorted(t for t in tokens if t):
                if token in text:
                    category = (
                        "template_names_future_source"
                        if where == "template"
                        else "output_names_future_source"
                    )
                    findings.append(
                        {
                            "category": category,
                            "subject": where,
                            "detail": f"{source}: {token}",
                        }
                    )
    for where, text in future_text_targets:
        category = (
            "template_names_future_source"
            if where == "template"
            else "output_names_future_source"
        )
        for rid in sorted(future_ids):
            kind, _, tail = rid.partition(":")
            if kind != "structure_ids" and tail and tail in text:
                findings.append({"category": category, "subject": where, "detail": rid})
    for name, ok in sorted(checksums_ok.items()):
        if not ok:
            findings.append({"category": name, "subject": name, "detail": "mismatch"})
    if future_opened_before_reveal:
        findings.append(
            {
                "category": "future_file_opened_before_reveal",
                "subject": "future",
                "detail": "",
            }
        )
    if not baseline_frozen_before_reveal:
        findings.append(
            {
                "category": "baseline_not_frozen_before_reveal",
                "subject": "baseline",
                "detail": "",
            }
        )
    unknown = sorted({f["category"] for f in findings} - set(LEAKAGE_CATEGORIES))
    if unknown:
        raise ValueError(f"unregistered leakage category {unknown}")
    # de-duplicate stable
    seen = set()
    unique = []
    for f in findings:
        key = (f["category"], f["subject"], f["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return {
        "valid": not unique,
        "label": None if not unique else INVALID_LABEL,
        "findings": unique,
        "checked": {
            "window_records": len(temporal.record_ids(window)),
            "future_records": len(future_ids),
            "future_sources": sorted(future_sources),
            "cutoff": cutoff.date.isoformat(),
        },
    }


# --- leave-one-source-out -----------------------------------------------------


def leave_one_source_out(
    template: dict[str, Any],
    window: dict[str, Any],
    sources: dict[str, str],
    state_t: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    """Which window source does the decision at T depend on? (categorical)"""
    out = []
    for source in sorted(set(sources.values())):
        keep = {k for k, v in sources.items() if v != source}
        reduced: dict[str, Any] = {}
        for key, value in window.items():
            if key == "structure_ids":
                reduced[key] = [s for s in value if f"structure_ids:{s}" in keep]
            elif isinstance(value, list):
                reduced[key] = [r for r in value if f"{key}:{temporal.rid(r)}" in keep]
            else:
                reduced[key] = value
        if reduced == window:
            continue
        diff = state_diff(state_t, summary(decide(template, reduced, mode)))
        out.append(
            {
                "removed_source": source,
                "decision_changed": diff["decision_changed"],
                "critical_uncertainty": diff["critical_uncertainty"],
                "recommended_experiment": diff["recommended_experiment"],
                "explanation_changes": diff["explanations"],
            }
        )
    return out
