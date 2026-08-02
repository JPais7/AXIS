"""Promote recurrent analytical results into immutable evidence claims."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.domain import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
    Transformation,
)
from axis.storage import EvidenceStore


@dataclass(frozen=True)
class PublishedRanking:
    ranking_path: Path
    recurrent_rows: int
    claims_added: int
    claim_ids: tuple[str, ...]


class RankingPublisher:
    """Publishes only rows explicitly satisfying the recurrence contract."""

    def publish(
        self,
        ranking_path: str | Path,
        *,
        store: EvidenceStore,
    ) -> PublishedRanking:
        path = Path(ranking_path)
        payload = path.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        summary_path = path.with_name("recurrence-analysis.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("analysis_role", "primary") != "primary":
            raise ValueError(
                "sensitivity rankings cannot be published as primary claims"
            )
        studies = tuple(str(value) for value in summary["studies"])
        retrieved_at = datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=UTC,
        )
        rows = self._recurrent_rows(path)
        claim_ids: list[str] = []
        for row in rows:
            gene = row["gene_symbol"].strip()
            adjusted = float(row["combined_adjusted_p_value"])
            identifier = (
                "axis:claim:"
                + hashlib.sha256(f"{checksum}:{gene}".encode()).hexdigest()
            )
            claim = Claim(
                identifier=identifier,
                subject=EntityRef(
                    kind=EntityKind.GENE,
                    identifier=gene,
                    label=gene,
                    namespace="HGNC-symbol",
                ),
                predicate="recurrently_associated_with",
                object=EntityRef(
                    kind=EntityKind.DISEASE,
                    identifier="axSpA",
                    label="axial spondyloarthritis",
                    namespace="AXIS",
                ),
                knowledge_kind=KnowledgeKind.AXIS_INFERENCE,
                context=ClaimContext(comparison="case versus control"),
                confidence=max(0.0, min(1.0, 1.0 - adjusted)),
                provenance=Provenance(
                    source_kind=SourceKind.AXIS_PIPELINE,
                    source_identifier=f"sha256:{checksum}",
                    retrieved_at=retrieved_at,
                    source_uri=path.resolve().as_uri(),
                    checksum=f"sha256:{checksum}",
                    transformations=(
                        Transformation(
                            name="cross-study-recurrence-ranking",
                            version="1",
                            parameters=(
                                ("studies", "|".join(studies)),
                                (
                                    "minimum_recurrent_studies",
                                    str(summary["minimum_recurrent_studies"]),
                                ),
                                ("alpha", str(summary["alpha"])),
                            ),
                        ),
                    ),
                ),
            )
            store.claims.add(claim)
            claim_ids.append(identifier)
        return PublishedRanking(
            ranking_path=path,
            recurrent_rows=len(rows),
            claims_added=len(claim_ids),
            claim_ids=tuple(claim_ids),
        )

    @staticmethod
    def _recurrent_rows(path: Path) -> tuple[dict[str, str], ...]:
        with path.open(encoding="utf-8", newline="") as source:
            return tuple(
                row
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("recurrent", "").lower() == "true"
            )
