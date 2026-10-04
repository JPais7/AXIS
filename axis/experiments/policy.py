"""Pure, versioned result rules: review state, eligibility and scenario matching.

No store, clock, network or randomness. The decision engine consumes only the
*outcome* of these functions (eligible contributions); it never parses result files.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

POLICY_ID = "decision-review-policy-v1"
MATCH_RULE_VERSION = "axis-scenario-match-1"
RESULT_RULES_VERSION = "axis-results-1"
MODES = ("exploratory", "reviewed")
ACCEPTING = ("accepted", "accepted_with_caveat")


@dataclass(frozen=True)
class ResultRule:
    id: str
    description: str
    rationale: str


RESULT_RULES: dict[str, ResultRule] = {
    r.id: r
    for r in (
        ResultRule(
            "RESULT-QC-001",
            "A technical failure, non-interpretable result or non-interpretable QC "
            "assessment is ineligible for biological inference.",
            "A failed control is not a biological negative.",
        ),
        ResultRule(
            "RESULT-REV-001",
            "A rejected result or interpretation is excluded; a review conflict or "
            "needs-revision state is excluded in every mode.",
            "Disagreement is never resolved silently.",
        ),
        ResultRule(
            "RESULT-REV-002",
            "Pending review is eligible only in exploratory mode and is labelled; "
            "reviewed mode requires accepted or accepted-with-caveat.",
            "Pending science must not look accepted.",
        ),
        ResultRule(
            "RESULT-EDGE-001",
            "An interpretation may update only an evidence edge that the performed "
            "experiment declares it measures.",
            "No edge promotion through adjacency; no automatic cascade.",
        ),
        ResultRule(
            "RESULT-CTX-001",
            "A contribution keeps its scope (compound, perturbagen, target) and its "
            "context; it never silently generalizes.",
            "Compound 3 evidence is not Compound 2 evidence.",
        ),
        ResultRule(
            "RESULT-SUP-001",
            "A superseded or withdrawn result is not eligible for the current "
            "decision.",
            "History is preserved; the current decision uses the current record.",
        ),
        ResultRule(
            "RESULT-DEV-001",
            "A design deviation that limits interpretation makes the contribution "
            "eligible only with a caveat; one that invalidates comparison makes it "
            "ineligible for that comparison.",
            "A modified experiment is not the original design.",
        ),
    )
}


def policy_fingerprint() -> str:
    material = {
        "policy": POLICY_ID,
        "match": MATCH_RULE_VERSION,
        "rules": {
            k: [r.description, r.rationale] for k, r in sorted(RESULT_RULES.items())
        },
        "modes": {
            "reviewed": "accepted and accepted_with_caveat only",
            "exploratory": "accepted, accepted_with_caveat and pending (labelled)",
        },
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def review_state(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the current state from append-only reviews.

    Each reviewer's latest non-pending decision counts. Accept and reject together
    are a *conflict*; there is no majority rule.
    """
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=lambda r: (r["reviewed_at"], r["id"])):
        if review["decision"] == "pending":
            latest.pop(review["reviewer"], None)
            continue
        latest[review["reviewer"]] = review
    decisions = {r["decision"] for r in latest.values()}
    caveats = [r["caveat"] for r in latest.values() if r.get("caveat")]
    reviewers = sorted(latest)
    if not decisions:
        state = "pending"
    elif decisions & {"rejected"} and decisions & set(ACCEPTING):
        state = "conflict"
    elif "rejected" in decisions:
        state = "rejected"
    elif "needs_revision" in decisions:
        state = "needs_revision"
    elif "accepted_with_caveat" in decisions:
        state = "accepted_with_caveat"
    else:
        state = "accepted"
    return {"state": state, "reviewers": reviewers, "caveats": caveats}


