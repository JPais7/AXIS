"""Versioned, transparent decision rules over a plain evidence-state mapping.

Every function is pure: explicit inputs, deterministic output, no clock, network,
randomness or global state, and inputs are never mutated. There are no numeric
scores, probabilities or information-gain figures; ordering is lexicographic over
documented categorical criteria and every comparison reports the criterion that
decided it. Ties are reported as ties, never broken silently by insertion order.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from axis.domain.decision import ExplanationEvidenceLink, ScientificUncertainty

RULES_VERSION = "axis-decision-3"
Evidence = dict[str, Any]
Ref = tuple[str, str]
TARGET = "the target"


@dataclass(frozen=True)
class Rule:
    id: str
    version: str
    description: str
    inputs: str
    output: str
    rationale: str


def _rule(*values: str) -> tuple[str, Rule]:
    return values[0], Rule(values[0], "1", *values[1:])


RULES: dict[str, Rule] = dict(
    [
        _rule(
            "DECISION-GAP-001",
            "Engagement uncertainty when biochemical activity and a compound "
            "phenotype are supported but direct cellular engagement is not.",
            "edges.biochemical, edges.engagement, compound_phenotype_ids",
            "target_engagement uncertainty (decision_material)",
            "A phenotype is not engagement; the bridge is unobserved, not refuted.",
        ),
        _rule(
            "DECISION-GAP-002",
            "Raise engagement to decision_blocking while selectivity is unresolved, "
            "because an off-target explanation then cannot be excluded.",
            "selectivity.comparable, uncertainty target_engagement",
            "target_engagement decision_blocking",
            "Without engagement or comparable selectivity the compound phenotype "
            "cannot be attributed to the target and the strategy decision cannot "
            "be taken.",
        ),
        _rule(
            "DECISION-TRANS-001",
            "Assay-translation uncertainty when biochemical activity is supported "
            "and no cellular phenotype or engagement is supported.",
            "edges.biochemical, edges.engagement, compound_phenotype_ids",
            "assay_translation uncertainty (decision_blocking)",
            "Biochemical activity alone says nothing about activity in cells.",
        ),
        _rule(
            "DECISION-DEP-001",
            "Dependency uncertainty when genetic dependency is supported but "
            "compound dependency is uncertain or not assessed.",
            "genetic_dependency_ids, compound_dependency_uncertain_ids",
            "target_dependency uncertainty (decision_material)",
            "Genetic dependency does not transfer to a compound without a matched "
            "chemical-genetic comparison.",
        ),
        _rule(
            "DECISION-SEL-001",
            "Selectivity uncertainty when no selectivity comparison is directly "
            "comparable; quantity of incompatible data never counts as resolution.",
            "selectivity",
            "selectivity uncertainty (decision_material, indirectly_testable)",
            "A cellular experiment alone cannot resolve selectivity; it needs a "
            "comparable biochemical panel.",
        ),
        _rule(
            "DECISION-CTX-001",
            "Genetic-context uncertainty when the target allotype/genotype is "
            "unreported in every experiment or an experiment lacks the "
            "disease-relevant context.",
            "contexts",
            "genetic_context uncertainty (decision_material)",
            "Target biology is context sensitive; contexts are not interchangeable.",
        ),
        _rule(
            "DECISION-REPRO-001",
            "Reproducibility uncertainty when sources report opposite directions "
            "for the same genetic endpoint.",
            "source_disagreements",
            "reproducibility uncertainty (decision_material)",
            "Opposite directions in distinct systems are source disagreement, not "
            "noise to average away.",
        ),
        _rule(
            "DECISION-BRIDGE-001",
            "Mechanistic-bridge uncertainty when proximal functional modulation is "
            "insufficiently shown.",
            "functional_insufficient_ids",
            "mechanistic_bridge uncertainty (decision_material)",
            "Downstream phenotype alone does not show proximal modulation.",
        ),
        _rule(
            "DECISION-BRIDGE-002",
            "Mechanistic-bridge uncertainty when engagement is supported but no "
            "relevant cellular phenotype is supported.",
            "edges.engagement, compound_phenotype_ids, edges.hla, edges.immune",
            "mechanistic_bridge uncertainty (decision_material)",
            "Engagement without phenotype is a distinct state from phenotype "
            "without engagement.",
        ),
        _rule(
            "DECISION-DIS-001",
            "Disease-relevance uncertainty; informative while engagement or "
            "dependency is open, material once both are resolved.",
            "edges.disease, uncertainties",
            "disease_relevance uncertainty",
            "Disease relevance is downstream of target dependency.",
        ),
        _rule(
            "DECISION-CLIN-001",
            "Clinical translation is recorded but not actionable at this layer.",
            "edges.clinical",
            "clinical_translation uncertainty (peripheral, not_actionable)",
            "No clinical or patient recommendation is in scope.",
        ),
        _rule(
            "DECISION-STRUCT-001",
            "Structural evidence informs design but cannot resolve engagement or "
            "dependency.",
            "structure_ids",
            "structural_mechanism uncertainty (peripheral, not_actionable)",
            "A mapped structure is not cellular engagement or therapeutic mechanism.",
        ),
        _rule(
            "DECISION-EXPL-001",
            "Explanation status from its evidence links only (no probabilities).",
            "explanation links",
            "supported | partially_supported | viable | weakened | contradicted "
            "| unresolved",
            "Status is a categorical reading of link relationships.",
        ),
        _rule(
            "DECISION-EXPL-010",
            "Ground on_target: the compound phenotype arises from direct target "
            "modulation.",
            "compound phenotype, biochemical, engagement, selectivity",
            "evidence links",
            "Admitted only when a compound phenotype exists.",
        ),
        _rule(
            "DECISION-EXPL-011",
            "Ground off_target: the phenotype arises from off-target activity.",
            "selectivity, engagement, concordance",
            "evidence links",
            "Admitted whenever a compound phenotype exists; comparable selectivity "
            "weakens but does not eliminate it.",
        ),
        _rule(
            "DECISION-EXPL-012",
            "Ground indirect_pathway: the target is perturbed but the phenotype is "
            "indirect.",
            "functional_insufficient_ids",
            "evidence links",
            "Admitted while proximal functional modulation is insufficient.",
        ),
        _rule(
            "DECISION-EXPL-013",
            "Ground context_dependent: the effect depends on genetic or disease "
            "context.",
            "contexts, source_disagreements",
            "evidence links",
            "Admitted when contexts are unmatched or sources disagree.",
        ),
        _rule(
            "DECISION-CRIT-001",
            "Critical uncertainty: lexicographic over relevance, explanations "
            "separated, resolvability, candidate availability and distinct next "
            "actions; unresolved and testable only; ties are reported.",
            "uncertainties, explanations, candidates",
            "one critical uncertainty with per-criterion reasons, or none",
            "Deterministic and explainable; no opaque score.",
        ),
        _rule(
            "DECISION-EXP-001",
            "Discrimination: pairs of viable explanations moved in opposite "
            "directions by at least one scenario.",
            "outcome interpretations",
            "separated pair list; low_discrimination flag",
            "An experiment is discriminating only if explanations predict "
            "different outcomes.",
        ),
        _rule(
            "DECISION-EXP-002",
            "Interpretability high/moderate/low/unknown from four documented criteria.",
            "profile, scenarios",
            "interpretability level",
            "Criteria: >=3 interpretable scenarios; direct/proximal endpoint; a "
            "negative control; a stated confounder addressed.",
        ),
        _rule(
            "DECISION-EXP-003",
            "Recommended next discriminating experiment among those considered "
            "for the critical uncertainty: exclude blocked; then falsifying, "
            "separated pairs, distinct next actions, interpretability, proximity "
            "and fewer unestablished prerequisites; ties are reported.",
            "candidate analyses",
            "recommended experiment with reasons; alternatives with reasons",
            "Complexity and cost are reported but never preferred automatically.",
        ),
        _rule(
            "DECISION-EXP-004",
            "Label experiments that separate no pair as low discrimination and "
            "give them a non-mechanistic role.",
            "discrimination",
            "low_discrimination flag",
            "Replication or precision gain must not be presented as mechanism "
            "discrimination.",
        ),
        _rule(
            "DECISION-EXP-005",
            "Falsification: an experiment is falsifying only if some "
            "interpretable scenario weakens a currently preferred explanation.",
            "outcome interpretations, explanation statuses",
            "falsifying flag; non-falsifying candidates rank after falsifying ones",
            "AXIS should favour experiments able to change its mind.",
        ),
        _rule(
            "DECISION-RESULT-001",
            "Apply eligible experimental-result contributions to their own evidence "
            "edge and scope only; never cascade to another edge or generalize to "
            "another scope or context.",
            "contributions (eligible under the review policy)",
            "scoped edge states; project edge aggregate",
            "Each edge requires its own evidence; a result is bound to its scope.",
        ),
        _rule(
            "DECISION-RESULT-002",
            "Roll engagement up over the phenotype-producing scopes: complete only "
            "when every required scope is decided; otherwise partial or open.",
            "required scopes, scoped engagement states",
            "engagement rollup and uncertainty status",
            "Target-level resolution is distinct from compound-level resolution.",
        ),
        _rule(
            "DECISION-RESULT-003",
            "A result outside every predefined scenario creates an unexpected-result "
            "uncertainty instead of being force-fitted.",
            "unexpected_results",
            "uncertainty:unexpected_result:<id>",
            "Unexpected data are preserved and need interpretation.",
        ),
        _rule(
            "DECISION-REPRO-002",
            "Opposite eligible results for the same edge and scope yield a mixed "
            "scope state and a reproducibility uncertainty; both are preserved.",
            "scoped edges",
            "reproducibility uncertainty",
            "Contradiction is data; results are never averaged into consensus.",
        ),
        _rule(
            "DECISION-REVIEW-001",
            "Scenario→explanation mappings and candidate designs enter a decision "
            "only if their review state is allowed by the review mode; rejected, "
            "conflicting and needs-revision are always excluded.",
            "review states, review mode",
            "filtered mappings and candidate set; review dependencies",
            "A rejected mapping must not silently stay active.",
        ),
    ]
)


def fingerprint() -> str:
    """Identify the methodology: rule ids, versions and texts plus the rules version.

    Changes when the decision rules change, independently of any evidence.
    """
    material = {
        "version": RULES_VERSION,
        "rules": {
            key: [r.version, r.description, r.inputs, r.output, r.rationale]
            for key, r in sorted(RULES.items())
        },
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


RELEVANCE_RANK = {
    "decision_blocking": 0,
    "decision_material": 1,
    "informative": 2,
    "peripheral": 3,
}
RESOLVABILITY_RANK = {
    "directly_testable": 0,
    "indirectly_testable": 1,
    "requires_multiple_experiments": 2,
    "unknown": 3,
    "currently_not_testable": 4,
}
INTERPRETABILITY_RANK = {"high": 0, "moderate": 1, "low": 2, "unknown": 3}
PROXIMITY_RANK = {
    "direct_target": 0,
    "target_proximal": 1,
    "pathway_proximal": 2,
    "downstream": 3,
    "disease_phenotype": 4,
}
EFFECT_SIGN = {
    "strengthens": 1,
    "resolves_for_current_decision": 1,
    "weakens": -1,
    "contradicts": -1,
    "does_not_discriminate": 0,
}
PREFERRED_STATUSES = {"supported", "partially_supported"}


def _edge(ev: Evidence, name: str) -> str:
    return str(ev["edges"].get(name, {}).get("state", "not_assessed"))


def _ids(ev: Evidence, key: str) -> list[str]:
    return list(ev.get(key, []))


def _target(ev: Evidence) -> str:
    return str(ev.get("target_label") or TARGET)


def has_compound_phenotype(ev: Evidence) -> bool:
    return bool(_ids(ev, "compound_phenotype_ids"))


def selectivity_unresolved(ev: Evidence) -> bool:
    selectivity = ev.get("selectivity", {"total": 0, "comparable": 0})
    return bool(selectivity["comparable"] == 0)


def off_target_viable(ev: Evidence) -> bool:
    """Off-target explanation can be excluded neither by selectivity nor engagement."""
    return has_compound_phenotype(ev) and (
        selectivity_unresolved(ev) or _edge(ev, "engagement") != "supported"
    )


def _refs(*groups: tuple[str, list[str]]) -> tuple[Ref, ...]:
    return tuple((kind, value) for kind, values in groups for value in sorted(values))


def _selectivity_breakdown(selectivity: dict[str, Any]) -> list[str]:
    """Keep 'not assessed' and 'not directly comparable' distinct (Phase 3.3)."""
    by_status = selectivity.get("by_status") or {}
    return [
        f"{count} {status.lower()}"
        for status, count in sorted(by_status.items())
        if status != "Comparable" and count
    ]


def _coverage_reason(ev: Evidence) -> list[str]:
    coverage = ev.get("compound_coverage")
    if not coverage:
        return []
    reasons = []
    rows = coverage.get("compounds", [])
    both = [c for c in rows if c["biochemical"] and c["cellular_phenotype"]]
    if rows:
        reasons.append(
            f"{len(both)} of {len(rows)} compounds have both biochemical activity "
            "and a cellular phenotype; evidence is not pooled across compounds"
        )
    if coverage.get("unresolved_identity_perturbagens"):
        reasons.append(
            f"{len(coverage['unresolved_identity_perturbagens'])} phenotype-producing "
            "perturbagen(s) have unresolved chemical identity and cannot be linked "
            "to any compound's biochemical data"
        )
    return reasons


def _aggregate_states(states: list[str]) -> str:
    unique = set(states)
    if "mixed" in unique or {"supported", "contradicted"} <= unique:
        return "mixed"
    for state in ("contradicted", "supported", "insufficient"):
        if state in unique:
            return state
    return "not_assessed"


def apply_contributions(ev: Evidence) -> Evidence:
    """DECISION-RESULT-001/002: fold eligible result contributions into the evidence.

    Pure. Each contribution touches only its own edge and scope; an engagement
    result never changes functional, HLA, immune or disease edges, and a result for
    one compound never decides another compound's scope.
    """
    out: Evidence = json.loads(json.dumps(ev))
    contributions = out.get("contributions", [])
    scoped: dict[str, dict[str, dict[str, Any]]] = {}
    for item in sorted(
        contributions,
        key=lambda c: (c["edge"], c["scope_type"], c["scope_id"], c["id"]),
    ):
        key = f"{item['scope_type']}:{item['scope_id']}"
        entry = scoped.setdefault(item["edge"], {}).setdefault(
            key,
            {
                "states": [],
                "contribution_ids": [],
                "caveats": [],
                "review_caveats": [],
                "experiments": [],
                "review_states": [],
                "contexts": [],
            },
        )
        entry["states"].append(item["state"])
        entry["contribution_ids"].append(item["id"])
        entry["caveats"] += [
            c for c in item.get("caveats", []) if c not in entry["caveats"]
        ]
        entry["review_caveats"] += [
            c
            for c in item.get("review_caveats", [])
            if c not in entry["review_caveats"]
        ]
        if item["experiment_id"] not in entry["experiments"]:
            entry["experiments"].append(item["experiment_id"])
        entry["review_states"].append(item["review_state"])
        entry["contexts"].append(item.get("context", {}))
    for scopes in scoped.values():
        for entry in scopes.values():
            entry["state"] = _aggregate_states(entry.pop("states"))
            entry["replicated"] = len(entry["experiments"]) >= 2 and entry["state"] in (
                "supported",
                "contradicted",
            )
    out["scoped_edges"] = scoped
    for edge, scopes in scoped.items():
        if edge == "engagement":
            continue
        base = out["edges"].get(edge, {"state": "not_assessed", "ids": []})
        merged = (
            _aggregate_states([base["state"]] + [e["state"] for e in scopes.values()])
            if base["state"] != "insufficient"
            else _aggregate_states([e["state"] for e in scopes.values()])
        )
        out["edges"][edge] = {
            "state": merged,
            "ids": sorted(
                set(base["ids"])
                | {i for e in scopes.values() for i in e["contribution_ids"]}
            ),
        }
    if "engagement" in scoped:
        required = [
            f"{s['scope_type']}:{s['scope_id']}" for s in out.get("required_scopes", [])
        ]
        engaged = scoped["engagement"]
        rows = []
        for key in sorted(set(required) | set(engaged)):
            scope_type, _, scope_id = key.partition(":")
            found = engaged.get(key)
            rows.append(
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "state": found["state"] if found else "not_assessed",
                    "required": key in required,
                    "contribution_ids": found["contribution_ids"] if found else [],
                    "caveats": found["caveats"] if found else [],
                    "review_caveats": found["review_caveats"] if found else [],
                    "replicated": bool(found and found["replicated"]),
                }
            )
        needed = [r for r in rows if r["required"]]
        decided = [
            r for r in needed if r["state"] in ("supported", "contradicted", "mixed")
        ]
        mixed = any(r["state"] == "mixed" for r in needed)
        if needed and len(decided) == len(needed) and not mixed:
            status = "complete"
        elif decided or mixed:
            status = "partial"
        else:
            status = "open"
        out["engagement_rollup"] = {"status": status, "scopes": rows}
        states = {r["state"] for r in needed}
        if status == "complete" and states == {"supported"}:
            project_state = "supported"
        elif status == "complete" and states == {"contradicted"}:
            project_state = "contradicted"
        elif mixed or {"supported", "contradicted"} <= states or status == "complete":
            project_state = "mixed"
        elif status == "partial":
            project_state = "incomplete"
        else:
            project_state = out["edges"]["engagement"]["state"]
        out["edges"]["engagement"] = {
            "state": project_state,
            "ids": sorted(
                set(out["edges"]["engagement"]["ids"])
                | {i for r in rows for i in r["contribution_ids"]}
            ),
        }
        gap_scopes = out.get("gap_scopes", {})
        decided_keys = {
            f"{r['scope_type']}:{r['scope_id']}"
            for r in rows
            if r["state"] != "not_assessed"
        }
        out["gap_ids"] = sorted(
            g for g in out.get("gap_ids", []) if gap_scopes.get(g) not in decided_keys
        )
    return out


def derive_uncertainties(ev: Evidence) -> list[ScientificUncertainty]:
    """Apply DECISION-* uncertainty rules; each result names the rules that fired."""
    result: list[ScientificUncertainty] = []
    target = _target(ev)
    phenotype = has_compound_phenotype(ev)
    engagement = _edge(ev, "engagement")
    biochemical = _edge(ev, "biochemical") == "supported"
    gaps = sorted(_ids(ev, "gap_ids"))
    unresolved_sel = ev.get("selectivity", {}).get("unresolved_ids", [])
    selectivity = ev.get("selectivity", {"total": 0, "comparable": 0})

    if phenotype and biochemical:
        rollup = ev.get("engagement_rollup")
        if rollup:
            status = {
                "complete": "resolved_for_current_decision",
                "partial": "partially_resolved",
            }.get(rollup["status"], "open")
        else:
            status = {
                "supported": "resolved_for_current_decision",
                "contradicted": "resolved_for_current_decision",
                "mixed": "partially_resolved",
            }.get(engagement, "open")
        fired = ["DECISION-GAP-001"]
        relevance = "decision_material"
        reasons = [
            "biochemical activity is supported",
            "a compound-treated cellular phenotype is supported",
            f"direct cellular engagement is {engagement.replace('_', ' ')}",
        ]
        breakdown: tuple[tuple[str, str, str], ...] = ()
        if rollup:
            fired.append("DECISION-RESULT-002")
            breakdown = tuple(
                (s["scope_type"], s["scope_id"], s["state"]) for s in rollup["scopes"]
            )
            reasons.append(
                "scope coverage: "
                + "; ".join(f"{t}:{i} {s.replace('_', ' ')}" for t, i, s in breakdown)
                + " (a result for one scope never resolves another)"
            )
        if status == "open" and selectivity_unresolved(ev):
            relevance = "decision_blocking"
            fired.append("DECISION-GAP-002")
            reasons.append(
                "selectivity is unresolved, so an off-target explanation remains viable"
            )
        elif status == "open":
            reasons.append(
                "comparable selectivity data exist, so engagement is material "
                "rather than blocking"
            )
        if status == "resolved_for_current_decision":
            relevance = "informative"
        reasons += _coverage_reason(ev)
        result.append(
            ScientificUncertainty(
                "uncertainty:target_engagement",
                "target_engagement",
                f"Do the phenotype-producing compounds directly engage {target} in "
                "cells at those exposures?",
                status,
                relevance,
                "directly_testable",
                "Engagement is the missing link between biochemical activity and "
                "the cellular phenotype.",
                tuple(fired),
                tuple(reasons),
                tuple(gaps),
                (),
                _refs(
                    ("edge", ["biochemical", "engagement"]),
                    ("gap", gaps),
                    ("cellular_assessment", _ids(ev, "compound_phenotype_ids")),
                ),
                ("on_target", "off_target", "indirect_pathway"),
                scope_breakdown=breakdown,
            )
        )

    if biochemical and not phenotype and engagement != "supported":
        result.append(
            ScientificUncertainty(
                "uncertainty:assay_translation",
                "assay_translation",
                f"Does biochemical activity against {target} translate to a "
                "cellular effect?",
                "open",
                "decision_blocking",
                "directly_testable",
                "Biochemical activity alone says nothing about activity in cells.",
                ("DECISION-TRANS-001",),
                (
                    "biochemical activity is supported",
                    "no cellular phenotype is supported",
                    f"direct cellular engagement is {engagement.replace('_', ' ')}",
                ),
                (),
                (),
                _refs(("edge", ["biochemical", "engagement"])),
                ("on_target",),
            )
        )

    if phenotype and (
        _ids(ev, "genetic_dependency_ids")
        or _ids(ev, "compound_dependency_uncertain_ids")
    ):
        resolved = bool(_ids(ev, "compound_dependency_supported_ids")) and not _ids(
            ev, "compound_dependency_uncertain_ids"
        )
        result.append(
            ScientificUncertainty(
                "uncertainty:target_dependency",
                "target_dependency",
                f"Is the compound phenotype {target}-dependent, as the genetic "
                "perturbation phenotype is?",
                "resolved_for_current_decision" if resolved else "open",
                "informative" if resolved else "decision_material",
                "directly_testable",
                "Genetic dependency does not transfer to a compound without a "
                "matched chemical-genetic comparison.",
                ("DECISION-DEP-001",),
                (
                    "genetic perturbation phenotypes are dependency-supported",
                    "compound dependency is uncertain / not assessed",
                    f"{ev.get('concordance', {}).get('not_comparable', 0)} "
                    "chemical-genetic comparisons are not comparable",
                ),
                tuple(gaps),
                (),
                _refs(
                    ("cellular_assessment", _ids(ev, "genetic_dependency_ids")),
                    (
                        "cellular_assessment",
                        _ids(ev, "compound_dependency_uncertain_ids"),
                    ),
                ),
                ("on_target", "off_target"),
            )
        )

    if phenotype:
        resolved = selectivity["comparable"] > 0 and not unresolved_sel
        partial = selectivity["comparable"] > 0 and bool(unresolved_sel)
        result.append(
            ScientificUncertainty(
                "uncertainty:selectivity",
                "selectivity",
                f"Is the compound phenotype attributable to {target} rather than to "
                "paralogue or other off-target activity?",
                "resolved_for_current_decision"
                if resolved
                else "partially_resolved"
                if partial
                else "open",
                "informative" if resolved else "decision_material",
                "indirectly_testable",
                "A cellular experiment cannot resolve selectivity without a "
                "comparable biochemical panel.",
                ("DECISION-SEL-001",),
                (
                    f"{selectivity['comparable']} of {selectivity['total']} "
                    "selectivity comparisons are directly comparable",
                    *_selectivity_breakdown(selectivity),
                ),
                tuple(gaps),
                (),
                _refs(("selectivity_assessment", list(unresolved_sel))),
                ("on_target", "off_target"),
            )
        )

    contexts = ev.get("contexts", {})
    if contexts:
        unmatched = contexts.get("unmatched_context_experiments", 0)
        missing = not contexts.get("allotype_reported", False) or unmatched
        reasons = []
        if not contexts.get("allotype_reported", False):
            reasons.append(
                f"{target} allotype/genotype is unreported in every experiment"
            )
        if unmatched:
            reasons.append(f"{unmatched} experiments lack the disease-relevant context")
        result.append(
            ScientificUncertainty(
                "uncertainty:genetic_context",
                "genetic_context",
                f"Does the effect depend on the disease-relevant context or on the "
                f"{target} genotype/allotype?",
                "open" if missing else "resolved_for_current_decision",
                "decision_material" if missing else "informative",
                "directly_testable",
                f"{target} biology is context sensitive.",
                ("DECISION-CTX-001",),
                tuple(reasons) or ("contexts are reported and matched",),
                (),
                (),
                _refs(("context", list(contexts.get("hla_alleles", [])))),
                ("context_dependent", "on_target"),
            )
        )

    disagreements = sorted(
        ev.get("source_disagreements", []), key=lambda d: d["endpoint"]
    )
    mixed_scopes = sorted(
        (edge, scope, entry)
        for edge, scopes in ev.get("scoped_edges", {}).items()
        for scope, entry in scopes.items()
        if entry["state"] == "mixed"
    )
    if disagreements or mixed_scopes:
        fired_repro = ["DECISION-REPRO-001"] if disagreements else []
        reasons_repro = [
            f"{d['endpoint']}: {' vs '.join(sorted(d['directions']))}"
            for d in disagreements
        ]
        if mixed_scopes:
            fired_repro.append("DECISION-REPRO-002")
            reasons_repro += [
                f"new results disagree for {edge} / {scope}; both are preserved"
                for edge, scope, _ in mixed_scopes
            ]
        result.append(
            ScientificUncertainty(
                "uncertainty:reproducibility",
                "reproducibility",
                "Is the observed phenotype or engagement reproducible across "
                "cellular systems, sources and experiments?",
                "open",
                "decision_material",
                "requires_multiple_experiments",
                "Sources or results report opposite directions for the same "
                "endpoint; contradiction is preserved, not averaged.",
                tuple(fired_repro),
                tuple(reasons_repro),
                (),
                (),
                tuple(
                    ("readout", r)
                    for d in disagreements
                    for r in sorted(d["readout_ids"])
                )
                + tuple(
                    ("interpretation", i)
                    for _, _, entry in mixed_scopes
                    for i in entry["contribution_ids"]
                ),
                ("context_dependent",),
            )
        )

    for unexpected in sorted(
        ev.get("unexpected_results", []), key=lambda u: u["result_id"]
    ):
        result.append(
            ScientificUncertainty(
                f"uncertainty:unexpected_result:{unexpected['result_id']}",
                "other",
                "How should the observed result that fell outside the predefined "
                f"outcome scenarios ({unexpected['result_id']}) be interpreted?",
                "open",
                "decision_material",
                "unknown",
                "Observed result falls outside the predefined outcome scenarios; it is "
                "preserved, not force-fitted.",
                ("DECISION-RESULT-003",),
                ("scenario match: outside predefined scenarios",),
                (),
                (),
                (("result", unexpected["result_id"]),),
                (),
            )
        )

    if _ids(ev, "functional_insufficient_ids"):
        result.append(
            ScientificUncertainty(
                "uncertainty:mechanistic_bridge",
                "mechanistic_bridge",
                f"Is proximal {target} catalytic modulation shown between "
                "engagement and the downstream phenotype?",
                "open",
                "decision_material",
                "directly_testable",
                "Downstream phenotype alone does not show proximal modulation.",
                ("DECISION-BRIDGE-001",),
                ("functional modulation is insufficiently shown",),
                (),
                (),
                _refs(("cellular_assessment", _ids(ev, "functional_insufficient_ids"))),
                ("indirect_pathway", "on_target"),
            )
        )
    elif engagement == "supported" and not phenotype:
        result.append(
            ScientificUncertainty(
                "uncertainty:mechanistic_bridge",
                "mechanistic_bridge",
                f"Does demonstrated {target} engagement lead to the relevant "
                "cellular phenotype?",
                "open",
                "decision_material",
                "directly_testable",
                "Engagement without phenotype is a distinct state from phenotype "
                "without engagement.",
                ("DECISION-BRIDGE-002",),
                (
                    "direct cellular engagement is supported",
                    "no relevant cellular phenotype is supported",
                ),
                (),
                (),
                _refs(("edge", ["engagement"])),
                ("indirect_pathway", "on_target"),
            )
        )

    disease = _edge(ev, "disease")
    upstream_open = any(
        u.id
        in (
            "uncertainty:target_engagement",
            "uncertainty:target_dependency",
            "uncertainty:assay_translation",
        )
        and u.status == "open"
        for u in result
    )
    result.append(
        ScientificUncertainty(
            "uncertainty:disease_relevance",
            "disease_relevance",
            "Does the molecular phenotype translate to a disease-relevant "
            "phenotype in patient-relevant systems?",
            "resolved_for_current_decision" if disease == "supported" else "open",
            "informative" if upstream_open else "decision_material",
            "requires_multiple_experiments",
            "Disease relevance is downstream of unresolved target dependency."
            if upstream_open
            else "Upstream links are resolved; disease relevance now limits "
            "the decision.",
            ("DECISION-DIS-001",),
            (f"disease edge is {disease.replace('_', ' ')}",),
            (),
            (),
            _refs(("edge", ["disease"])),
            (),
        )
    )
    result.append(
        ScientificUncertainty(
            "uncertainty:clinical_translation",
            "clinical_translation",
            f"Does modulation of {target} have clinical benefit?",
            "not_actionable",
            "peripheral",
            "currently_not_testable",
            "No clinical or patient recommendation is in scope.",
            ("DECISION-CLIN-001",),
            (f"clinical edge is {_edge(ev, 'clinical').replace('_', ' ')}",),
            (),
            (),
            _refs(("edge", ["clinical"])),
            (),
        )
    )
    if _ids(ev, "structure_ids"):
        result.append(
            ScientificUncertainty(
                "uncertainty:structural_mechanism",
                "structural_mechanism",
                "Can the mapped structure resolve cellular engagement or dependency?",
                "not_actionable",
                "peripheral",
                "currently_not_testable",
                "A structure informs design; it cannot establish cellular engagement.",
                ("DECISION-STRUCT-001",),
                ("structure evidence exists but is not a cellular measurement",),
                (),
                (),
                _refs(("structure", _ids(ev, "structure_ids"))),
                (),
            )
        )
    return result


GROUND_RULES = {
    "on_target": "DECISION-EXPL-010",
    "off_target": "DECISION-EXPL-011",
    "indirect_pathway": "DECISION-EXPL-012",
    "context_dependent": "DECISION-EXPL-013",
}


def explanation_links(
    ev: Evidence, ground: str, explanation_id: str
) -> list[ExplanationEvidenceLink]:
    """Evidence links for one explanation ground; an empty list means ungrounded."""
    rule = GROUND_RULES[ground]
    target = _target(ev)
    links: list[ExplanationEvidenceLink] = []

    def add(relationship: str, kind: str, identifier: str, why: str) -> None:
        links.append(
            ExplanationEvidenceLink(
                explanation_id, relationship, kind, identifier, rule, why
            )
        )

    engagement = _edge(ev, "engagement")
    concordance = ev.get("concordance", {})
    selectivity = ev.get("selectivity", {"total": 0, "comparable": 0})
    phenotype = has_compound_phenotype(ev)
    if ground == "on_target" and phenotype:
        for item in _ids(ev, "biochemical_ids"):
            add(
                "supports",
                "measurement",
                item,
                f"Biochemical activity against {target}.",
            )
        for item in _ids(ev, "compound_phenotype_ids"):
            where = ev.get("context_of", {}).get(item)
            add(
                "supports",
                "cellular_assessment",
                item,
                "Compound phenotype reported"
                + (f" (system: {where})." if where else "."),
            )
        for item in _ids(ev, "genetic_dependency_ids"):
            add(
                "supports",
                "cellular_assessment",
                item,
                f"Genetic {target} perturbation produces a dependent phenotype in "
                "this system.",
            )
        rollup = ev.get("engagement_rollup")
        if rollup:
            for scope in rollup["scopes"]:
                if scope["state"] == "supported":
                    add(
                        "supports",
                        "interpretation",
                        scope["contribution_ids"][0],
                        f"Direct cellular engagement shown for {scope['scope_type']}:"
                        f"{scope['scope_id']} only.",
                    )
                elif scope["state"] == "contradicted":
                    add(
                        "contradicts",
                        "interpretation",
                        scope["contribution_ids"][0],
                        f"No engagement observed for {scope['scope_type']}:"
                        f"{scope['scope_id']} in a valid assay.",
                    )
            for item in _ids(ev, "gap_ids"):
                add(
                    "leaves_unresolved",
                    "gap",
                    item,
                    "Direct cellular engagement is not assessed for this scope.",
                )
        elif engagement == "supported":
            add("supports", "edge", "engagement", "Direct cellular engagement shown.")
        else:
            for item in _ids(ev, "gap_ids"):
                add(
                    "leaves_unresolved",
                    "gap",
                    item,
                    "Direct cellular engagement is not assessed.",
                )
        for item in ev.get("selectivity", {}).get("unresolved_ids", []):
            add(
                "leaves_unresolved",
                "selectivity_assessment",
                item,
                "Selectivity not directly comparable or not assessed.",
            )
        for item in _ids(ev, "compound_dependency_uncertain_ids"):
            add(
                "leaves_unresolved",
                "cellular_assessment",
                item,
                "Compound dependency is uncertain.",
            )
        for item in concordance.get("discordant_ids", []):
            add(
                "contradicts",
                "concordance",
                item,
                "Chemical and genetic phenotypes disagree.",
            )
        if engagement == "contradicted" and not rollup:
            add("contradicts", "edge", "engagement", "Engagement assay was negative.")
    elif ground == "off_target" and phenotype:
        for item in ev.get("selectivity", {}).get("unresolved_ids", []):
            add(
                "leaves_unresolved",
                "selectivity_assessment",
                item,
                "Off-target contribution cannot be excluded without comparable "
                "selectivity.",
            )
        if engagement != "supported":
            for item in _ids(ev, "gap_ids"):
                add(
                    "leaves_unresolved",
                    "gap",
                    item,
                    f"Without engagement the phenotype is not attributed to {target}.",
                )
        for item in concordance.get("discordant_ids", []):
            add(
                "supports",
                "concordance",
                item,
                "Compound and genetic phenotypes differ.",
            )
        for item in ev.get("selectivity", {}).get("comparable_ids", []):
            add(
                "contradicts",
                "selectivity_assessment",
                item,
                "Comparable selectivity reduces, but does not eliminate, off-target "
                "contribution.",
            )
        rollup = ev.get("engagement_rollup")
        if rollup:
            for scope in rollup["scopes"]:
                if scope["state"] == "contradicted":
                    add(
                        "supports",
                        "interpretation",
                        scope["contribution_ids"][0],
                        f"Phenotype persists for {scope['scope_type']}:"
                        f"{scope['scope_id']} although engagement was not observed.",
                    )
        elif engagement == "contradicted":
            add(
                "supports",
                "edge",
                "engagement",
                "Phenotype persists although direct engagement was not observed.",
            )
        if engagement == "supported" and selectivity["comparable"] > 0:
            add(
                "contradicts",
                "edge",
                "engagement",
                "Engagement plus comparable selectivity argues against an off-target "
                "primary cause.",
            )
    elif ground == "indirect_pathway" and _ids(ev, "functional_insufficient_ids"):
        for item in _ids(ev, "functional_insufficient_ids"):
            add(
                "leaves_unresolved",
                "cellular_assessment",
                item,
                "Proximal functional modulation is insufficiently shown.",
            )
    elif ground == "context_dependent":
        contexts = ev.get("contexts", {})
        if not contexts.get("allotype_reported", True):
            add(
                "leaves_unresolved",
                "context",
                "target_allotype",
                f"{target} allotype is unreported in every experiment.",
            )
        if contexts.get("unmatched_context_experiments", 0):
            add(
                "context_limits",
                "context",
                "unmatched_context_systems",
                "Some systems lack the disease-relevant context.",
            )
        for item in sorted(
            ev.get("source_disagreements", []), key=lambda d: d["endpoint"]
        ):
            for readout in sorted(item["readout_ids"]):
                add(
                    "context_limits",
                    "readout",
                    readout,
                    f"Sources disagree on {item['endpoint']} direction.",
                )
    return links


def explanation_status(links: list[ExplanationEvidenceLink]) -> str:
    """DECISION-EXPL-001; raises for an ungrounded explanation.

    Counter-evidence that leaves open items (or coexists with support) is
    *weakened*; counter-evidence with nothing else is *contradicted*.
    """
    if not links:
        raise ValueError("explanation has no grounded evidence link")
    count = {
        kind: 0
        for kind in ("supports", "contradicts", "leaves_unresolved", "context_limits")
    }
    for link in links:
        count[link.relationship] += 1
    support, contradict = count["supports"], count["contradicts"]
    open_items = count["leaves_unresolved"] + count["context_limits"]
    if contradict and (support or open_items):
        return "weakened"
    if contradict:
        return "contradicted"
    if support:
        return "partially_supported" if open_items else "supported"
    return "viable" if count["leaves_unresolved"] else "unresolved"


def discrimination(
    interpretations: dict[str, dict[str, str]], viable: set[str]
) -> dict[str, Any]:
    """DECISION-EXP-001/004; ``interpretations``: scenario -> explanation -> effect."""
    pairs: set[tuple[str, str]] = set()
    for effects in interpretations.values():
        signed = {
            key: EFFECT_SIGN[value]
            for key, value in effects.items()
            if key in viable and value in EFFECT_SIGN
        }
        for a in sorted(signed):
            for b in sorted(signed):
                if a < b and signed[a] * signed[b] < 0:
                    pairs.add((a, b))
    return {
        "separated_pairs": sorted(pairs),
        "low_discrimination": not pairs,
        "rule": "DECISION-EXP-001",
    }


def falsification(
    interpretations: dict[str, dict[str, str]],
    scenario_kinds: dict[str, str],
    statuses: dict[str, str],
) -> dict[str, Any]:
    """DECISION-EXP-005: can an interpretable scenario weaken a preferred one?"""
    preferred = sorted(e for e, s in statuses.items() if s in PREFERRED_STATUSES)
    if not preferred:
        preferred = sorted(e for e, s in statuses.items() if s != "contradicted")
    weakening = sorted(
        scenario
        for scenario, effects in interpretations.items()
        if scenario_kinds.get(scenario) != "non_interpretable"
        and any(EFFECT_SIGN.get(effects.get(e, ""), 0) < 0 for e in preferred)
    )
    return {
        "falsifying": bool(weakening),
        "preferred_explanations": preferred,
        "weakening_scenarios": weakening,
        "rule": "DECISION-EXP-005",
    }


def interpretability(
    profile: dict[str, Any], scenario_kinds: list[str]
) -> dict[str, Any]:
    """DECISION-EXP-002: count four documented criteria."""
    if not profile.get("controls_negative") and not profile.get("controls_positive"):
        return {"level": "unknown", "met": [], "rule": "DECISION-EXP-002"}
    met = []
    if sum(kind != "non_interpretable" for kind in scenario_kinds) >= 3:
        met.append("at least three interpretable outcome scenarios")
    if profile["target_proximity"] in ("direct_target", "target_proximal"):
        met.append("endpoint is direct or target-proximal")
    if profile.get("controls_negative"):
        met.append("a negative control is specified")
    if profile.get("confounders_addressed"):
        met.append("a stated confounder is addressed")
    level = "high" if len(met) == 4 else "moderate" if len(met) >= 2 else "low"
    return {"level": level, "met": met, "rule": "DECISION-EXP-002"}


def _unestablished(profile: dict[str, Any]) -> int:
    return sum(
        status != "available_in_corpus" for _, status in profile["prerequisites"]
    )


CANDIDATE_CRITERIA = (
    "falsification (able to weaken a preferred explanation)",
    "explanation pairs separated",
    "distinct next actions across outcomes",
    "interpretability",
    "target proximity",
    "unestablished prerequisites",
)


def candidate_key(item: dict[str, Any]) -> list[int]:
    """Scientific criteria only; the identifier is deliberately not a criterion."""
    return [
        0 if item["falsification"]["falsifying"] else 1,
        -len(item["discrimination"]["separated_pairs"]),
        -item["distinct_consequences"],
        INTERPRETABILITY_RANK[item["interpretability"]["level"]],
        PROXIMITY_RANK[item["profile"]["target_proximity"]],
        _unestablished(item["profile"]),
    ]


def rank_candidates(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DECISION-EXP-003. Adds ``rank_key``, ``excluded`` and ``tied_with``.

    Input order never matters: candidates are sorted by criteria, then by id only to
    give ties a stable display order; ties are reported, not resolved.
    """
    for item in analyses:
        item["rank_key"] = candidate_key(item)
        item["excluded"] = (
            "feasibility is blocked"
            if item["feasibility"]["level"] == "blocked"
            else None
        )
    ordered = sorted(
        analyses,
        key=lambda a: (a["excluded"] is not None, a["rank_key"], a["experiment_id"]),
    )
    for item in ordered:
        item["tied_with"] = sorted(
            other["experiment_id"]
            for other in ordered
            if other is not item
            and other["excluded"] is None
            and item["excluded"] is None
            and other["rank_key"] == item["rank_key"]
        )
    return ordered


