from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

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
    Study,
    Transformation,
)
from axis.storage import (
    EvidenceStore,
    RecordConflictError,
    RecordNotFoundError,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def make_claim(
    identifier: str = "claim-1", predicate: str = "associated_with"
) -> Claim:
    return Claim(
        identifier=identifier,
        subject=EntityRef(
            EntityKind.GENE,
            "ENSG00000112115",
            "IL17A",
            "Ensembl",
        ),
        predicate=predicate,
        object=EntityRef(
            EntityKind.DISEASE,
            "MONDO:0012050",
            "axSpA",
            "MONDO",
        ),
        knowledge_kind=KnowledgeKind.SOURCE_ASSERTION,
        provenance=Provenance(
            source_kind=SourceKind.GEO,
            source_identifier="GSE12345",
            retrieved_at=NOW,
            source_uri=("https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345"),
            checksum="sha256:example",
            transformations=(
                Transformation(
                    "geo_metadata_parser",
                    "1.0.0",
                    (("field", "title"), ("normalizer", "trim")),
                ),
            ),
        ),
        context=ClaimContext(
            tissue="peripheral blood",
            assay="RNA-seq",
            comparison="active axSpA vs healthy control",
            species="Homo sapiens",
        ),
        confidence=0.82,
    )


def first_revision(evidence_ids: tuple[str, ...] = ()) -> HypothesisRevision:
    return HypothesisRevision(
        revision=1,
        created_at=NOW,
        state=HypothesisState.DRAFT,
        description="IL17A is recurrent across independent axSpA studies.",
        rationale="Initial research question.",
        evidence_ids=evidence_ids,
    )


def test_claim_round_trip_preserves_context_and_provenance() -> None:
    claim = make_claim()

    with EvidenceStore() as store:
        store.claims.add(claim)

        assert store.claims.get(claim.identifier) == claim
        assert store.claims.list_by_subject(claim.subject) == (claim,)


def test_adding_same_claim_is_idempotent_but_mutation_is_rejected() -> None:
    claim = make_claim()

    with EvidenceStore() as store:
        store.claims.add(claim)
        store.claims.add(claim)

        with pytest.raises(RecordConflictError):
            store.claims.add(make_claim(predicate="causes"))


def test_database_reopens_without_reapplying_migrations() -> None:
    with TemporaryDirectory() as directory:
        database = Path(directory) / "evidence.duckdb"
        claim = make_claim()

        with EvidenceStore(database) as store:
            store.claims.add(claim)

        with EvidenceStore(database) as reopened:
            assert reopened.claims.get(claim.identifier) == claim


def test_hypothesis_revision_history_is_append_only() -> None:
    claim = make_claim()
    hypothesis = Hypothesis(
        identifier="hyp-1",
        title="Recurrent IL17A evidence",
        revisions=(first_revision((claim.identifier,)),),
    )

    with EvidenceStore() as store:
        store.claims.add(claim)
        store.hypotheses.add(hypothesis)
        second = HypothesisRevision(
            revision=2,
            created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
            state=HypothesisState.ACTIVE,
            description=hypothesis.current.description,
            rationale="Supported by another independent dataset.",
            evidence_ids=(claim.identifier,),
            confidence=0.7,
        )

        revised = store.hypotheses.append_revision(hypothesis.identifier, second)
        loaded = store.hypotheses.get(hypothesis.identifier)

        assert revised == loaded
        assert len(loaded.revisions) == 2
        assert loaded.revisions[0] == hypothesis.revisions[0]


def test_missing_evidence_rolls_back_hypothesis_creation() -> None:
    hypothesis = Hypothesis(
        identifier="hyp-1",
        title="Untraceable hypothesis",
        revisions=(first_revision(("missing-claim",)),),
    )

    with EvidenceStore() as store:
        with pytest.raises(RecordNotFoundError):
            store.hypotheses.add(hypothesis)

        with pytest.raises(RecordNotFoundError):
            store.hypotheses.get(hypothesis.identifier)


def test_study_round_trip_preserves_discovery_metadata() -> None:
    study = Study(
        identifier="GSE234339",
        title="RIOK3 in ankylosing spondylitis",
        summary="RNA-seq of whole blood.",
        source=SourceKind.GEO,
        organisms=("Homo sapiens",),
        experiment_type="Expression profiling by high throughput sequencing",
        sample_count=8,
        platform_ids=("GPL24676",),
        publication_ids=("PMID:38974235",),
        bioproject_id="PRJNA982001",
        provenance=Provenance(
            source_kind=SourceKind.GEO,
            source_identifier="GSE234339",
            retrieved_at=NOW,
            source_uri="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE234339",
            checksum="sha256:example",
        ),
    )

    with EvidenceStore() as store:
        store.studies.add(study)

        assert store.studies.get(study.identifier) == study
