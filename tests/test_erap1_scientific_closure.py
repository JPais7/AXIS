"""Scientific refusal is a valid outcome, not an invented stable AFTER state."""

import json
import shutil
import socket
from pathlib import Path

import pytest

from axis.evidence_integration import digest, eligible_date, verify_package
from scripts.close_erap1_data_rich import (
    BASE,
    OUTPUT,
    domain_claim,
    read,
    replay_closure,
    selectivity_replay,
    verify_closure,
)


def test_evidence_identity() -> None:
    records = {r["accession"]: r for r in read(BASE / "data-access.json")}
    assert len(records) == 7
    for accession in ("PXD054491", "PXD054494", "PXD060572", "PXD060575"):
        assert "100964" in json.dumps(records[accession]["references"])
    assert "70056" in json.dumps(records["PXD066752"]["references"])


def test_structures_not_cellular_engagement() -> None:
    claims = read(OUTPUT / "integrated-claims.json")["claims"]
    structure_claims = [c for c in claims if c["source_class"] == "structural database"]
    assert len(structure_claims) == 12
    assert all(domain_claim(c).subject.identifier == "Q9NZ08" for c in structure_claims)
    assert all(
        "not a computational pose" in domain_claim(c).predicate
        for c in structure_claims
    )
    assert all("geometry only" in c["scope"] for c in structure_claims)


def test_chemistry_historical_source_identity_unchanged() -> None:
    chemical = read(BASE / "chemical-datasets.json")
    assert len(chemical["compounds"]) == 63
    for c in chemical["compounds"]:
        assert c["original_smiles"] == c["source_row"]["SMILES"]
        assert c["review_state"] == "pending_review"
    assert verify_package(BASE)["review_state"] == "pending_review"


def test_measurement_context_not_borrowed() -> None:
    assays = {a["id"]: a for a in read(OUTPUT / "assay-comparability.json")["assays"]}
    assert assays["hry-2024-cell"]["fields"]["duration"]["value"] == "40 h"
    for name in ("bradshaw-2026-cell", "tinworth-2026-cell"):
        a = assays[name]
        assert a["fields"]["duration"] == {"state": "INACCESSIBLE", "value": None}
        assert a["pooling"].startswith("REFUSED")
    assert (
        assays["tinworth-2026-cell"]["fields"]["substrate"]["state"]
        == "PARTIALLY VERIFIED"
    )


def test_selectivity_real_existing_rules() -> None:
    for row in selectivity_replay().values():
        result = row["axis_observation"]
        assert result["comparability_status"] == "Not directly comparable"
        assert "substrate" in result["rationale"]
        assert result["ratio"] is None
        assert result["ratio_lower_bound"] is None
        assert row["inputs"]["counter_measurement"]["relation_operator"] == ">"


def test_temporal_integrity() -> None:
    adjudication = read(OUTPUT / "source-adjudication.json")
    assert adjudication["cutoff"] == "2026-10-05"
    for study in adjudication["publication_identity"]:
        assert eligible_date(study["first_publication_date"])
    assert not eligible_date("2026-10-06")


def test_source_class_separate_from_epistemic_kind() -> None:
    claims = read(OUTPUT / "integrated-claims.json")["claims"]
    by_id = {domain_claim(c).identifier: c for c in claims}
    sponsor = by_id["closure:claim:east-sponsor"]
    assert sponsor["source_class"] == "sponsor-reported communication"
    assert domain_claim(sponsor).knowledge_kind == "source_assertion"
    registry = by_id["closure:claim:east-registry"]
    assert registry["source_class"] == "trial registry"
    assert domain_claim(registry).knowledge_kind == "axis_observation"
    assert all(c["review_state"] == "pending_review" for c in claims)


def test_perturbation_ko_not_drug() -> None:
    claims = read(OUTPUT / "integrated-claims.json")
    by_id = {domain_claim(c).identifier: c for c in claims["claims"]}
    mode = domain_claim(by_id["closure:claim:temponeras-mode"])
    assert "KO" in mode.predicate and "marginal length effects" in mode.predicate
    assert "clone 1G5" in domain_claim(by_id["closure:claim:2025-clone"]).predicate
    assert claims["researcher_hypothesis"]["kind"] == "researcher_hypothesis"
    assert claims["researcher_hypothesis"]["status"] == "PLAUSIBLE BUT INSUFFICIENT"


def test_compound_specificity() -> None:
    diff = read(OUTPUT / "causal-decision-diff.json")
    assert diff["historical_maben_engagement"]["status"] == "UNRESOLVED"
    assert diff["historical_maben_engagement"]["changed"] is False
    sponsor = next(
        c
        for c in read(OUTPUT / "integrated-claims.json")["claims"]
        if domain_claim(c).identifier == "closure:claim:east-sponsor"
    )
    assert sponsor["scope"] == "GRWD0715 programme only"
    assert "No transfer to historical Maben compounds" in sponsor["limitations"]


def test_learning_no_numeric_admission_bypass() -> None:
    state = read(OUTPUT / "learning-eligibility.json")
    assert state["historical_status"] == state["closure_status"] == "MODEL NOT BUILT"
    assert not state["thresholds_changed"]
    assert not state["model_built"]
    assert not state["eligibility_rerun_on_unadjudicated_records"]
    assert state["prior_diagnostics_not_new_admission"]


def test_causality_no_fabricated_after() -> None:
    state = read(OUTPUT / "decision-refusal.json")
    diff = read(OUTPUT / "causal-decision-diff.json")
    assert not state["candidate_created"]
    assert state["after"] is None
    assert not state["historical_state_modified"]
    assert all(c["changed"] is None for c in diff["decision_changes"].values())
    blockers = read(OUTPUT / "unresolved-blockers.json")["blockers"]
    assert state["blocker_ids"] == [b["id"] for b in blockers]
    assert len(blockers) == 1


def test_offline_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline replay may not fetch sources")

    monkeypatch.setattr(socket, "create_connection", refuse)
    result = replay_closure()
    assert result["existing_claim_roundtrips"] == 34
    assert not result["integrated_decision_replayed"]
    assert result["scientific_outcome"] == "SCIENTIFIC REASSESSMENT BLOCKED"


def test_tampered_refusal_rejected(tmp_path: Path) -> None:
    target = tmp_path / "closure"
    shutil.copytree(OUTPUT, target)
    (target / "decision-refusal.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        verify_closure(target)


def test_no_self_approval_even_with_rehashed_package(tmp_path: Path) -> None:
    target = tmp_path / "closure"
    shutil.copytree(OUTPUT, target)
    path = target / "integrated-claims.json"
    data = read(path)
    data["claims"][0]["review_state"] = "accepted"
    path.write_text(json.dumps(data))
    manifest_path = target / "manifest.json"
    manifest = read(manifest_path)
    manifest["checksums"][path.name] = digest(path.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    (target / "manifest.sha256").write_text(digest(manifest_path.read_bytes()))
    with pytest.raises(ValueError, match="approve itself"):
        replay_closure(target)
