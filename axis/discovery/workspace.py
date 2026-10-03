"""Read projections and transparent corpus-scoped states for the workspace."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from axis.discovery.service import DiscoveryService
from axis.domain import Claim, KnowledgeKind
from axis.storage import EvidenceStore, RecordNotFoundError

DOMAIN_LABELS = {
    "human_genetics": "Human Genetics",
    "biological_function": "Biological Function",
    "hla_mechanism": "HLA-B27 / Mechanism",
    "perturbation_evidence": "Perturbation Evidence",
    "disease_pharmacology": "Disease-Relevant Pharmacology",
}


def claim_metadata(claim: Claim) -> dict[str, str]:
    return dict(
        parameter
        for transformation in claim.provenance.transformations
        for parameter in transformation.parameters
    )


def claim_summary(claim: Claim) -> dict[str, Any]:
    metadata = claim_metadata(claim)
    return {
        "claim_id": claim.identifier,
        "statement": metadata.get(
            "statement",
            f"{claim.subject.label} — "
            f"{claim.predicate.replace('_', ' ')} — {claim.object.label}",
        ),
        "knowledge_kind": claim.knowledge_kind.value,
        "source_id": claim.provenance.source_identifier,
        "domain": metadata.get("domain", "proposal"),
        "limitation": metadata.get("limitation", ""),
        "context": asdict(claim.context),
    }


class WorkspaceService:
    """All scientific interpretation stays on the AXIS service side."""

    def __init__(self, store: EvidenceStore) -> None:
        self.store = store
        self.discovery = DiscoveryService(store)

    def project(self, project_id: str) -> dict[str, Any]:
        project, pair = self.discovery.project_identity(project_id)
        first, total = self.store.projects.evidence_page(project_id, limit=1)
        metadata = claim_metadata(first[0]) if first else {}
        return {
            "project": asdict(project),
            "pair": asdict(pair),
            "project_kind": "curated" if metadata.get("package_id") else "development",
            "package_version": metadata.get("package_version"),
            "curation_status": metadata.get("curation_status", "Development fixture"),
            "coverage": metadata.get(
                "corpus_scope",
                "Proposal-only development fixture; no imported evidence",
            ),
            "counts": {
                "claims": total,
                "mechanisms": self.store.mechanistic_assessments.count(project_id),
                "perturbations": self.store.perturbations.count(project_id),
                "strategies": self.store.strategies.count(project_id),
                "questions": self.store.questions.count(project_id),
                "experiments": self.store.proposed_experiments.count(project_id),
            },
            "matrix": self.matrix(project_id),
        }

    def matrix(self, project_id: str) -> list[dict[str, Any]]:
        domains = {
            item["domain"]: item
            for item in self.store.projects.evidence_domains(project_id)
        }
        result = []
        for domain, label in DOMAIN_LABELS.items():
            item = domains.get(domain)
            if item is None:
                state, explanation = (
                    "not_assessed",
                    "This domain has not been assessed for this project.",
                )
            elif item["increasing"] and item["decreasing"]:
                state = "mixed_context_dependent"
                explanation = (
                    "Indexed observations include increasing and decreasing endpoints "
                    "across stored contexts; this is not an automatic "
                    "contradiction verdict."
                )
            elif item["sources"] == 1:
                state, explanation = (
                    "limited_evidence",
                    "The curated domain contains one primary source; "
                    "this is a coverage description, not a truth score.",
                )
            else:
                state, explanation = (
                    "evidence_available",
                    "Source assertions are available in the curated corpus; "
                    "association and mechanism do not establish clinical benefit.",
                )
            result.append(
                {
                    "domain": domain,
                    "label": label,
                    "state": state,
                    "claim_count": item["claims"] if item else 0,
                    "source_count": item["sources"] if item else 0,
                    "explanation": explanation,
                    "methodology_version": "corpus-state-v1",
                }
            )
        return result

    def evidence(
        self, project_id: str, limit: int, offset: int, domain: str | None = None
    ) -> dict[str, Any]:
        if domain is not None and domain not in DOMAIN_LABELS and domain != "proposal":
            raise ValueError("unknown evidence domain")
        claims, total = self.store.projects.evidence_page(
            project_id, limit=limit, offset=offset, domain=domain
        )
        return page([claim_summary(claim) for claim in claims], total, limit, offset)

    def claim(self, project_id: str, claim_id: str) -> dict[str, Any]:
        claim = self.store.projects._require_claim(project_id, claim_id)
        metadata = claim_metadata(claim)
        assessments = self.store.evidence_assessments.list_for_claim(
            project_id, claim_id, limit=100
        )
        mechanisms = self.store.mechanistic_assessments.list_for_claim(
            project_id, claim_id, limit=100
        )
        return {
            **claim_summary(claim),
            "claim": asdict(claim),
            "assessments": [asdict(item) for item in assessments],
            "mechanisms": [asdict(item) for item in mechanisms],
            "assessment_limit": 100,
            "assessments_may_be_truncated": len(assessments) == 100
            or len(mechanisms) == 100,
            "source": {
                "source_id": claim.provenance.source_identifier,
                "source_kind": claim.provenance.source_kind.value,
                "title": metadata.get(
                    "source_title", claim.provenance.source_identifier
                ),
                "doi": metadata.get("source_doi"),
                "source_uri": claim.provenance.source_uri,
                "retrieved_at": claim.provenance.retrieved_at,
                "locator": metadata.get("source_locator"),
                "access": metadata.get("source_access"),
            },
            "package_version": metadata.get("package_version"),
            "inclusion_rationale": metadata.get("inclusion_rationale"),
            "curation_status": metadata.get("curation_status"),
            "is_observational_evidence": claim.knowledge_kind
            in (
                KnowledgeKind.SOURCE_ASSERTION,
                KnowledgeKind.AXIS_OBSERVATION,
                KnowledgeKind.EXPERIMENTAL_RESULT,
            ),
        }

    def mechanisms(self, project_id: str, limit: int, offset: int) -> dict[str, Any]:
        assessments = self.store.mechanistic_assessments.list_for_project(
            project_id, limit=limit, offset=offset
        )
        items = [
            {
                "assessment": asdict(item),
                "claim": asdict(self.store.claims.get(item.claim_id)),
                "summary": claim_summary(self.store.claims.get(item.claim_id)),
            }
            for item in assessments
        ]
        return page(
            items, self.store.mechanistic_assessments.count(project_id), limit, offset
        )

    def compare(self, project_id: str, claim_ids: list[str]) -> dict[str, Any]:
        """Side-by-side original records, with no reconciliation verdict."""
        if not 2 <= len(claim_ids) <= 4 or len(set(claim_ids)) != len(claim_ids):
            raise ValueError("comparison requires 2–4 distinct project claim IDs")
        self.store.projects.get(project_id)
        items = []
        for claim_id in claim_ids:
            detail = self.claim(project_id, claim_id)
            perturbations = self.store.perturbations.for_effect(project_id, claim_id)
            items.append(
                {
                    **detail,
                    "perturbations": [asdict(item) for item in perturbations],
                    "perturbation_limit": 100,
                    "perturbations_may_be_truncated": len(perturbations) == 100,
                }
            )
        return {
            "project_id": project_id,
            "items": items,
            "interpretation": "Original contexts and stored assessments only; "
            "different observations are not automatically contradictions.",
        }

    def sources(self, project_id: str, limit: int, offset: int) -> dict[str, Any]:
        items, total = self.store.projects.source_page(
            project_id, limit=limit, offset=offset
        )
        return page(list(items), total, limit, offset)

    def source(
        self, project_id: str, source_id: str, limit: int, offset: int
    ) -> dict[str, Any]:
        first = self.store.claims.list_by_source(
            source_id, project_id=project_id, limit=1
        )
        if not first:
            raise RecordNotFoundError("source is not present in this project")
        claims = self.store.claims.list_by_source(
            source_id, project_id=project_id, limit=limit, offset=offset
        )
        detail = self.claim(project_id, first[0].identifier)
        return {
            "source": detail["source"],
            "claims": [claim_summary(item) for item in claims],
            "limit": limit,
            "offset": offset,
            "total": self.store.claims.count_by_source(
                source_id, project_id=project_id
            ),
            "has_more": offset + len(claims)
            < self.store.claims.count_by_source(source_id, project_id=project_id),
            "projects": self.store.projects.source_projects(source_id),
            "transformations": asdict(first[0].provenance)["transformations"],
            "package_version": detail["package_version"],
        }


def page(items: list[Any], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }
