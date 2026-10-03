from dataclasses import replace

import pytest

from axis.domain import ClaimContext, KnowledgeKind, SourceKind, Study, Transformation
from axis.storage import EvidenceStore
from tests.test_storage import NOW, make_claim


def test_legacy_knowledge_values_and_experimental_result() -> None:
    legacy = (
        "source_assertion",
        "axis_observation",
        "axis_inference",
        "ai_suggestion",
        "researcher_hypothesis",
    )
    assert tuple(KnowledgeKind(value).value for value in legacy) == legacy
    assert KnowledgeKind.EXPERIMENTAL_RESULT.value == "experimental_result"
    assert KnowledgeKind.AXIS_OBSERVATION != KnowledgeKind.EXPERIMENTAL_RESULT


def test_extended_context_and_experimental_result_round_trip() -> None:
    context = ClaimContext(
        cell_type="test cell",
        genotype="test genotype",
        hla_status="test HLA",
        allotype="test allotype",
        experimental_system="synthetic system",
        endpoint="synthetic endpoint",
    )
    claim = replace(
        make_claim(), context=context, knowledge_kind=KnowledgeKind.EXPERIMENTAL_RESULT
    )
    with EvidenceStore() as store:
        store.claims.add(claim)
        assert store.claims.get(claim.identifier) == claim
    assert ClaimContext().genotype is None


def test_study_transformations_round_trip() -> None:
    study = Study(
        identifier="synthetic-study",
        title="Synthetic fixture",
        summary="",
        source=SourceKind.GEO,
        provenance=replace(
            make_claim().provenance,
            retrieved_at=NOW,
            transformations=(
                Transformation("first", "1", (("a", "1"), ("a", "2"))),
                Transformation("second", "2"),
            ),
        ),
    )
    with EvidenceStore() as store:
        store.studies.add(study)
        store.studies.add(study)
        assert store.studies.get(study.identifier) == study


def test_ai_source_cannot_supply_experimental_result() -> None:
    with pytest.raises(ValueError, match="AI source"):
        replace(
            make_claim(),
            knowledge_kind=KnowledgeKind.EXPERIMENTAL_RESULT,
            provenance=replace(
                make_claim().provenance, source_kind=SourceKind.AI_MODEL
            ),
        )
