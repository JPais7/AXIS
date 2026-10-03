import json

import pytest

from axis.api.server import ReadAPI
from axis.discovery import DiscoveryService
from axis.discovery.curation import (
    CURATED_PROJECT,
    import_curated_erap1,
    load_curated_package,
)
from axis.discovery.review import render_scientific_review, review_packet
from axis.storage import EvidenceStore, RecordNotFoundError


@pytest.fixture(scope="module")
def store():
    with EvidenceStore() as value:
        import_curated_erap1(value)
        DiscoveryService(value).create_erap1_demo()
        yield value


def test_comparison_preserves_context_assessments_and_source(store):
    api = ReadAPI(store)
    ids = ["AXIS-ERAP1-CURATED-C08", "AXIS-ERAP1-CURATED-C12", "AXIS-ERAP1-CURATED-C13"]
    result = api.get(
        f"/api/projects/{CURATED_PROJECT}/compare", {"claim_ids": [",".join(ids)]}
    )
    assert len(result["items"]) == 3
    for item, identifier in zip(result["items"], ids, strict=True):
        original = api.get(
            f"/api/claims/{identifier}", {"project_id": [CURATED_PROJECT]}
        )
        assert item["context"] == original["context"]
        assert item["assessments"] == original["assessments"]
        assert item["mechanisms"] == original["mechanisms"]
        assert item["source"] == original["source"]
        assert item["claim"]["provenance"] == original["claim"]["provenance"]
        assert item["context"]["tissue"] is None
    assert "U937" in result["items"][1]["context"]["experimental_system"]
    assert result["items"][2]["perturbations"][0]["observed_effect_claim_id"] == ids[2]
    assert "not automatically contradictions" in result["interpretation"]


@pytest.mark.parametrize(
    "suffixes", [[], ["C01"], ["C01", "C01"], ["C01", "C02", "C03", "C04", "C05"]]
)
def test_comparison_bounds(store, suffixes):
    with pytest.raises(ValueError):
        ReadAPI(store).get(
            f"/api/projects/{CURATED_PROJECT}/compare",
            {
                "claim_ids": [
                    ",".join("AXIS-ERAP1-CURATED-" + value for value in suffixes)
                ]
            },
        )


def test_comparison_isolates_project_and_accepts_four(store):
    api = ReadAPI(store)
    ids = [f"AXIS-ERAP1-CURATED-C{number:02}" for number in range(1, 5)]
    assert (
        len(
            api.get(
                f"/api/projects/{CURATED_PROJECT}/compare",
                {"claim_ids": [",".join(ids)]},
            )["items"]
        )
        == 4
    )
    with pytest.raises(RecordNotFoundError):
        api.get(
            "/api/projects/AXIS-DD-ERAP1-001/compare",
            {"claim_ids": [",".join(ids[:2])]},
        )


def test_comparison_parameter_does_not_change_existing_route_contract(store):
    with pytest.raises(ValueError):
        ReadAPI(store).get("/api/projects", {"claim_ids": ["one,two"]})


def test_review_packet_is_separate_pending_and_never_accepted(store):
    package_before = load_curated_package()
    packet = review_packet(store)
    assert packet == review_packet(store)
    assert packet["status"] == "pending_expert_review"
    assert packet["project_id"] == CURATED_PROJECT
    assert len(packet["source_assertions"]) == 13
    assert len(packet["evidence_assessments"]) == 24
    assert len(packet["mechanism_assessments"]) == 8
    for category in (
        "source_assertions",
        "evidence_assessments",
        "mechanism_assessments",
    ):
        assert all(item["reviewer_decision"] is None for item in packet[category])
    document = render_scientific_review(packet)
    assert document.count("Reviewer decision: [ ] Accept  [ ] Revise  [ ] Reject") == 45
    assert "Not reported" in document
    assert "### SOURCE ASSERTION" in document
    assert "### AXIS ASSESSMENT" in document
    assert "### MECHANISTIC ASSESSMENT" in document
    assert "ai_suggestion" in document
    assert load_curated_package() == package_before
    assert json.dumps(packet, default=str)