def contribution_eligibility(
    *,
    result: dict[str, Any],
    qc: dict[str, Any] | None,
    interpretation: dict[str, Any],
    experiment: dict[str, Any],
    result_review: dict[str, Any],
    interpretation_review: dict[str, Any],
    superseded: bool,
    withdrawn: bool,
    deviations: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    """Decide whether one interpretation may inform a DecisionState (policy v1)."""
    if mode not in MODES:
        raise ValueError(f"unknown review mode {mode!r}")
    review_caveats = result_review["caveats"] + interpretation_review["caveats"]
    caveats: list[str] = list(interpretation.get("caveats", [])) + review_caveats
    reasons: list[str] = []

    def out(state: str, rule: str, why: str) -> dict[str, Any]:
        return {
            "state": state,
            "eligible": False,
            "rule": rule,
            "reasons": [why],
            "caveats": caveats,
            "review_caveats": review_caveats,
            "review_state": interpretation_review["state"],
        }

    if withdrawn:
        return out("withdrawn", "RESULT-SUP-001", "the result was withdrawn")
    if superseded:
        return out(
            "superseded", "RESULT-SUP-001", "a newer version of the result exists"
        )
    if result["result_type"] in ("technical_failure", "non_interpretable") or (
        qc is not None and qc["assessment"] == "non_interpretable"
    ):
        return out(
            "ineligible_qc_failure",
            "RESULT-QC-001",
            "quality control does not allow biological inference",
        )
    if interpretation["edge"] not in experiment["measures_edges"]:
        return out(
            "ineligible_edge_not_measured",
            "RESULT-EDGE-001",
            "the experiment does not declare that it measures "
            f"{interpretation['edge']!r}",
        )
    for deviation in deviations:
        if deviation["interpretation_relevance"] == "invalidates_comparison":
            return out(
                "ineligible_design_deviation",
                "RESULT-DEV-001",
                f"deviation in {deviation['field']} invalidates the comparison",
            )
        if deviation["interpretation_relevance"] == "limits_interpretation":
            caveats.append(
                f"design deviation: {deviation['field']} "
                f"({deviation['proposed_value']} → {deviation['actual_value']})"
            )
    if qc is not None and qc["assessment"] == "interpretable_with_caveat":
        caveats.append("quality control: interpretable with caveat")
    if result_review["state"] == "rejected":
        return out("rejected", "RESULT-REV-001", "the result itself was rejected")
    if interpretation_review["state"] == "rejected":
        return out("rejected", "RESULT-REV-001", "the interpretation was rejected")
    for label, review in (
        ("result", result_review),
        ("interpretation", interpretation_review),
    ):
        if review["state"] == "conflict":
            return out(
                "review_conflict",
                "RESULT-REV-001",
                f"reviewers disagree on the {label}",
            )
        if review["state"] == "needs_revision":
            return out(
                "needs_revision", "RESULT-REV-001", f"the {label} needs revision"
            )
    if (
        interpretation_review["state"] in ACCEPTING
        and result_review["state"] in ACCEPTING
    ):
        return {
            "state": "eligible_with_caveat" if caveats else "eligible",
            "eligible": True,
            "rule": "RESULT-REV-002",
            "reasons": ["accepted by explicit reviewer action"],
            "caveats": caveats,
            "review_caveats": review_caveats,
            "review_state": interpretation_review["state"],
        }
    reasons.append("scientific review is pending")
    if mode == "exploratory":
        return {
            "state": "pending_review",
            "eligible": True,
            "rule": "RESULT-REV-002",
            "reasons": reasons + ["used only because the decision mode is exploratory"],
            "caveats": caveats + ["pending scientific review"],
            "review_caveats": review_caveats + ["pending scientific review"],
            "review_state": interpretation_review["state"],
        }
    return out(
        "pending_review",
        "RESULT-REV-002",
        "reviewed mode requires accepted or accepted-with-caveat",
    )


def match_scenarios(
    observed: dict[str, str],
    signatures: dict[str, dict[str, str]],
    *,
    non_interpretable: bool,
) -> dict[str, Any]:
    """Compare observed categorical facets with each anticipated scenario signature.

    No probabilities. A real result is never forced into a scenario.
    """
    per: list[dict[str, Any]] = []
    for scenario, signature in sorted(signatures.items()):
        matched = sorted(k for k, v in signature.items() if observed.get(k) == v)
        conflicting = sorted(
            k for k, v in signature.items() if k in observed and observed[k] != v
        )
        unobserved = sorted(k for k in signature if k not in observed)
        if matched and not conflicting and not unobserved:
            relation = "matches"
        elif matched:
            relation = "partially_matches"
        elif conflicting:
            relation = "contradicts"
        else:
            relation = "ambiguous"
        per.append(
            {
                "scenario_id": scenario,
                "relationship": relation,
                "matched": matched,
                "conflicting": conflicting,
                "unobserved": unobserved,
            }
        )
    if non_interpretable:
        overall = "non_interpretable"
    elif any(p["relationship"] == "matches" for p in per):
        overall = "matches"
    elif any(p["relationship"] == "partially_matches" for p in per):
        overall = "partially_matches"
    elif not observed or not per:
        overall = "ambiguous"
    elif all(p["relationship"] in ("contradicts", "ambiguous") for p in per):
        overall = "outside_predefined_scenarios"
    else:
        overall = "ambiguous"
    return {"overall": overall, "per_scenario": per, "rule_version": MATCH_RULE_VERSION}
