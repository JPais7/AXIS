"""Synthetic future observations test machinery, never EAST-1 predictions."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from axis.api.server import ReadAPI
from axis.storage import EvidenceStore
from axis.validation import prospective, temporal
from axis.validation.package import PackageError, sha256_file

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "axis/resources/validation/prospective/erap1-east1/v1"


@pytest.fixture
def bundle() -> dict[str, Any]:
    return prospective.load(PACKAGE)


def future(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "SYNTHETIC:FUTURE-1",
        "url": "https://example.org/synthetic",
        "content_sha256": "0" * 64,
        "first_public_date": "2026-11-01",
        "intervention": "GRWD0715",
        "knowledge_kind": "source_assertion",
        "evidence_class": "peer_reviewed_primary",
        "review_status": "pending_review",
        "methods_and_data_available": True,
        "discriminator_id": "D1",
        "observation": "SYNTHETIC ONLY: interpretable sustained engagement",
        "rationale": "SYNTHETIC ONLY: methods and controls meet D1 conditions",
        "outcome": "strengthens",
        **overrides,
    }


def test_deterministic_offline_replay(bundle: dict[str, Any]) -> None:
    assert prospective.replay(bundle) == bundle["t0-state.json"]
    assert prospective.replay(bundle) == prospective.replay(deepcopy(bundle))


def test_future_reveal_preserves_t0_and_files(bundle: dict[str, Any]) -> None:
    before = deepcopy(bundle)
    hashes = {p.name: sha256_file(p) for p in PACKAGE.iterdir() if p.is_file()}
    prospective.reveal(bundle, future())
    assert bundle == before
    assert hashes == {p.name: sha256_file(p) for p in PACKAGE.iterdir() if p.is_file()}


def test_postcutoff_source_rejected(bundle: dict[str, Any]) -> None:
    bundle["source-index.json"]["sources"][0]["available_by"] = "2026-10-06"
    with pytest.raises(PackageError, match="post-cutoff"):
        prospective.replay(bundle)


def test_undated_source_rejected(bundle: dict[str, Any]) -> None:
    bundle["source-index.json"]["sources"][0]["available_by"] = None
    with pytest.raises(PackageError, match="undated"):
        prospective.replay(bundle)


def test_retrieved_after_freeze_rejected(bundle: dict[str, Any]) -> None:
    bundle["source-index.json"]["sources"][0]["retrieved_at"] = (
        "2026-10-06T00:00:00+00:00"
    )
    with pytest.raises(PackageError, match="after freeze"):
        prospective.replay(bundle)


def test_sponsor_evidence_cannot_be_upgraded(bundle: dict[str, Any]) -> None:
    claim = next(
        c for c in bundle["evidence-snapshot.json"]["claims"] if c["id"] == "S1"
    )
    claim["evidence_class"] = "peer_reviewed_primary"
    with pytest.raises(PackageError, match="class upgraded"):
        prospective.replay(bundle)


def test_abstract_is_not_adjudicated_result(bundle: dict[str, Any]) -> None:
    bundle["evidence-snapshot.json"]["claims"][0]["knowledge_kind"] = (
        "experimental_result"
    )
    with pytest.raises(PackageError, match="promoted"):
        prospective.replay(bundle)


@pytest.mark.parametrize("intervention", ["Maben compound 2", "DG013A", "GRWD5769"])
def test_no_cross_compound_engagement(
    bundle: dict[str, Any], intervention: str
) -> None:
    with pytest.raises(PackageError, match="another compound"):
        prospective.reveal(bundle, future(intervention=intervention))


def test_t0_cross_intervention_rejected(bundle: dict[str, Any]) -> None:
    bundle["evidence-snapshot.json"]["claims"][0]["intervention"] = "Maben compound 3"
    with pytest.raises(PackageError, match="transfer"):
        prospective.replay(bundle)


def test_every_scenario_and_discriminator_is_mapped(bundle: dict[str, Any]) -> None:
    scenarios = bundle["outcome-scenarios.json"]["items"]
    assert {s["id"] for s in scenarios} == set("ABCDEFG")
    for row in scenarios:
        assert row["uncertainty_ids"] and row["consequence"]
    for d in bundle["prospective-discriminators.json"]["items"]:
        assert set(d["consequences"]) == {
            "strengthens",
            "weakens",
            "ambiguous",
            "non_interpretable",
        }
    assert "not target engagement" in scenarios[1]["interpretation"]
    assert "does not universally disprove" in scenarios[3]["interpretation"]


@pytest.mark.parametrize("outcome", ["ambiguous", "non_interpretable"])
def test_non_directional_reveal(bundle: dict[str, Any], outcome: str) -> None:
    result = prospective.reveal(bundle, future(outcome=outcome))
    assert result["causal_diff"]["decision_changed"] == "no"
    assert (
        result["proposed_case_state"]["uncertainties"]
        == prospective.replay(bundle)["uncertainties"]
    )


def test_sponsor_and_missing_methods_keep_uncertainty_open(
    bundle: dict[str, Any],
) -> None:
    for overrides in [
        {"evidence_class": "sponsor_reported"},
        {"methods_and_data_available": False},
    ]:
        result = prospective.reveal(bundle, future(**overrides))
        assert result["interpretation"] == "ambiguous"
        assert result["causal_diff"]["decision_changed"] == "no"


def test_partial_t1_without_final_clinical_outcome(bundle: dict[str, Any]) -> None:
    result = prospective.reveal(bundle, future())
    assert (
        result["proposed_case_state"]["uncertainties"]["U1"]["status"]
        == "partially_resolved"
    )
    assert result["proposed_case_state"]["uncertainties"]["U4"]["status"] == "open"
    assert result["review_status"] == "pending_review"
    assert result["canonical_decision_state_update"] is None
    assert result["causal_diff"]["source_id"] == "SYNTHETIC:FUTURE-1"
    assert result["causal_diff"]["proposal_only"]


def test_partial_chain_and_causal_diff(bundle: dict[str, Any]) -> None:
    t1 = prospective.reveal(bundle, future())
    t2 = prospective.reveal(
        bundle,
        future(
            id="SYNTHETIC:FUTURE-2",
            first_public_date="2026-12-01",
            discriminator_id="D2",
        ),
        [t1],
    )
    assert t2["sequence"] == 2
    assert t2["parent_fingerprint"] == t1["fingerprint"]
    assert set(t2["causal_diff"]["uncertainties"]) == {"U2", "U3"}
    assert t2["t0_fingerprint"] == prospective.replay(bundle)["fingerprint"]


def test_reveal_chain_tamper_rejected(bundle: dict[str, Any]) -> None:
    t1 = prospective.reveal(bundle, future())
    t1["interpretation"] = "weakens"
    with pytest.raises(PackageError, match="chain"):
        prospective.reveal(bundle, future(id="SYNTHETIC:2"), [t1])


def test_reveal_dates_follow_public_order(bundle: dict[str, Any]) -> None:
    t1 = prospective.reveal(bundle, future())
    with pytest.raises(PackageError, match="release order"):
        prospective.reveal(
            bundle, future(id="SYNTHETIC:2", first_public_date="2026-10-20"), [t1]
        )
    with pytest.raises(PackageError, match="backfill"):
        prospective.reveal(bundle, future(first_public_date="2026-10-05"))


def test_duplicate_reveal_rejected(bundle: dict[str, Any]) -> None:
    t1 = prospective.reveal(bundle, future())
    with pytest.raises(PackageError, match="duplicate"):
        prospective.reveal(bundle, future(), [t1])


def test_review_cannot_self_approve(bundle: dict[str, Any]) -> None:
    with pytest.raises(PackageError, match="approve"):
        prospective.reveal(bundle, future(review_status="accepted"))
    bundle["case.json"]["hypotheses"][0]["review_status"] = "accepted"
    with pytest.raises(PackageError, match="self-approve"):
        prospective.replay(bundle)


def test_no_clinical_trial_prediction_or_scores(bundle: dict[str, Any]) -> None:
    assert all(h["status"] == "unresolved" for h in bundle["case.json"]["hypotheses"])
    assert "probability" not in temporal.canonical(bundle)
    assert not bundle["case.json"]["commercialization_blocker"]


def test_changed_resource_rejected(tmp_path: Path) -> None:
    import shutil

    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    (target / "case.json").write_text("{}")
    with pytest.raises(PackageError, match="resource changed"):
        prospective.load(target)


def test_history_preserved(bundle: dict[str, Any]) -> None:
    case = bundle["case.json"]
    ref = case["canonical_decision"]
    assert sha256_file(ROOT / ref["path"]) == ref["sha256"]
    for name, item in case["baseline"]["resource_manifests"].items():
        assert sha256_file(ROOT / name) == item["sha256"]
    assert json.loads((ROOT / ref["path"]).read_text())["decision"]["id"] == ref["id"]
    assert not case["baseline"]["recent_evidence_addendum_on_main"]


def test_read_only_existing_api_exposes_frozen_case(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    db = tmp_path / "view.duckdb"
    with EvidenceStore(db):
        pass
    with EvidenceStore(db, read_only=True) as store:
        api = ReadAPI(store)
        case_id = bundle["case.json"]["case_id"]
        assert case_id in {
            c["case_id"] for c in api.get("/api/benchmarks", {})["items"]
        }
        result = api.get(f"/api/benchmarks/{case_id}", {})
        assert result["prospective"]["reveals"] == []
        assert result["prospective"]["state"] == prospective.replay(bundle)
