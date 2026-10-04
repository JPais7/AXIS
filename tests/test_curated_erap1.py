from pathlib import Path

from axis.discovery import DiscoveryService
from axis.discovery.curation import import_curated_erap1, load_curated_package
from axis.domain import KnowledgeKind, MechanismClassification, PerturbationStatus
from axis.storage import EvidenceStore


def test_curated_package_has_atomic_source_grounded_claims() -> None:
    package, digest = load_curated_package()
    assert len(digest) == 64
    assert len(package["sources"]) == 6
    assert len(package["claims"]) == 13
    identifiers = {source["source_id"] for source in package["sources"]}
    for source in package["sources"]:
        assert source["source_id"].startswith("PMID:")
        assert source["retrieved_at"]
        assert source["doi"]
        assert len(source["response_sha256"]) == 64
    assert all(claim["source_id"] in identifiers for claim in package["claims"])


def test_curated_import_round_trip_and_demo_separation(tmp_path: Path) -> None:
    database = tmp_path / "curated.duckdb"
    with EvidenceStore(database) as store:
        demo = DiscoveryService(store).create_erap1_demo()
        curated = import_curated_erap1(store)
        assert import_curated_erap1(store) == curated
        assert demo.project.project_id != curated.project.project_id
        assert {claim.identifier for claim in demo.claims}.isdisjoint(
            claim.identifier for claim in curated.claims
        )
        assert len(curated.assessments) == 24
        assert len(curated.mechanisms) == 8
        assert len(curated.perturbations) == 3
        assert all(
            item.status == PerturbationStatus.PERFORMED
            for item in curated.perturbations
        )
        assert all(item.observed_effect_claim_id for item in curated.perturbations)
        assert len(curated.outcomes) == 2
        for claim in curated.claims:
            assert claim.provenance.retrieved_at.tzinfo is not None
            assert claim.provenance.transformations
            if claim.knowledge_kind == KnowledgeKind.SOURCE_ASSERTION:
                assert claim.provenance.source_identifier.startswith("PMID:")
                assert claim.provenance.source_uri
                assert claim.provenance.checksum
        assert curated.experiments[0].knowledge_kind == KnowledgeKind.AI_SUGGESTION
        assert (
            sum(
                item.classification == MechanismClassification.HYPOTHESIZED
                for item in curated.mechanisms
            )
            == 1
        )
    with EvidenceStore(database) as store:
        assert (
            DiscoveryService(store).inspect_project(curated.project.project_id)
            == curated
        )


def test_curation_preserves_disease_and_assay_context() -> None:
    with EvidenceStore() as store:
        curated = import_curated_erap1(store)
        claims = {claim.identifier: claim for claim in curated.claims}
        assert "Ankylosing spondylitis" in curated.pair.indication_scope
        assert "unassessed" in curated.pair.indication_scope
        assert "40:01" in claims["AXIS-ERAP1-CURATED-C02"].context.hla_status
        assert (
            "viral"
            in claims["AXIS-ERAP1-CURATED-C07"].context.experimental_system.lower()
        )
        assert "U937" in claims["AXIS-ERAP1-CURATED-C13"].context.experimental_system
        assert not any(
            claim.knowledge_kind == KnowledgeKind.EXPERIMENTAL_RESULT
            for claim in curated.claims
        )
