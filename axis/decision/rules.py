"""Versioned, transparent decision rules over a plain evidence-state mapping.

Every function is pure and unit-testable without a store. There are no numeric
scores, probabilities or information-gain figures: ordering is lexicographic over
documented categorical criteria and every comparison reports the criterion that
decided it.
"""

from dataclasses import dataclass
from typing import Any

from axis.domain.decision import ExplanationEvidenceLink, ScientificUncertainty

RULES_VERSION = "axis-decision-1"
Evidence = dict[str, Any]
Ref = tuple[str, str]


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
            "phenotype exist but direct cellular engagement is not supported.",
            "edges.biochemical, edges.engagement, compound_phenotype_ids",
            "target_engagement uncertainty (decision_material)",
            "A phenotype is not engagement; the bridge is unobserved, not refuted.",
        ),
        _rule(
            "DECISION-GAP-002",
            "Raise engagement to decision_blocking while an off-target explanation "
            "remains viable because selectivity is unresolved.",
            "selectivity.unresolved_ids, uncertainty target_engagement",
            "target_engagement decision_blocking",
            "Without engagement or selectivity, the compound phenotype cannot be "
            "attributed to ERAP1 and the strategy decision cannot be taken.",
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
            "comparable.",
            "selectivity",
            "selectivity uncertainty (decision_material, indirectly_testable)",
            "A cellular experiment alone cannot resolve selectivity; it needs a "
            "comparable biochemical panel.",
        ),
        _rule(
            "DECISION-CTX-001",
            "Genetic-context uncertainty when ERAP1 allotype is unreported in every "
            "experiment or an experiment lacks HLA-B27 context.",
            "contexts",
            "genetic_context uncertainty (decision_material)",
            "ERAP1 x HLA-B27 biology is context sensitive; contexts are not "
            "interchangeable.",
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
            "Downstream phenotype alone does not show proximal catalytic modulation.",
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
            "Ground: compound phenotype arises through direct ERAP1 modulation.",
            "compound phenotype, biochemical, engagement, selectivity",
            "evidence links",
            "Admitted only when a compound phenotype exists.",
        ),
        _rule(
            "DECISION-EXPL-011",
            "Ground: phenotype arises through off-target activity.",
            "selectivity, engagement, concordance",
            "evidence links",
            "Admitted while selectivity or engagement leave it open.",
        ),
        _rule(
            "DECISION-EXPL-012",
            "Ground: ERAP1 is perturbed but the phenotype is indirect.",
            "functional_insufficient_ids",
            "evidence links",
            "Admitted while proximal functional modulation is insufficient.",
        ),
        _rule(
            "DECISION-EXPL-013",
            "Ground: effect depends on HLA / ERAP1 genetic context.",
            "contexts, source_disagreements",
            "evidence links",
            "Admitted when contexts are unmatched or sources disagree.",
        ),
        _rule(
            "DECISION-CRIT-001",
            "Critical uncertainty: lexicographic over relevance, explanations "
            "separated, resolvability, candidate availability, and distinct next "
            "actions; unresolved and testable only.",
            "uncertainties, explanations, candidates",
            "one critical uncertainty with per-criterion reasons",
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
            "Recommended experiment among those considered for the critical "
            "uncertainty: exclude blocked; then separated pairs, distinct next "
            "actions, interpretability, proximity, fewer unestablished "
            "prerequisites, id.",
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
    ]
)

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
VIABLE_STATUSES = {"supported", "partially_supported", "viable", "unresolved"}


def _edge(ev: Evidence, name: str) -> str:
    return str(ev["edges"].get(name, {}).get("state", "not_assessed"))


def _ids(ev: Evidence, key: str) -> list[str]:
    return list(ev.get(key, []))


def has_compound_phenotype(ev: Evidence) -> bool:
    return bool(_ids(ev, "compound_phenotype_ids"))


def selectivity_unresolved(ev: Evidence) -> bool:
    selectivity = ev.get("selectivity", {"total": 0, "comparable": 0})
    return bool(selectivity["comparable"] == 0)


def off_target_viable(ev: Evidence) -> bool:
    return has_compound_phenotype(ev) and (
        selectivity_unresolved(ev) or _edge(ev, "engagement") != "supported"
    )


def _refs(*groups: tuple[str, list[str]]) -> tuple[Ref, ...]:
    return tuple((kind, value) for kind, values in groups for value in sorted(values))


