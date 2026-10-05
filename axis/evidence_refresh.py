"""Study-specific integrity and fail-closed acceptance audit of the ERAP1 refresh.

This is not a relevance classifier, evidence assessment or Decision Engine.
Replaying an incomplete package must reproduce its NO-GO, not invent v2.
"""

import gzip
import hashlib
import json
from collections import Counter
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

PREFIX = "resources/evidence-refresh/erap1-axspa/2020-2026/v1"
PROTOCOL_SHA = "174ea4f7bde09ab435f56655f7bbed3b97edb7813fe6f080ecff88e28fef66bc"
FINAL_STATES = {
    "included",
    "excluded",
    "duplicate",
    "already_indexed",
    "historical_evidence_gap",
}


def read_json(root: Traversable, name: str) -> Any:
    content = root.joinpath(name).read_bytes()
    if name.endswith(".gz"):
        content = gzip.decompress(content)
    return json.loads(content)


def acceptance_blockers(
    unresolved_screening: int,
    supplemental_candidates_pending: bool,
    material_fulltext_pending: bool,
    evidence_set_frozen: bool,
    decision_v2_present: bool,
    causal_diff_present: bool,
    integrity_passed: bool,
) -> list[str]:
    """Scientific direction cannot affect eligibility for publication."""
    conditions = {
        "material_screening_backlog": unresolved_screening > 0,
        "supplemental_candidates_not_integrated": supplemental_candidates_pending,
        "material_fulltext_unresolved": material_fulltext_pending,
        "evidence_set_not_frozen": not evidence_set_frozen,
        "DecisionState_v2_absent": not decision_v2_present,
        "causal_diff_absent": not causal_diff_present,
        "resource_integrity_failed": not integrity_passed,
    }
    return [name for name, failed in conditions.items() if failed]


def audit(root: Traversable | None = None) -> dict[str, Any]:
    """Load only packaged resources; no network, cwd, local cache or mutations."""
    root = root if root is not None else files("axis").joinpath(PREFIX)
    manifest = read_json(root, "continuation/integrity-manifest.json")
    errors = []
    for entry in manifest["files"]:
        name = entry["path"]
        if name.startswith("/") or ".." in name.split("/"):
            errors.append("unsafe_resource_path:" + name)
            continue
        try:
            data = root.joinpath(name).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                errors.append("checksum_mismatch:" + name)
        except (OSError, FileNotFoundError):
            errors.append("missing_resource:" + name)
    fingerprint = hashlib.sha256(
        root.joinpath("protocol.json").read_bytes()
    ).hexdigest()
    if fingerprint != PROTOCOL_SHA:
        errors.append("frozen_protocol_changed")
    screening = read_json(root, "screening.json")
    counts = dict(sorted(Counter(item["state"] for item in screening).items()))
    unresolved = sum(item["state"] not in FINAL_STATES for item in screening)
    reviews = read_json(root, "continuation/study-reviews.json")
    claims = [claim for study in reviews["studies"] for claim in study["claims"]]
    if any(claim["review_status"] != "pending_review" for claim in claims):
        errors.append("unauthorized_review_promotion")
    log = read_json(root, "search-log.json")
    families = {
        row["family"]
        for row in log
        if row["source"] in {"PubMed", "Europe PMC"}
        and row["pagination"] == "complete"
        and not row["errors"]
    }
    source_records = read_json(root, "records.json.gz")
    unique = read_json(root, "unique-records.json")
    openalex = read_json(root, "continuation/openalex.json.gz")
    trials = read_json(root, "continuation/clinical-trials.json")
    preprints = read_json(root, "continuation/preprints.json")
    registry_ids = [
        s["protocolSection"]["identificationModule"]["nctId"] for s in trials["studies"]
    ]
    blockers = acceptance_blockers(
        unresolved, True, True, False, False, False, not errors
    )
    return {
        "audit_kind": "partial_refresh_integrity_and_acceptance_not_decision_replay",
        "protocol_fingerprint": fingerprint,
        "query_families_completed": len(families),
        "query_families_total": 8,
        "checkpoint_occurrences": len(source_records),
        "checkpoint_unique_records": len(unique),
        "checkpoint_duplicate_occurrences": len(source_records) - len(unique),
        "checkpoint_screening_counts": counts,
        "unresolved_checkpoint_screening": unresolved,
        "supplemental_screening": "not_complete_not_deduplicated_into_checkpoint",
        "openalex_records": len(openalex["records"]),
        "openalex_pagination": openalex["pagination"],
        "preprint_records": len(preprints["resultList"]["result"]),
        "registry_records": len(trials["studies"]),
        "registry_pagination": trials["pagination"],
        "registry_ids": registry_ids,
        "partial_study_reviews": len(reviews["studies"]),
        "draft_atomic_claims": len(claims),
        "draft_claims_pending_review": sum(
            c["review_status"] == "pending_review" for c in claims
        ),
        "new_claims_imported": 0,
        "DecisionState_v2": "not_created",
        "causal_decision_diff": "not_created",
        "integrity_errors": errors,
        "manifest_file_count": len(manifest["files"]),
        "manifest_bytes": sum(entry["bytes"] for entry in manifest["files"]),
        "blockers": blockers,
        "overall_decision_impact": "INSUFFICIENT REFRESH COMPLETENESS TO ASSESS",
        "verdict": "NOT READY FOR MERGE" if blockers else "READY FOR MERGE",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
