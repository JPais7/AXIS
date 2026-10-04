"""Deterministic, explainable candidate prioritization (pure).

There is no aggregate score. Dimensions stay separate; the rules below decide only
panel membership and are fingerprinted. Experimental evidence is never mixed with
computational observations.
"""

import hashlib
import json
from typing import Any

RULES_VERSION = "axis-prioritization-1"
RULES: dict[str, str] = {
    "PRIO-001": "Compounds whose preparation failed are excluded and reported.",
    "PRIO-002": (
        "Compounds with indexed experimental evidence are reference chemistry, "
        "reported separately; they are not computational candidates."
    ),
    "PRIO-003": (
        "A computational candidate is an exploitation candidate when its highest "
        "similarity to reference chemistry reaches the campaign threshold, "
        "otherwise an exploration candidate."
    ),
    "PRIO-004": (
        "If the campaign requires structural compatibility and no structural "
        "method produced evidence, no candidate is selected."
    ),
    "PRIO-005": (
        "Panel quotas per role come from the campaign configuration; a role "
        "with fewer eligible candidates than its quota is filled only by those."
    ),
    "PRIO-006": (
        "At most `per_cluster` candidates are taken from one chemical cluster, "
        "so near-duplicates are not selected unless the campaign allows it."
    ),
    "PRIO-007": (
        "Within a cluster, fewer descriptor flags first; then, for exploitation "
        "higher / for exploration lower similarity to reference chemistry; then "
        "the stable compound reference (display tie-break only)."
    ),
    "PRIO-008": (
        "Descriptor flags are reported, never used to exclude a compound or to "
        "form a total."
    ),
    "PRIO-009": (
        "An empty panel is a valid outcome and is stated as such; no candidate "
        "is invented to fill it."
    ),
}