def derive_uncertainties(ev: Evidence) -> list[ScientificUncertainty]:
    """Apply DECISION-* uncertainty rules; each result names the rules that fired."""
    result: list[ScientificUncertainty] = []
    phenotype = has_compound_phenotype(ev)
    engagement = _edge(ev, "engagement")
    gaps = _ids(ev, "gap_ids")
    unresolved_sel = ev.get("selectivity", {}).get("unresolved_ids", [])
    blocking_offtarget = off_target_viable(ev)

    if phenotype and _edge(ev, "biochemical") == "supported":
        status = {
            "supported": "resolved_for_current_decision",
            "mixed": "partially_resolved",
        }.get(engagement, "open")
        fired = ["DECISION-GAP-001"]
        relevance = "decision_material"
        reasons = [
            "biochemical activity is supported",
            "a compound-treated cellular phenotype is supported",
            f"direct cellular engagement is {engagement.replace('_', ' ')}",
        ]
        if status == "open" and blocking_offtarget:
            relevance = "decision_blocking"
            fired.append("DECISION-GAP-002")
            reasons.append(
                "selectivity is unresolved, so an off-target explanation remains viable"
            )
        if status != "open":
            relevance = "informative"
        result.append(
            ScientificUncertainty(
                "uncertainty:target_engagement",
                "target_engagement",
                "Do the phenotype-producing compounds directly engage ERAP1 in cells "
                "at those exposures?",
                status,
                relevance,
                "directly_testable",
                "Engagement is the missing link between biochemical activity and the "
                "cellular phenotype.",
                tuple(fired),
                tuple(reasons),
                tuple(gaps),
                (
                    "explanation:on_target",
                    "explanation:off_target",
                    "explanation:indirect",
                ),
                _refs(
                    ("edge", ["biochemical", "engagement"]),
                    ("gap", gaps),
                    ("cellular_assessment", _ids(ev, "compound_phenotype_ids")),
                ),
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
                "Is the compound phenotype ERAP1-dependent, as the genetic "
                "perturbation phenotype is?",
                "resolved_for_current_decision" if resolved else "open",
                "informative" if resolved else "decision_material",
                "directly_testable",
                "Genetic dependency does not transfer to a compound without a matched "
                "chemical-genetic comparison.",
                ("DECISION-DEP-001",),
                (
                    "genetic perturbation phenotypes are dependency-supported",
                    "compound dependency is uncertain / not assessed",
                    f"{ev.get('concordance', {}).get('not_comparable', 0)} "
                    "chemical-genetic comparisons are not comparable",
                ),
                tuple(gaps),
                ("explanation:on_target", "explanation:off_target"),
                _refs(
                    ("cellular_assessment", _ids(ev, "genetic_dependency_ids")),
                    (
                        "cellular_assessment",
                        _ids(ev, "compound_dependency_uncertain_ids"),
                    ),
                ),
            )
        )

    selectivity = ev.get("selectivity", {"total": 0, "comparable": 0})
    if phenotype and selectivity["total"] >= 0:
        resolved = selectivity["comparable"] > 0 and not unresolved_sel
        partial = selectivity["comparable"] > 0 and bool(unresolved_sel)
        result.append(
            ScientificUncertainty(
                "uncertainty:selectivity",
                "selectivity",
                "Is the compound phenotype attributable to ERAP1 rather than to "
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
                    "selectivity "
                    "comparisons are directly comparable",
                ),
                tuple(gaps),
                ("explanation:on_target", "explanation:off_target"),
                _refs(("selectivity_assessment", list(unresolved_sel))),
            )
        )

    contexts = ev.get("contexts", {})
    if contexts:
        missing = not contexts.get("allotype_reported", False) or contexts.get(
            "non_b27_experiments", 0
        )
        reasons = []
        if not contexts.get("allotype_reported", False):
            reasons.append("ERAP1 allotype is unreported in every experiment")
        if contexts.get("non_b27_experiments", 0):
            reasons.append(
                f"{contexts['non_b27_experiments']} experiments lack an HLA-B27 context"
            )
        result.append(
            ScientificUncertainty(
                "uncertainty:genetic_context",
                "genetic_context",
                "Does the effect depend on the HLA-B27 subtype or ERAP1 allotype "
                "context?",
                "open" if missing else "resolved_for_current_decision",
                "decision_material" if missing else "informative",
                "directly_testable",
                "ERAP1 x HLA-B27 biology is context sensitive.",
                ("DECISION-CTX-001",),
                tuple(reasons) or ("contexts are reported and matched",),
                (),
                ("explanation:context", "explanation:on_target"),
                _refs(("context", list(contexts.get("hla_alleles", [])))),
            )
        )

    disagreements = ev.get("source_disagreements", [])
    if disagreements:
        result.append(
            ScientificUncertainty(
                "uncertainty:reproducibility",
                "reproducibility",
                "Is the genetic-perturbation phenotype reproducible across cellular "
                "systems and sources?",
                "open",
                "decision_material",
                "requires_multiple_experiments",
                "Sources report opposite directions for the same genetic endpoint "
                "in different systems.",
                ("DECISION-REPRO-001",),
                tuple(
                    f"{d['endpoint']}: {' vs '.join(d['directions'])}"
                    for d in disagreements
                ),
                (),
                ("explanation:context",),
                tuple(("readout", r) for d in disagreements for r in d["readout_ids"]),
            )
        )

    if _ids(ev, "functional_insufficient_ids"):
        result.append(
            ScientificUncertainty(
                "uncertainty:mechanistic_bridge",
                "mechanistic_bridge",
                "Is proximal ERAP1 catalytic modulation shown between engagement and "
                "the downstream HLA phenotype?",
                "open",
                "decision_material",
                "directly_testable",
                "Downstream phenotype alone does not show proximal modulation.",
                ("DECISION-BRIDGE-001",),
                ("functional modulation is insufficiently shown",),
                (),
                ("explanation:indirect", "explanation:on_target"),
                _refs(("cellular_assessment", _ids(ev, "functional_insufficient_ids"))),
            )
        )

    disease = _edge(ev, "disease")
    upstream_open = any(
        u.id in ("uncertainty:target_engagement", "uncertainty:target_dependency")
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
        )
    )
    result.append(
        ScientificUncertainty(
            "uncertainty:clinical_translation",
            "clinical_translation",
            "Does modulation have clinical benefit in axial spondyloarthritis?",
            "not_actionable",
            "peripheral",
            "currently_not_testable",
            "No clinical or patient recommendation is in scope.",
            ("DECISION-CLIN-001",),
            (f"clinical edge is {_edge(ev, 'clinical').replace('_', ' ')}",),
            (),
            (),
            _refs(("edge", ["clinical"])),
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
            add("supports", "measurement", item, "Biochemical activity against ERAP1.")
        for item in _ids(ev, "compound_phenotype_ids"):
            add("supports", "cellular_assessment", item, "Compound phenotype reported.")
        for item in _ids(ev, "genetic_dependency_ids"):
            add(
                "supports",
                "cellular_assessment",
                item,
                "Genetic ERAP1 perturbation produces a dependent phenotype in this "
                "system.",
            )
        if engagement == "supported":
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
        if engagement == "contradicted":
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
                    "Without engagement the phenotype is not attributed to ERAP1.",
                )
        for item in concordance.get("discordant_ids", []):
            add(
                "supports",
                "concordance",
                item,
                "Compound and genetic phenotypes differ.",
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
                "erap1_allotype",
                "ERAP1 allotype is unreported in every experiment.",
            )
        if contexts.get("non_b27_experiments", 0):
            add(
                "context_limits",
                "context",
                "non_b27_systems",
                "Some systems lack an HLA-B27 context.",
            )
        for item in ev.get("source_disagreements", []):
            for readout in item["readout_ids"]:
                add(
                    "context_limits",
                    "readout",
                    readout,
                    f"Sources disagree on {item['endpoint']} direction.",
                )
    return links


def explanation_status(links: list[ExplanationEvidenceLink]) -> str:
    """DECISION-EXPL-001; raises for an ungrounded explanation."""
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
    if support and contradict:
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


def rank_candidates(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DECISION-EXP-003. Adds ``rank_key`` and ``excluded`` to each analysis."""
    for item in analyses:
        item["rank_key"] = [
            -len(item["discrimination"]["separated_pairs"]),
            -item["distinct_consequences"],
            INTERPRETABILITY_RANK[item["interpretability"]["level"]],
            PROXIMITY_RANK[item["profile"]["target_proximity"]],
            _unestablished(item["profile"]),
            item["experiment_id"],
        ]
        item["excluded"] = (
            "feasibility is blocked"
            if item["feasibility"]["level"] == "blocked"
            else None
        )
    return sorted(analyses, key=lambda a: (a["excluded"] is not None, a["rank_key"]))


CRITERIA = (
    "decision relevance",
    "viable explanations separated by resolving it",
    "resolvability",
    "an experiment is available",
    "distinct next actions across outcomes",
)


def select_critical(
    uncertainties: list[ScientificUncertainty],
    viable_explanations: set[str],
    candidate_info: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """DECISION-CRIT-001: pick one open, testable uncertainty and say why."""
    eligible = [
        u
        for u in uncertainties
        if u.status in ("open", "partially_resolved")
        and u.resolvability != "currently_not_testable"
    ]

    def key(u: ScientificUncertainty) -> tuple[int, ...]:
        info = candidate_info.get(u.category, {"count": 0, "consequences": 0})
        affected = len(
            [e for e in u.affected_explanation_ids if e in viable_explanations]
        )
        return (
            RELEVANCE_RANK[u.decision_relevance],
            -affected,
            RESOLVABILITY_RANK[u.resolvability],
            0 if info["count"] else 1,
            -info["consequences"],
        )

    ranked = sorted(eligible, key=lambda u: (key(u), u.id))
    others = []
    for u in uncertainties:
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
                len(CRITERIA),
            )
            others.append(
                {
                    "uncertainty_id": u.id,
                    "reason": "not selected: lower on "
                    + (
                        CRITERIA[deciding]
                        if deciding < len(CRITERIA)
                        else "the final identifier tie-break"
                    )
                    + f" ({u.decision_relevance.replace('_', ' ')}, "
                    f"{u.resolvability.replace('_', ' ')}) than "
                    f"{winner.category.replace('_', ' ')}",
                }
            )
    if not ranked:
        return {"selected": None, "reasons": [], "alternatives": others}
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
        "rule": "DECISION-CRIT-001",
    }
