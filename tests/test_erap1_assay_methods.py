"""Offline scientific boundaries for the targeted methods delta."""

import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from axis.evidence_integration import digest, eligible_date
from scripts.adjudicate_erap1_assay_methods import (
    BASE,
    COLS,
    OUTPUT,
    PARENT,
    TIN,
    freeze,
    matrix,
    read,
    replay,
    selectivity,
    stage_a,
    verify,
    write,
)


def rows() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in matrix()}


def copy_delta(tmp_path: Path) -> Path:
    out = tmp_path / "delta"
    shutil.copytree(OUTPUT, out)
    return out


def reseal(root: Path) -> None:
    m = read(root / "manifest.json")
    m["files"] = {
        p.name: digest(p.read_bytes())
        for p in root.glob("*.json")
        if p.name != "manifest.json"
    }
    write(root / "manifest.json", m)
    (root / "manifest.sha256").write_text(
        digest((root / "manifest.json").read_bytes()) + "\n"
    )


def test_complete_matrix_columns_are_categorical() -> None:
    for row in matrix():
        assert set(row["fields"]) == set(COLS)
        assert row["review_state"] == "pending_review"
        for f in row["fields"].values():
            assert f["state"] in {
                "VERIFIED",
                "INHERITED_VERIFIED",
                "MODIFIED_VERIFIED",
                "NOT_CONFIRMED",
                "CONFLICTING",
            }
            assert f["source_locator"] and f["source_version"]
        assert "score" not in row


def test_stage_a_partially_resolved_only_bradshaw_blocks() -> None:
    gate = stage_a(matrix())
    assert gate["stage"] == "A2"
    assert not gate["stage_b_permitted"]
    assert {x["assay"] for x in gate["failures"]} == {
        "bradshaw-2026-enzyme",
        "bradshaw-2026-cell",
    }


def test_empty_missing_and_duplicate_families_cannot_pass() -> None:
    for sample in ([], matrix()[1:], matrix() + [matrix()[0]]):
        with pytest.raises(ValueError, match="missing/duplicate"):
            stage_a(sample)


def test_bradshaw_references_cannot_be_borrowed_as_assays() -> None:
    for name in ("bradshaw-2026-enzyme", "bradshaw-2026-cell"):
        b = rows()[name]
        for key in ("construct", "substrate", "incubation duration", "fitting"):
            assert b["fields"][key]["value"] is None
            assert b["fields"][key]["state"] == "NOT_CONFIRMED"
        assert "synthesis only" in b["excluded_inheritance"]["S3/ref1"]
        assert "crystallography only" in b["excluded_inheritance"]["S56/ref9"]


def test_tinworth_explicit_inheritance_not_crystallographic_construct() -> None:
    e = rows()["tinworth-human-enzyme"]
    for key, value in (
        ("enzyme concentration", "1 nM"),
        ("substrate concentration", "5 uM"),
        ("incubation duration", "60 min"),
        ("pH", "7.0"),
    ):
        f = e["fields"][key]
        assert f["value"] == value
        assert f["state"] == "INHERITED_VERIFIED"
        assert f["chain"][0] == TIN + ":p15:ref31"
    assert "6His" in e["fields"]["construct"]["value"]
    assert "deleted crystal" in e["preparation"]["residue_range"]
    assert e["fields"]["temperature"]["value"] is None


def test_cellular_pharmacology_not_direct_occupancy() -> None:
    for name in ("tinworth-cell-KK", "tinworth-cell-compound6"):
        c = rows()[name]
        assert c["fields"]["incubation duration"]["value"] == "40 h"
        assert not c["direct_cellular_engagement"]
        assert c["cell_context"]["ERAP1_allotype"] == "NOT_CONFIRMED"
        assert c["cell_context"]["ERAP2"] == "NOT_CONFIRMED"


def test_normalization_schemes_and_unbound_endpoint_separate() -> None:
    r = rows()
    a, b = r["tinworth-cell-KK"], r["tinworth-cell-compound6"]
    assert a["cell_context"]["compound21_pIC50"] == 7.25
    assert b["cell_context"]["compound21_pIC50"] == 7.05
    assert b["cell_context"]["unbound_pIC50"] == 7.26
    assert a["cell_context"]["control_chain"] != b["cell_context"]["control_chain"]


def test_immunopeptidome_replicates_and_fdr_scope() -> None:
    i = rows()["tinworth-CT26-immunopeptidome"]
    assert i["fields"]["incubation duration"]["value"] == "30 days"
    assert "3 biological" in i["fields"]["replicates"]["value"]
    assert i["MS_details"]["FDR"].startswith("ion-level 1%")
    assert "not compound-in-KO" in i["MS_details"]["KO_dependency"]