def fingerprint() -> str:
    text = json.dumps({"v": RULES_VERSION, "rules": RULES}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def _max_similarity(
    ref: str, similarities: dict[str, dict[str, float | None]]
) -> tuple[float | None, str | None]:
    best: tuple[float | None, str | None] = (None, None)
    for other, value in sorted(similarities.get(ref, {}).items()):
        if value is not None and (best[0] is None or value > best[0]):
            best = (value, other)
    return best


def prioritize(
    *,
    members: list[dict[str, Any]],
    prepared: dict[str, dict[str, Any]],
    known: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
    flags: dict[str, list[dict[str, Any]]],
    similarities: dict[str, dict[str, float | None]],
    clusters: dict[str, Any],
    scaffolds: dict[str, str],
    structure_available: bool,
    docking: dict[str, Any],
    constraints: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    assay_options: list[str],
    decision_link: dict[str, Any] | None,
) -> dict[str, Any]:
    failures: list[str] = []
    if not members:
        failures.append("chemical space empty")
    failed = sorted(r for r, p in prepared.items() if p["status"] != "prepared")
    if members and len(failed) == len(members):
        failures.append("compound preparation failed for every member")
    if constraints.get("require_structure") and not structure_available:
        failures.append("no usable structure")
    cluster_of = {
        m: i for i, c in enumerate(clusters["clusters"]) for m in c["members"]
    }
    references = [
        m for m in members if known.get(m["ref"], {}).get("has_experimental_evidence")
    ]
    ref_ids = {m["ref"] for m in references}
    candidates = [
        m
        for m in members
        if m["ref"] not in ref_ids and prepared[m["ref"]]["status"] == "prepared"
    ]
    threshold = float(constraints["exploit_threshold"])
    require_structural = bool(constraints.get("require_structural_compatibility"))
    structural_evidence = docking.get("status") == "completed"
    roles: dict[str, list[dict[str, Any]]] = {"exploitation": [], "exploration": []}
    for m in candidates:
        best, against = _max_similarity(m["ref"], similarities)
        role = (
            "exploitation" if best is not None and best >= threshold else "exploration"
        )
        roles[role].append({**m, "_best": best, "_against": against})
    quotas = constraints["panel"]
    per_cluster = int(quotas.get("per_cluster", 1))
    panel: list[dict[str, Any]] = []
    not_selected: list[dict[str, Any]] = []
    taken_by_cluster: dict[int, int] = {}
    if require_structural and not structural_evidence:
        failures.append(
            "structural compatibility required but no structural method completed"
        )
    if not failures:
        for role in ("exploitation", "exploration"):
            pool = sorted(
                roles[role],
                key=lambda m: (
                    len(flags.get(m["ref"], [])),
                    -(m["_best"] or 0.0)
                    if role == "exploitation"
                    else (m["_best"] or 0.0),
                    m["ref"],
                ),
            )
            quota = int(quotas.get(role, 0))
            chosen = 0
            for m in pool:
                cluster_id = cluster_of.get(m["ref"], -1)
                if chosen >= quota:
                    not_selected.append(
                        {
                            "ref": m["ref"],
                            "reason": f"{role} quota of {quota} filled (PRIO-005)",
                        }
                    )
                elif taken_by_cluster.get(cluster_id, 0) >= per_cluster:
                    not_selected.append(
                        {
                            "ref": m["ref"],
                            "reason": f"cluster {cluster_id} already represented (PRIO-006)",
                        }
                    )
                else:
                    taken_by_cluster[cluster_id] = (
                        taken_by_cluster.get(cluster_id, 0) + 1
                    )
                    chosen += 1
                    panel.append({**m, "role": role, "cluster": cluster_id})
    outcome = "failed" if failures else ("panel" if panel else "no_candidate")
    entries = [
        _entry(
            m,
            known,
            descriptors,
            flags,
            similarities,
            scaffolds,
            docking,
            hypotheses,
            assay_options,
            references,
            decision_link,
            panel,
        )
        for m in panel
    ]
    disagreements = [
        {
            "compound": e["compound_ref"],
            "statement": "high similarity to reference chemistry coexists with descriptor flags; both are shown, none is averaged",
        }
        for e in entries
        if (e["dimensions"]["similarity_to_reference"]["value"] or 0) >= threshold
        and e["dimensions"]["descriptor_flags"]
    ]
    statements = []
    if outcome == "no_candidate":
        statements.append(
            "There is insufficient evidence in this chemical space to prioritize any candidate for experimental testing."
        )
    if not roles["exploitation"] and not failures:
        statements.append(
            "No computational candidate reached the exploitation similarity threshold; the exploitation role is empty, not filled."
        )
    tested = {h for e in entries for h in e["hypotheses_tested"]}
    untested = sorted(h["id"] for h in hypotheses if h["id"] not in tested)
    for hid in untested:
        statements.append(
            f"Hypothesis {hid} is not tested by any panel member of this chemical space."
        )
    statements.append(
        "No experimentally supported inactive control is indexed; none was fabricated."
    )
    return {
        "rules_version": RULES_VERSION,
        "rules_fingerprint": fingerprint(),
        "rules": RULES,
        "outcome": outcome,
        "failure_states": failures,
        "failed_preparation": failed,
        "reference_chemistry": [
            {
                "compound_ref": m["ref"],
                "name": m.get("name"),
                "evidence": known[m["ref"]],
            }
            for m in references
        ],
        "panel": entries,
        "not_selected": not_selected,
        "diversity": {
            "clusters_represented": sorted({e["cluster"] for e in entries}),
            "panel_size": len(entries),
            "per_cluster_limit": per_cluster,
            "scaffolds": sorted(
                {scaffolds.get(e["compound_ref"], "") for e in entries}
            ),
        },
        "untested_hypotheses": untested,
        "method_disagreements": disagreements,
        "statements": statements,
        "aggregate_score": None,
    }


def _entry(
    m: dict[str, Any],
    known: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
    flags: dict[str, list[dict[str, Any]]],
    similarities: dict[str, dict[str, float | None]],
    scaffolds: dict[str, str],
    docking: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    assay_options: list[str],
    references: list[dict[str, Any]],
    decision_link: dict[str, Any] | None,
    panel: list[dict[str, Any]],
) -> dict[str, Any]:
    ref = m["ref"]
    best, against = m["_best"], m["_against"]
    mine = [h for h in hypotheses if h["id"] in m.get("hypothesis_ids", [])]
    experimental = known.get(
        ref,
        {
            "has_experimental_evidence": False,
            "summary": "no direct evidence identified in the indexed AXIS sources",
        },
    )
    peers = [p["ref"] for p in panel if p["ref"] != ref and p["role"] == m["role"]]
    dims: dict[str, Any] = {
        "known_experimental_evidence": experimental,
        "similarity_to_reference": {
            "value": best,
            "reference": against,
            "metric": "Tanimoto, Morgan r=2, 2048 bits",
            "meaning": "chemical similarity only; biological relevance is a hypothesis",
        },
        "docking": {"status": docking["status"], "note": "no docking evidence"},
        "chemical_novelty": {
            "value": None if best is None else round(1 - best, 4),
            "meaning": "distinct from the indexed reference chemistry under this metric; not patent novelty",
        },
        "cellular_evidence": "none indexed",
        "selectivity_evidence": "none indexed",
        "descriptors": descriptors.get(ref, {}),
        "descriptor_flags": flags.get(ref, []),
        "scaffold": scaffolds.get(ref, ""),
    }
    against_text = (
        "No indexed experimental evidence against the campaign target exists for this compound; every statement about it is computational or a researcher hypothesis."
        if not experimental.get("has_experimental_evidence")
        else "Existing experimental evidence is for a different question than this campaign tests."
    )
    if dims["descriptor_flags"]:
        against_text += (
            " Descriptor flags: "
            + ", ".join(f["descriptor"] for f in dims["descriptor_flags"])
            + "."
        )
    why = (
        f"{m.get('name', ref)} was selected as an {m['role']} candidate "
        f"testing {', '.join(h['id'] for h in mine) or 'no recorded hypothesis'}: "
        f"highest similarity to reference chemistry is {best if best is not None else 'not computed'}"
        f"{' (' + against + ')' if against else ''}, it falls in a chemical cluster not otherwise represented by "
        f"{'other panel members' if peers else 'the panel'}, and "
        f"{'no experimental activity against the target is indexed for it' if not experimental.get('has_experimental_evidence') else 'experimental evidence is linked separately'}. "
        "No docking evidence supports or opposes it."
    )
    return {
        "compound_ref": ref,
        "name": m.get("name"),
        "role": m["role"],
        "cluster": m["cluster"],
        "why_this_molecule": why,
        "dimensions": dims,
        "supporting_evidence": [
            f"chemical hypothesis {h['id']}: {h['statement']} (researcher hypothesis, review pending)"
            for h in mine
        ],
        "contradicting_evidence": []
        if not dims["descriptor_flags"]
        else ["descriptor flags (descriptive, not exclusionary)"],
        "missing_evidence": [
            "no experimental measurement against the target",
            "no docking/pose evidence",
            "no cellular or selectivity evidence",
        ],
        "strongest_reason_against": against_text,
        "hypotheses_tested": [h["id"] for h in mine],
        "distinguishes_from": peers,
        "what_would_change_our_mind": sorted(
            {c for h in mine for c in h.get("falsification", [])}
        ),
        "experimental_package": _package(
            m, mine, assay_options, references, decision_link
        ),
        "epistemic_status": "ai_suggestion",
        "review_state": "pending_review",
    }


def _package(
    m: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    assay_options: list[str],
    references: list[dict[str, Any]],
    decision_link: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "knowledge_kind": "ai_suggestion",
        "title": f"Test computational candidate {m.get('name', m['ref'])}",
        "compound": m["ref"],
        "hypotheses_tested": [h["id"] for h in hypotheses],
        "suggested_assays": assay_options,
        "positive_control_candidates": [r["ref"] for r in references],
        "negative_control": "none: no experimentally supported inactive control is indexed",
        "outcomes": {
            "positive": "Concentration-dependent change in the assay readout with adequate controls would support testing the chemical hypothesis further; it would not show cellular activity or therapeutic benefit.",
            "negative": "No measurable change at adequate concentration would weaken the chemical hypothesis for this compound only.",
            "non_interpretable": "Failed controls, solubility or assay-interference artefacts: no conclusion about the hypothesis.",
        },
        "decision_consequence": (
            "Results enter the Phase 3.6 results loop and may update the existing decision state."
        ),
        "decision_link": decision_link,
        "requires": "external experimental validation; AXIS cannot run it",
    }