CRITERIA = (
    "decision relevance",
    "viable explanations separated by resolving it",
    "resolvability",
    "an experiment is available",
    "distinct next actions across outcomes",
)


def _critical_key(
    u: ScientificUncertainty,
    viable_explanations: set[str],
    candidate_info: dict[str, dict[str, int]],
) -> tuple[int, ...]:
    info = candidate_info.get(u.category, {"count": 0, "consequences": 0})
    affected = len([e for e in u.affected_explanation_ids if e in viable_explanations])
    return (
        RELEVANCE_RANK[u.decision_relevance],
        -affected,
        RESOLVABILITY_RANK[u.resolvability],
        0 if info["count"] else 1,
        -info["consequences"],
    )


def select_critical(
    uncertainties: list[ScientificUncertainty],
    viable_explanations: set[str],
    candidate_info: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """DECISION-CRIT-001: pick one open, testable uncertainty and say why.

    Input order does not matter; exact ties on every criterion are reported in
    ``tied_with`` and only then ordered by id for stable display.
    """
    eligible = [
        u
        for u in uncertainties
        if u.status in ("open", "partially_resolved")
        and u.resolvability != "currently_not_testable"
    ]

    def key(u: ScientificUncertainty) -> tuple[int, ...]:
        return _critical_key(u, viable_explanations, candidate_info)

    ranked = sorted(eligible, key=lambda u: (key(u), u.id))
    others = []
    for u in sorted(uncertainties, key=lambda u: u.id):
        if ranked and u.id == ranked[0].id:
            continue
        if u not in eligible:
            others.append(
                {
                    "uncertainty_id": u.id,
                    "reason": f"not selected: status is {u.status.replace('_', ' ')}"
                    + (
                        " and it cannot currently be tested"
                        if u.resolvability == "currently_not_testable"
                        else ""
                    ),
                }
            )
        else:
            winner = ranked[0]
            deciding = next(
                (
                    index
                    for index, (a, b) in enumerate(
                        zip(key(winner), key(u), strict=True)
                    )
                    if a != b
                ),
                None,
            )
            if deciding is None:
                reason = (
                    "not selected: tied with the selected uncertainty on every "
                    "criterion; identifier order is a display convention only"
                )
            else:
                reason = (
                    "not selected: lower on "
                    + CRITERIA[deciding]
                    + f" ({u.decision_relevance.replace('_', ' ')}, "
                    f"{u.resolvability.replace('_', ' ')}) than "
                    f"{winner.category.replace('_', ' ')}"
                )
            others.append({"uncertainty_id": u.id, "reason": reason})
    if not ranked:
        return {
            "selected": None,
            "reasons": [],
            "alternatives": others,
            "tied_with": [],
            "rule": "DECISION-CRIT-001",
            "message": "No open, testable uncertainty meets the criticality criteria; "
            "no next discriminating experiment is currently justified.",
        }
    winner = ranked[0]
    info = candidate_info.get(winner.category, {"count": 0, "consequences": 0})
    return {
        "selected": winner.id,
        "reasons": [
            f"decision relevance: {winner.decision_relevance.replace('_', ' ')}",
            "explanations depending on it: "
            + (
                ", ".join(
                    e
                    for e in winner.affected_explanation_ids
                    if e in viable_explanations
                )
                or "none"
            ),
            f"resolvability: {winner.resolvability.replace('_', ' ')}",
            f"{info['count']} candidate experiments are considered for it",
            f"{info['consequences']} distinct next actions across their outcomes",
            *winner.reasons,
        ],
        "alternatives": others,
        "tied_with": sorted(u.id for u in ranked[1:] if key(u) == key(winner)),
        "rule": "DECISION-CRIT-001",
    }