def test_internal_conflicts_and_species_scope_retained() -> None:
    r = rows()
    assert (
        r["tinworth-mouse-YTAFTIPSI"]["fields"]["substrate"]["state"] == "CONFLICTING"
    )
    assert (
        r["tinworth-mouse-YTAFTIPSI"]["fields"]["enzyme concentration"]["value"] is None
    )
    cia = r["tinworth-CIA"]
    assert "not axSpA" in cia["fields"]["target"]["value"]
    assert any("conflicts" in s for s in cia["limits"])


def test_actual_existing_selectivity_rules_refuse_ratios() -> None:
    for item in selectivity().values():
        result = item["result"]
        assert result["comparability_status"] == "Not directly comparable"
        assert "substrate" in result["rationale"]
        assert result["ratio"] is None
        assert result["ratio_lower_bound"] is None
        assert result["ratio_upper_bound"] is None


def test_versions_same_work_not_independent_replication() -> None:
    v = read(OUTPUT / "version-provenance.json")
    assert not v["relationship"]["independent_replication"]
    assert v["relationship"]["epistemic_kind"] == "axis_inference"
    assert eligible_date(v["dates"]["preprint_version1"])
    assert v["language_adjudication"]["direct_cellular_occupancy_demonstrated"] is False


def test_preserved_claim_ids_delta_not_self_approval() -> None:
    parents = read(PARENT / "integrated-claims.json")["claims"]
    delta = read(OUTPUT / "claim-provenance-delta.json")
    assert len(parents) == 34 and len(delta) == 3
    ids = {c["domain_claim"]["identifier"] for c in parents}
    for d in delta:
        assert d["parent_claim_id"] in ids
        assert d["review_state"] == "pending_review"
        assert not d["immutable_claim_replaced"]
    assert len(read(BASE / "chemical-datasets.json")["compounds"]) == 63


def test_learning_and_decision_refused_not_fake_stable() -> None:
    d = read(OUTPUT / "decision-refusal.json")
    assert d["after"] is None and not d["candidate_created"]
    assert d["critical_uncertainty_changed"] is None
    assert d["next_experiment_changed"] is None
    learning = read(OUTPUT / "assay-comparability.json")["Chemical_Learning"]
    assert not learning["new_existing_eligibility_run"]
    assert not learning["predictive_model_built"]


def test_offline_replay_and_historical_parent_bytes() -> None:
    assert verify()["parents"]["v1"]
    result = replay()
    assert result["stage"] == "A2"
    assert result["historical_claim_roundtrips"] == 34


def test_tampered_matrix_detected(tmp_path: Path) -> None:
    root = copy_delta(tmp_path)
    data = deepcopy(read(root / "assay-method-matrix.json"))
    data[0]["review_state"] = "accepted"
    write(root / "assay-method-matrix.json", data)
    with pytest.raises(ValueError, match="checksum"):
        verify(root)
    reseal(root)
    with pytest.raises(ValueError, match="curated method matrix"):
        replay(root)


def test_post_cutoff_artifact_rejected_even_if_resealed(tmp_path: Path) -> None:
    root = copy_delta(tmp_path)
    data = read(root / "source-artifacts.json")
    data[0]["public_available_date"] = "2026-10-06"
    write(root / "source-artifacts.json", data)
    reseal(root)
    with pytest.raises(ValueError, match="beyond cutoff"):
        replay(root)


def test_after_cannot_be_created_when_gate_blocked(tmp_path: Path) -> None:
    root = copy_delta(tmp_path)
    data = read(root / "decision-refusal.json")
    data["after"] = {"id": "fake-decision"}
    write(root / "decision-refusal.json", data)
    reseal(root)
    with pytest.raises(ValueError, match="cannot contain DecisionState"):
        replay(root)


def test_manifest_cannot_ignore_unlisted_resources(tmp_path: Path) -> None:
    root = copy_delta(tmp_path)
    write(root / "extra.json", {})
    with pytest.raises(ValueError, match="unmanifested"):
        verify(root)


def test_frozen_delta_cannot_be_silently_regenerated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="frozen delta already exists"):
        freeze(tmp_path)


def test_acceptance_has_thirteen_gates_no_aggregate_score() -> None:
    gates = read(OUTPUT / "acceptance-matrix.json")
    assert len(gates) == 13
    assert {g["status"] for g in gates.values()} <= {
        "PASS",
        "PASS WITH CONDITIONS",
        "FAIL",
    }
    assert gates["External-review readiness"]["status"] == "FAIL"
