"""Conservative, transparent categorical rules; no translational score."""

from dataclasses import asdict
from typing import Any

from axis.domain.cellular import CellularExperiment, ExperimentalReadout


def aggregate(states: list[str]) -> str:
    if "mixed" in states or {"supported", "contradicted"}.issubset(states):
        return "mixed"
    for state in ("contradicted", "supported", "insufficient", "not_assessed"):
        if state in states:
            return state
    return "not_applicable" if states else "not_assessed"


def concordance(
    left: CellularExperiment,
    right: CellularExperiment,
    a: ExperimentalReadout,
    b: ExperimentalReadout,
) -> dict[str, Any]:
    reasons = []
    x, y = asdict(left.context), asdict(right.context)
    for key in ("cell_line", "hla_allele", "hla_expression", "disease_status"):
        if not x[key] or not y[key] or x[key] != y[key]:
            reasons.append(f"unknown/different {key}")
    for key in ("species", "genotype", "allotype", "assay", "experimental_system"):
        first, second = x["scientific_context"][key], y["scientific_context"][key]
        if not first or not second or first != second:
            reasons.append(f"unknown/different {key}")
    if not left.duration or left.duration != right.duration:
        reasons.append("unknown/different duration")
    if a.endpoint != b.endpoint:
        reasons.append("different endpoint")
    if left.modality == right.modality or "small_molecule" not in {
        left.modality,
        right.modality,
    }:
        reasons.append("not genetic versus chemical")
    return {
        "experiment_ids": [left.id, right.id],
        "readout_ids": [a.id, b.id],
        "state": "not_comparable"
        if reasons
        else ("concordant" if a.direction == b.direction else "discordant"),
        "rationale": "; ".join(reasons)
        if reasons
        else (
            "Matched reported contexts and endpoint; directions compared. "
            "Concordance alone does not establish on-target drug action."
        ),
        "review_status": "pending_expert_review",
        "rule_version": "axis-cellular-1",
        "inputs": [asdict(left), asdict(right), asdict(a), asdict(b)],
    }
