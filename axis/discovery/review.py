"""Deterministic independent-review packet; never makes reviewer decisions."""

import json
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from axis.discovery.curation import CURATED_PROJECT, load_curated_package
from axis.discovery.service import DiscoveryService
from axis.discovery.workspace import WorkspaceService
from axis.domain import KnowledgeKind
from axis.storage import EvidenceStore


def _default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def review_packet(store: EvidenceStore) -> dict[str, Any]:
    package, digest = load_curated_package()
    traversal = DiscoveryService(store).inspect_project(CURATED_PROJECT)
    workspace = WorkspaceService(store)
    claims = [
        workspace.claim(CURATED_PROJECT, claim.identifier)
        for claim in traversal.claims
        if claim.knowledge_kind == KnowledgeKind.SOURCE_ASSERTION
    ]
    return {
        "title": "ERAP1 × axSpA Evidence Vertical v1 — independent scientific review",
        "package_id": package["package_id"],
        "package_version": package["package_version"],
        "package_checksum": digest,
        "project_id": CURATED_PROJECT,
        "status": "pending_expert_review",
        "curation_status": package["curation_status"],
        "source_assertions": [
            {**claim, "reviewer_decision": None, "reviewer_notes": ""}
            for claim in claims
        ],
        "evidence_assessments": [
            {**asdict(item), "reviewer_decision": None, "reviewer_notes": ""}
            for item in traversal.assessments
        ],
        "mechanism_assessments": [
            {
                **asdict(item),
                "underlying_claim": workspace.claim(CURATED_PROJECT, item.claim_id),
                "reviewer_decision": None,
                "reviewer_notes": "",
            }
            for item in traversal.mechanisms
        ],
    }


def render_scientific_review(packet: dict[str, Any]) -> str:
    lines = [
        "# " + packet["title"],
        "",
        "**AI-ASSISTED CURATION — PENDING EXPERT REVIEW**",
        "",
        f"Project: `{packet['project_id']}`",
        f"Package: {packet['package_version']} · "
        f"SHA-256 `{packet['package_checksum']}`",
        "",
        "No claim or interpretation has been accepted automatically. Review source "
        "extraction independently from evidence roles and mechanism classifications. "
        "Different cell systems or endpoints do not automatically "
        "establish contradiction.",
        "",
        "Reviewer: ____________________    Date: ____________________",
        "",
        "## A. Source assertions — 13 independent extraction decisions",
        "",
    ]

    def decision() -> None:
        lines.extend(
            [
                "",
                "Reviewer decision: [ ] Accept  [ ] Revise  [ ] Reject",
                "",
                "Reviewer notes: ____________________",
                "",
            ]
        )

    def context(value: dict[str, Any]) -> None:
        lines.append("**Extracted/reported context**")
        for key, item in value.items():
            lines.append(f"- {key.replace('_', ' ')}: {item or 'Not reported'}")

    def provenance(value: dict[str, Any]) -> None:
        lines.extend(
            [
                "",
                "**Provenance (stored, unchanged)**",
                "",
                "```json",
                json.dumps(value, indent=2, ensure_ascii=False, default=_default),
                "```",
            ]
        )

    limitations = {
        claim["claim_id"]: claim["limitation"] for claim in packet["source_assertions"]
    }
    for claim in packet["source_assertions"]:
        lines.extend(
            [
                f"### SOURCE ASSERTION `{claim['claim_id']}`",
                "",
                claim["statement"],
                "",
                f"KnowledgeKind: `{claim['knowledge_kind']}`",
                f"Source: [{claim['source']['source_id']}]"
                f"({claim['source']['source_uri']})",
                f"Reference: {claim['source']['title']}",
                f"Source locator: {claim['source']['locator'] or 'Not reported'}",
                "",
            ]
        )
        context(claim["context"])
        lines.extend(
            [
                "",
                f"Inclusion rationale: {claim['inclusion_rationale']}",
                f"Known limitation: {claim['limitation']}",
                "Mechanistic assessments (review separately): "
                + (
                    ", ".join(
                        f"{item['assessment_id']} ({item['classification']})"
                        for item in claim["mechanisms"]
                    )
                    or "Not assessed"
                ),
                "Evidence assessments (review separately): "
                + ", ".join(
                    f"{item['assessment_id']} ({item['role']})"
                    for item in claim["assessments"]
                ),
            ]
        )
        provenance(claim["claim"]["provenance"])
        decision()
    lines.extend(
        [
            "## B. AXIS evidence assessments — 24 independent interpretation decisions",
            "",
        ]
    )
    for assessment in packet["evidence_assessments"]:
        lines.extend(
            [
                f"### AXIS ASSESSMENT `{assessment['assessment_id']}`",
                "",
                f"Underlying claim: `{assessment['claim_id']}`",
                f"Evidence role: `{assessment['role']}`",
                "Target strategy/question/hypothesis: `"
                + str(
                    assessment["strategy_id"]
                    or assessment["question_id"]
                    or assessment["hypothesis_id"]
                )
                + "`",
                f"Reasoning: {assessment['reasoning']}",
                "Context limitation: "
                + limitations.get(
                    assessment["claim_id"], "Inspect underlying claim context"
                ),
            ]
        )
        provenance(assessment["provenance"])
        decision()
    lines.extend(
        ["## C. Mechanistic assessments — 8 independent classification decisions", ""]
    )
    for assessment in packet["mechanism_assessments"]:
        claim = assessment["underlying_claim"]
        lines.extend(
            [
                f"### MECHANISTIC ASSESSMENT `{assessment['assessment_id']}`",
                "",
                f"Underlying claim: `{assessment['claim_id']}`",
                f"Assertion/proposal: {claim['statement']}",
                f"KnowledgeKind: `{claim['knowledge_kind']}`",
                f"Classification: `{assessment['classification']}`",
                f"Classification reasoning: {assessment['reasoning']}",
                "",
            ]
        )
        context(claim["context"])
        provenance(assessment["provenance"])
        decision()
    lines.extend(
        [
            "## Review procedure",
            "",
            "1. Check each extraction against the primary reference and locator; "
            "missing context remains Not reported.",
            "2. Review each evidence role separately; accepting an extraction "
            "does not accept its interpretation.",
            "3. Review mechanism classification within the reported context; "
            "disease translation remains a proposal.",
            "4. Return the completed document to the project owners. "
            "This read-first app does not ingest decisions.",
            "5. Scientific revisions require a new reviewed package version; "
            "never overwrite the frozen v1 resource.",
            "",
        ]
    )
    return "\n".join(lines)
