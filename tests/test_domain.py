import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

from axis.domain import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    Hypothesis,
    HypothesisRevision,
    HypothesisState,
    KnowledgeKind,
    Provenance,
    SourceKind,
    Transformation,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def gene() -> EntityRef:
    return EntityRef(EntityKind.GENE, "ENSG00000112115", "IL17A", "Ensembl")


def disease() -> EntityRef:
    return EntityRef(EntityKind.DISEASE, "MONDO:0012050", "axSpA", "MONDO")


def provenance() -> Provenance:
    return Provenance(
        source_kind=SourceKind.GEO,
        source_identifier="GSE12345",
        source_uri="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345",
        retrieved_at=NOW,
        checksum="sha256:example",
        transformations=(
            Transformation("geo_metadata_parser", "1.0.0", (("field", "title"),)),
        ),
    )


class ClaimTests(unittest.TestCase):
    def test_contextual_traceable_claim_is_valid(self) -> None:
        claim = Claim(
            identifier="claim-1",
            subject=gene(),
            predicate="associated_with",
            object=disease(),
            knowledge_kind=KnowledgeKind.SOURCE_ASSERTION,
            provenance=provenance(),
            context=ClaimContext(
                tissue="peripheral blood",
                assay="RNA-seq",
                comparison="active axSpA vs healthy control",
                species="Homo sapiens",
            ),
            confidence=0.82,
        )

        self.assertEqual(claim.context.assay, "RNA-seq")
        self.assertEqual(claim.provenance.source_identifier, "GSE12345")

    def test_claim_rejects_confidence_outside_unit_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            Claim(
                identifier="claim-1",
                subject=gene(),
                predicate="associated_with",
                object=disease(),
                knowledge_kind=KnowledgeKind.AXIS_INFERENCE,
                provenance=provenance(),
                confidence=1.01,
            )

    def test_provenance_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            Provenance(
                source_kind=SourceKind.GEO,
                source_identifier="GSE12345",
                retrieved_at=datetime(2026, 7, 27, 12, 0),
            )

    def test_claim_is_immutable(self) -> None:
        claim = Claim(
            identifier="claim-1",
            subject=gene(),
            predicate="associated_with",
            object=disease(),
            knowledge_kind=KnowledgeKind.SOURCE_ASSERTION,
            provenance=provenance(),
        )

        with self.assertRaises(FrozenInstanceError):
            claim.predicate = "causes"  # type: ignore[misc]


class HypothesisTests(unittest.TestCase):
    def test_revision_appends_without_overwriting_history(self) -> None:
        first = HypothesisRevision(
            revision=1,
            created_at=NOW,
            state=HypothesisState.DRAFT,
            description="IL17A is recurrent across independent axSpA studies.",
            rationale="Initial research question.",
        )
        hypothesis = Hypothesis("hyp-1", "Recurrent IL17A evidence", (first,))
        second = HypothesisRevision(
            revision=2,
            created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
            state=HypothesisState.ACTIVE,
            description=first.description,
            rationale="Supported by two independent datasets.",
            evidence_ids=("claim-1", "claim-2"),
            confidence=0.7,
        )

        revised = hypothesis.revise(second)

        self.assertEqual(len(hypothesis.revisions), 1)
        self.assertEqual(len(revised.revisions), 2)
        self.assertEqual(revised.current.state, HypothesisState.ACTIVE)

    def test_revision_sequence_cannot_have_gaps(self) -> None:
        revision = HypothesisRevision(
            revision=2,
            created_at=NOW,
            state=HypothesisState.DRAFT,
            description="Description",
            rationale="Rationale",
        )

        with self.assertRaisesRegex(ValueError, "sequential"):
            Hypothesis("hyp-1", "Title", (revision,))


if __name__ == "__main__":
    unittest.main()
