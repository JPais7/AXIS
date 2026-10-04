"""Conservative, explicit pairwise ratios; censored bounds are not point estimates."""

from dataclasses import asdict
from math import isfinite
from typing import Any

from axis.domain.pharmacology import CONCENTRATION, Assay, BioactivityMeasurement


def normalize(value: BioactivityMeasurement) -> BioactivityMeasurement:
    from dataclasses import replace

    if value.value is None or value.original_unit not in CONCENTRATION:
        return value
    factor = CONCENTRATION[value.original_unit]
    if not isfinite(value.value * factor):
        raise ValueError("concentration conversion overflow")
    return replace(
        value,
        normalized_value=value.value * factor,
        normalized_unit="nM",
        normalization_method={
            "method": "AXIS concentration conversion v1",
            "input": value.original_value,
            "input_unit": value.original_unit,
            "factor": factor,
            "output_unit": "nM",
        },
    )


def compare(
    primary: BioactivityMeasurement | None,
    comparison: BioactivityMeasurement | None,
    a: Assay | None,
    b: Assay | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "comparability_status": "Not assessed",
        "rationale": "Missing measurement",
        "ratio": None,
        "ratio_lower_bound": None,
        "ratio_upper_bound": None,
        "lower_inclusive": None,
        "upper_inclusive": None,
        "transformation": {},
    }
    if primary is None or comparison is None or a is None or b is None:
        return base
    reasons = []
    if primary.compound_id != comparison.compound_id:
        reasons.append("different chemical identities")
    if (
        primary.chemical_form_id is None
        or primary.chemical_form_id != comparison.chemical_form_id
    ):
        reasons.append("tested chemical form not explicitly matched")
    if primary.endpoint != comparison.endpoint:
        reasons.append("different endpoints")
    if primary.endpoint not in {"IC50", "Ki", "Kd"}:
        reasons.append("endpoint does not establish inhibitory/binding selectivity")
    if a.assay_type not in {"biochemical_activity", "binding"}:
        reasons.append("not a biochemical/binding comparison")
    for name in (
        "assay_type",
        "assay_format",
        "biological_system",
        "taxon_id",
        "substrate",
        "detection_method",
        "source_snapshot_id",
    ):
        x, y = getattr(a, name), getattr(b, name)
        if x is None or y is None or x != y:
            reasons.append(f"unknown or different {name}")
    # Exact assay constructs, not merely two strings reading 'His-tag'.
    if a.construct_mapping_status != "exact" or b.construct_mapping_status != "exact":
        reasons.append("constructs not exactly resolved")
    conditions_a = {c.name: asdict(c) for c in a.conditions}
    conditions_b = {c.name: asdict(c) for c in b.conditions}
    if (
        not {
            "buffer",
            "pH",
            "temperature",
            "substrate concentration",
            "enzyme concentration",
            "incubation time",
        }.issubset(conditions_a)
        or conditions_a != conditions_b
        or any(c.value is None for c in (*a.conditions, *b.conditions))
    ):
        reasons.append("missing or different conditions")
    p, q = normalize(primary), normalize(comparison)
    if p.normalized_value is None or q.normalized_value is None:
        reasons.append("no compatible concentration values")
    if reasons:
        return base | {
            "comparability_status": "Not directly comparable",
            "rationale": "; ".join(reasons),
        }
    assert p.normalized_value is not None and q.normalized_value is not None
    r = q.normalized_value / p.normalized_value
    result = base | {
        "comparability_status": "Comparable",
        "rationale": "Explicit compatible inputs; not therapeutic efficacy",
        "transformation": {
            "method": "AXIS pairwise selectivity v1",
            "numerator": q.id,
            "denominator": p.id,
            "units": "nM",
            "quotient_at_threshold": r,
        },
    }
    x, y = p.relation_operator, q.relation_operator
    if x == y == "=":
        result["ratio"] = r
    elif x in {"=", "<", "<="} and y in {"=", ">", ">="}:
        result.update(
            ratio_lower_bound=r, lower_inclusive=x in {"=", "<="} and y in {"=", ">="}
        )
    elif x in {"=", ">", ">="} and y in {"=", "<", "<="}:
        result.update(
            ratio_upper_bound=r, upper_inclusive=x in {"=", ">="} and y in {"=", "<="}
        )
    else:
        result.update(
            comparability_status="Not directly comparable",
            rationale="Approximate or indeterminate two-sided censoring",
            transformation={},
        )
    return result
