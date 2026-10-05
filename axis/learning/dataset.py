"""Context-correct learning datasets (pure).

A dataset is a transformation of existing measurements, never a new source.
Measurements are grouped by assay context; groups are never pooled. Units are
normalised only when the conversion is mathematically valid, inequalities are kept,
and contradictory replicates are flagged rather than averaged away.
"""

import hashlib
import statistics
from typing import Any

from axis.serialization import canonical_json

POLICY_VERSION = "axis-learning-dataset-1"
CONCENTRATION_TO_NM = {"pM": 1e-3, "nM": 1.0, "uM": 1e3, "µM": 1e3, "mM": 1e6, "M": 1e9}
DIMENSIONLESS = {"fold", "%"}
OPERATORS = ("=", ">", "<", ">=", "<=")
POLICY: dict[str, Any] = {
    "version": POLICY_VERSION,
    "censoring": "retain_with_operator; a boundary is never an exact value",
    "replicates": "retain_individual; per-compound median of exact values for modelling",
    "contradiction_ratio": 3.0,
    "normalisation": "concentration units to nM only; no endpoint conversion",
    "pooling": "none across assay contexts",
}


def canonical(value: object) -> str:
    return canonical_json(value)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def policy_fingerprint() -> str:
    return digest(POLICY)


CONTEXT_FIELDS = ("target", "taxon", "assay_type", "format", "substrate", "endpoint")


def context_key(record: dict[str, Any]) -> dict[str, Any]:
    context = record["context"]
    return {
        "target": context.get("target"),
        "taxon": context.get("taxon"),
        "assay_type": context.get("assay_type"),
        "format": context.get("format"),
        "substrate": context.get("substrate"),
        "endpoint": record["endpoint"],
    }


def key_slug(key: dict[str, Any]) -> str:
    return "|".join(str(key.get(f) or "unspecified") for f in CONTEXT_FIELDS)


def normalise(value: float, unit: str | None) -> tuple[float | None, str | None, str]:
    """Return (value, unit, transformation). None means no valid conversion."""
    if unit in CONCENTRATION_TO_NM:
        factor = CONCENTRATION_TO_NM[unit]
        return round(value * factor, 9), "nM", f"x{factor:g} ({unit} to nM)"
    if unit in DIMENSIONLESS:
        return value, unit, "none (dimensionless)"
    return None, None, f"no valid conversion for unit {unit!r}"


def group_records(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(records, key=lambda x: x["id"]):
        groups.setdefault(key_slug(context_key(r)), []).append(r)
    return groups


def build_dataset(
    records: list[dict[str, Any]],
    *,
    project_id: str,
    revision: int = 1,
    synthetic: bool = False,
    label: str = "",
    provenance: str = "",
) -> dict[str, Any]:
    """Freeze one dataset from records that share a single assay context."""
    keys = {key_slug(context_key(r)) for r in records}
    if len(keys) != 1:
        raise ValueError(
            "a learning dataset holds one assay context; incompatible measurements "
            f"were offered together: {sorted(keys)}"
        )
    key = context_key(records[0])
    measurements = []
    for r in sorted(records, key=lambda x: x["id"]):
        if r["operator"] not in OPERATORS:
            raise ValueError(f"unknown operator {r['operator']!r} on {r['id']}")
        value, unit, transform = normalise(float(r["value"]), r.get("unit"))
        measurements.append(
            {
                "id": r["id"],
                "compound_ref": r["compound_ref"],
                "operator": r["operator"],
                "original_value": r["value"],
                "original_unit": r.get("unit"),
                "normalized_value": value,
                "normalized_unit": unit,
                "transformation": transform,
                "included": value is not None,
                "exclusion_reason": None if value is not None else transform,
                "source": r.get("source"),
                "date": r.get("date"),
                "replicate_group": r.get("replicate_group"),
            }
        )
    structures = {r["compound_ref"]: r["smiles"] for r in records}
    compound_values = _compound_values(measurements)
    unit = next((m["normalized_unit"] for m in measurements if m["included"]), None)
    body = {
        "logical_id": f"dataset:{key_slug(key)}",
        "revision": revision,
        "project_id": project_id,
        "target": key["target"],
        "endpoint": key["endpoint"],
        "assay_context": key,
        "measurement_type": key["endpoint"],
        "unit": unit,
        "compounds": [
            {"compound_ref": c, "smiles": structures[c]} for c in sorted(structures)
        ],
        "measurements": measurements,
        "compound_values": compound_values,
        "policy": POLICY,
        "policy_fingerprint": policy_fingerprint(),
        "exclusion_rules": ["unit without a valid conversion"],
        "synthetic": synthetic,
        "label": label,
        "provenance": provenance
        or "transformation of indexed measurements; not a new experimental source",
        "review_state": "pending_review",
        "created_by": "axis.learning.dataset",
    }
    content = {
        k: body[k]
        for k in ("measurements", "compounds", "policy_fingerprint", "assay_context")
    }
    return {
        "id": f"{body['logical_id']}@r{revision}",
        "checksum": digest(body),
        "content_checksum": digest(content),
        **body,
    }


def _compound_values(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for m in measurements:
        if m["included"]:
            by.setdefault(m["compound_ref"], []).append(m)
    out = []
    for ref in sorted(by):
        rows = by[ref]
        exact = [m["normalized_value"] for m in rows if m["operator"] == "="]
        censored = [m for m in rows if m["operator"] != "="]
        contradictory = False
        if len(exact) > 1 and min(exact) > 0:
            contradictory = max(exact) / min(exact) > POLICY["contradiction_ratio"]
        out.append(
            {
                "compound_ref": ref,
                "n_measurements": len(rows),
                "exact_values": exact,
                "censored": [
                    {"operator": m["operator"], "value": m["normalized_value"]}
                    for m in censored
                ],
                "value": statistics.median(exact)
                if exact and not contradictory
                else None,
                "operator": "="
                if exact and not contradictory
                else (censored[0]["operator"] if censored and not exact else None),
                "contradictory": contradictory,
                "replicate_policy": "median of exact values"
                if len(exact) > 1
                else "single",
                "sources": sorted({str(m["source"]) for m in rows}),
            }
        )
    return out


# --- comparability --------------------------------------------------------------


def comparability(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Whether two assay contexts may be compared; never converts between endpoints."""
    ka, kb = a, b
    reasons: list[str] = []
    missing = [
        f
        for f in ("substrate", "format", "assay_type")
        if not (ka.get(f) and kb.get(f))
    ]
    if ka == kb:
        state = "directly_comparable"
        reasons.append("identical assay context and endpoint")
    elif ka.get("target") != kb.get("target") or ka.get("taxon") != kb.get("taxon"):
        state = "not_directly_comparable"
        reasons.append(
            "different target or species; a ratio is a selectivity claim that needs its own justification"
        )
    elif ka.get("assay_type") != kb.get("assay_type"):
        state = "not_directly_comparable"
        reasons.append("biochemical and cellular readouts measure different things")
    elif ka.get("endpoint") != kb.get("endpoint"):
        state = "not_directly_comparable"
        reasons.append(
            "different endpoint types (e.g. IC50, Ki, AC50) are not converted"
        )
    elif missing:
        state = "insufficient_context"
        reasons.append(f"assay context not reported: {', '.join(missing)}")
    elif ka.get("substrate") != kb.get("substrate"):
        state = "not_directly_comparable"
        reasons.append("different substrates change the apparent potency")
    else:
        state = "comparable_with_conditions"
        reasons.append("same endpoint and substrate; format or system differ")
    return {"state": state, "context_a": ka, "context_b": kb, "rationale": reasons}
