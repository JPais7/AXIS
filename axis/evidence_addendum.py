"""Offline integrity and epistemic-boundary audit, not a new Decision Engine."""

import hashlib
import json
from collections import Counter
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

PREFIX = "resources/evidence-addendum/erap1-axspa/2020-2026/v1"
ELIGIBLE_ACCESS = {"FULL_TEXT_ACCESSIBLE", "METHODS_AND_RESULTS_SUFFICIENT"}


def claim_eligible(study: dict[str, Any]) -> bool:
    """Access permits curation, not expert approval or a strength judgment."""
    return (
        study["action"] == "INTEGRATE"
        and study["accessibility"] in ELIGIBLE_ACCESS
        and study["methods_sufficient"] is True
        and study.get("primary", True) is True
    )


def engagement_eligible(observation: dict[str, Any]) -> bool:
    """Functional/structural/lysate measurements never become cellular occupancy."""
    return all(
        observation.get(key) is True
        for key in (
            "intact_cell",
            "direct_or_validated_proximal_readout",
            "exposure_matched",
            "specificity_controls",
            "methods_inspected",
        )
    )


def measurements_comparable(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Conservative context match; no ratios or conversion of censored values."""
    keys = ("substrate", "endpoint", "species", "matrix", "conditions")
    return all(a.get(k) is not None and a[k] == b.get(k) for k in keys)


def read(root: Traversable, name: str) -> Any:
    return json.loads(root.joinpath(name).read_bytes())


def scientific_boundary_errors(
    studies: list[dict[str, Any]], claims: list[dict[str, Any]]
) -> list[str]:
    errors = []
    by_id = {s["id"]: s for s in studies}
    if len(by_id) != len(studies):
        errors.append("duplicate_study_ids")
    if len({c["id"] for c in claims}) != len(claims):
        errors.append("duplicate_claim_ids")
    for claim in claims:
        study = by_id.get(claim["study_id"])
        if study is None or not claim_eligible(study):
            errors.append("ineligible_source:" + claim["id"])
            continue
        if claim["review_status"] != "pending_review":
            errors.append("unauthorized_review_promotion:" + claim["id"])
        if claim["epistemic_kind"] != "source_assertion":
            errors.append("wrong_claim_kind:" + claim["id"])
        if claim.get("direct_cellular_engagement") and not engagement_eligible(
            claim["experimental_context"]
        ):
            errors.append("unsupported_engagement_promotion:" + claim["id"])
        if any(
            claim.get(key)
            for key in (
                "clinical_efficacy",
                "chemical_genetic_dependency",
                "therapeutic_direction_established",
            )
        ):
            errors.append("outside_curated_scope:" + claim["id"])
        if claim["experimental_context"] != study["context"]:
            errors.append("context_lost:" + claim["id"])
        if not claim["source_locator"]["section"]:
            errors.append("missing_locator:" + claim["id"])
    for study in studies:
        if study["action"] == "INTEGRATE" and not any(
            c["study_id"] == study["id"] for c in claims
        ):
            errors.append("integrated_without_assertions:" + study["id"])
    return errors


def audit(root: Traversable | None = None) -> dict[str, Any]:
    """Reproduce the frozen addendum from a wheel without network or local cache."""
    root = root if root is not None else files("axis").joinpath(PREFIX)
    manifest = read(root, "manifest.json")
    errors = []
    manifest_sha = hashlib.sha256(
        root.joinpath("manifest.json").read_bytes()
    ).hexdigest()
    expected = root.joinpath("manifest.sha256").read_text().split()[0]
    if manifest_sha != expected:
        errors.append("manifest_checksum_mismatch")
    for entry in manifest["files"]:
        name = entry["path"]
        if name.startswith("/") or "/" in name or name in {".", ".."}:
            errors.append("unsafe_resource_path:" + name)
            continue
        try:
            data = root.joinpath(name).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                errors.append("checksum_mismatch:" + name)
        except OSError:
            errors.append("missing_resource:" + name)
    studies = read(root, "candidate-studies.json")
    claims = read(root, "claims.json")
    impacts = read(root, "impact-assessments.json")
    decision = read(root, "decision-impact.json")
    errors.extend(scientific_boundary_errors(studies, claims))
    claim_ids = {c["id"] for c in claims}
    for impact in impacts:
        if impact["review_status"] != "pending_review":
            errors.append("unauthorized_impact_promotion:" + impact["id"])
        if not set(impact["claim_ids"]) <= claim_ids:
            errors.append("untraceable_impact:" + impact["id"])
    if decision["canonical_decision_created"]:
        errors.append("unexpected_canonical_decision")
    if decision["historical_refresh_status"] != (
        "INSUFFICIENT REFRESH COMPLETENESS TO ASSESS"
    ):
        errors.append("historical_refresh_relabelled")
    for item in [decision["critical_uncertainty"], decision["recommended_experiment"]]:
        if not set(item["claim_ids"]) <= claim_ids:
            errors.append("untraceable_decision_impact")
    return {
        "audit_kind": "bounded_addendum_not_canonical_decision_replay",
        "manifest_sha256": manifest_sha,
        "files_checked": len(manifest["files"]),
        "selected_candidates": len(studies),
        "actions": dict(sorted(Counter(s["action"] for s in studies).items())),
        "source_assertions": len(claims),
        "pending_source_assertions": sum(
            c["review_status"] == "pending_review" for c in claims
        ),
        "impact_assessments": len(impacts),
        "new_canonical_decision": False,
        "critical_uncertainty": decision["critical_uncertainty"],
        "recommended_experiment": decision["recommended_experiment"],
        "chemical_learning": decision["chemical_learning"],
        "historical_refresh_status": decision["historical_refresh_status"],
        "integrity_errors": errors,
        "verdict": "VALID_BOUNDED_PACKAGE_PENDING_REVIEW" if not errors else "INVALID",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
