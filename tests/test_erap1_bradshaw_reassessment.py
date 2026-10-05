"""Scientific admission, immutable history and actual-engine causal replay."""

import json
import shutil
import socket
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from axis.decision import engine, rules
from axis.decision.evidence import assemble_evidence
from axis.decision.service import DecisionService
from axis.evidence_integration import digest, normalize_pic50
from scripts.reassess_erap1_bradshaw import (
    BASE,
    BRAD,
    CUTOFF,
    EXTRA_TESTS,
    LIDDLE,
    METHODS,
    OUTPUT,
    PARENTS,
    PROJECT,
    SNAPSHOT,
    allotypes,
    build,
    comparisons,
    learning,
    matrix,
    numerical,
    read,
    replay,
    stage_a,
    verify,
    write,
)


@pytest.fixture(scope="module")
def seed() -> dict[str, Any]:
    return read(OUTPUT / "source-provenance.json")


def test_primary_identity_and_publication_cutoff(seed: dict[str, Any]) -> None:
    s = seed["main_source"]
    assert s["doi"] == BRAD and s["filename"] == "jm5c03071.pdf"
    assert s["publication_date"] == "2026-04-13" and s["eligible"]
    assert s["access_date"] == CUTOFF
    assert "UNIV LUSOFONA" in s["access_provenance"]
    assert len(s["sha256"]) == 64 and s["bytes"] > 100000
    assert not s["redistributed"] and s["independent_study_count"] == 1
    assert all(f["verified"] for f in s["verification"])


def test_assay_identity_direct_and_explicit_inheritance() -> None:
    e = matrix()[0]["fields"]
    assert e["allotype"]["value"] == "Hap2 / Allotype2"
    assert e["substrate"]["value"] == "YTAFTIPSI -> TAFTIPSI"
    assert "RapidFire" in e["readout"]["value"]
    for f in ("construct", "buffer", "enzyme concentration", "incubation duration"):
        assert e[f]["state"] == "INHERITED_VERIFIED"
        assert e[f]["chain"] == [BRAD + ":p17:ref22", LIDDLE]
    assert e["incubation duration"]["value"] == "60 min"
    assert "full-length" in e["construct"]["value"]


@pytest.mark.parametrize(
    "field", ["temperature", "preincubation", "concentration range"]
)
def test_unreported_details_not_borrowed_from_related_programmes(field: str) -> None:
    for row in matrix()[:2]:
        assert row["fields"][field]["state"] == "NOT_CONFIRMED"
        assert row["fields"][field]["value"] is None
        assert "inaccessible" not in row["fields"][field]["source_locator"]


def test_cellular_endpoint_not_occupancy_or_hla_b27() -> None:
    c = matrix()[1]
    assert "HeLa" in c["fields"]["endpoint"]["value"]
    assert "SIINFEKL" in c["fields"]["substrate"]["value"]
    assert c["fields"]["incubation duration"]["value"] == "40 h"
    assert "iQue" in c["fields"]["readout"]["value"]
    assert not c["direct_cellular_engagement"]
    assert c["cell_context"]["ERAP1_allotype"] == "NOT_CONFIRMED"
    assert c["cell_context"]["ERAP2"] == "NOT_CONFIRMED"
    assert c["cell_context"]["control_compound_identity"].startswith("NOT_CONFIRMED")


def test_existing_stage_a_now_a1_not_all_fields_required() -> None:
    assert stage_a(matrix())["stage"] == "A1"
    assert stage_a(matrix())["stage_b_permitted"]
    assert read(METHODS / "stage-a.json")["stage"] == "A2"
    altered = deepcopy(matrix())
    altered[0]["fields"]["substrate"]["state"] = "NOT_CONFIRMED"
    assert not stage_a(altered)["stage_b_permitted"]


def test_cutoff_violation_refuses_decision(seed: dict[str, Any]) -> None:
    altered = deepcopy(seed)
    altered["main_source"]["publication_date"] = "2026-10-06"
    with pytest.raises(ValueError, match="ineligible"):
        build(altered)


def test_numerical_existing_ids_no_duplicate_studies(seed: dict[str, Any]) -> None:
    rows = numerical(seed)
    expected = {
        m["id"]
        for m in read(BASE / "chemical-datasets.json")["measurements"]
        if m["source"] == BRAD
    }
    assert len(rows) == 79
    assert {r["parent_measurement_id"] for r in rows} == expected
    assert len({r["parent_measurement_id"] for r in rows}) == len(rows)
    assert all(r["original_smiles"] for r in rows)


def test_exact_n_sd_not_generic_replicates(seed: dict[str, Any]) -> None:
    rows = numerical(seed)
    c40 = next(
        r for r in rows if r["compound_id"].endswith(":40") and r["family"] == "enzyme"
    )
    assert c40["si_statistics"]["n_in_mean"] == 5
    assert c40["si_statistics"]["sd_pIC50"] == 0.13
    c22 = next(
        r for r in rows if r["compound_id"].endswith(":22") and r["family"] == "cell"
    )
    assert c22["si_statistics"]["n_in_mean"] == 1
    assert c22["si_statistics"]["sd_pIC50"] is None
    assert not c22["fit_admission"]
    missing = next(r for r in rows if r["compound_id"].endswith(":1"))
    assert missing["si_statistics"] is None and not missing["fit_admission"]


def test_primary_si_csv_conflict_retained_and_excluded(seed: dict[str, Any]) -> None:
    r = next(
        r
        for r in numerical(seed)
        if r["compound_id"].endswith(":28") and r["family"] == "cell"
    )
    assert r["csv"]["source_value"] == r["si_statistics"]["mean"] == 5.4
    assert r["main_values"][0]["value"] == 5.3
    assert "main/CSV summary conflict" in r["limitations"]
    assert not r["fit_admission"]


@pytest.mark.parametrize(
    "key", [(21, "enzyme"), (28, "cell"), (33, "cell"), (44, "cell")]
)
def test_censored_extra_occasions_never_exact(
    key: tuple[int, str], seed: dict[str, Any]
) -> None:
    r = next(
        r
        for r in numerical(seed)
        if r["compound_id"].endswith(":" + str(key[0])) and r["family"] == key[1]
    )
    assert r["additional_test"] == EXTRA_TESTS[key]
    assert not r["fit_admission"]
    e = r["additional_test"]
    converted = normalize_pic50(e["operator"] + str(e["pIC50"]))
    assert converted["derived_operator"] == (">" if e["operator"] == "<" else "<")


def test_allotype_substrate_context_and_censoring() -> None:
    p = allotypes()
    assert p["allotypes"] == list(range(1, 11))
    assert set(p["substrates"]) == {"YTAFTIPSI", "EAAGIGILTV"}
    assert p["substrates"]["YTAFTIPSI"]["censored_below_pIC50_4"] == [4, 6, 7, 8, 9, 10]
    assert p["substrates"]["EAAGIGILTV"]["product"] == "AGIGILTV"
    assert not p["pooling"] and not p["graph_values_digitized"]


def test_cross_programme_not_forced() -> None:
    c = comparisons()["comparisons"]
    assert c[0]["status"] == "COMPARABLE"
    assert c[1]["status"] == "NOT_COMPARABLE"
    assert c[2]["status"] == "PARTIALLY_COMPARABLE"
    assert c[3]["status"] == "NOT_COMPARABLE"
    assert not comparisons()["existing_rules_changed"]


def test_learning_actual_policy_admits_bounded_contexts_no_model(
    seed: dict[str, Any],
) -> None:
    result = learning(seed)
    assert result["new_status"] == "MODEL_ELIGIBLE_WITH_CONDITIONS"
    assert result["historical_model_status"].startswith("MODEL NOT BUILT")
    assert not result["model_built"]
    assert [d["assessment"]["counts"]["exact"] for d in result["datasets"]] == [38, 31]
    assert all(a["admitted"] for a in result["source_context_admission"].values())
    assert all(
        d["assessment"]["conclusion"] == "not_eligible"
        for d in result["Tinworth_separate_policy_rerun"]
    )
    assert "NOT_ESTABLISHED" in result["temporal_split"]


def test_actual_engine_state_causal_link_and_unchanged_rules() -> None:
    before = read(SNAPSHOT)["decision"]
    after = read(OUTPUT / "decision-state-v2.json")
    reassessed = read(OUTPUT / "decision-reassessment.json")
    assert after["version"] == 2 and after["supersedes_id"] == before["id"]
    actual = json.loads(json.dumps(engine.analyze(reassessed["inputs"])))
    for key, value in actual.items():
        assert after[key] == value
    assert after["critical_uncertainty_id"] == before["critical_uncertainty_id"]
    assert after["recommended_experiment_id"] == before["recommended_experiment_id"]
    assert reassessed["classification"] == "DECISION STABLE"
    assert reassessed["rules_fingerprint"] == rules.fingerprint()


def test_maben_specificity_later_pharmacology_never_occupancy() -> None:
    d = read(OUTPUT / "decision-reassessment.json")
    a = d["after"]
    assert d["historical_Maben_engagement"].startswith("UNRESOLVED")
    assert a["evidence"]["edges"]["engagement"]["state"] != "supported"
    assert all(
        not (r["edge"] == "engagement" and r["state"] == "supported")
        for r in d["records"]["assessments"]
        if r["id"].startswith("brad-v3:")
    )
    assert a["review_mode"] == "exploratory"
    assert a["evidence"]["review"]["pending_expert_review"] > 0


def test_state_stable_without_mouse_disease_additions() -> None:
    d = read(OUTPUT / "decision-reassessment.json")
    inputs = deepcopy(d["inputs"])
    records = deepcopy(d["records"])
    removed = {
        e["id"]
        for e in records["experiments"]
        if e["id"] in {"brad-v3:tinworth-CIA", "brad-v3:tran-arthritis"}
    }
    records["experiments"] = [
        e for e in records["experiments"] if e["id"] not in removed
    ]
    for k in ("readouts", "assessments"):
        records[k] = [r for r in records[k] if r["experiment_id"] not in removed]
    inputs["evidence"] = assemble_evidence(records)
    result = engine.analyze(inputs)
    assert result["critical_uncertainty_id"] == d["after"]["critical_uncertainty_id"]
    assert (
        result["recommended_experiment_id"] == d["after"]["recommended_experiment_id"]
    )


def test_readout_claims_and_sources_have_real_parent_or_delta() -> None:
    delta = read(OUTPUT / "integrated-claim-delta.json")
    assert len(delta) == 6
    assert all(c["review_state"] == "pending_review" for c in delta)
    parents = read(PARENTS["closure-v1"] / "integrated-claims.json")["claims"]
    ids = {c["domain_claim"]["identifier"] for c in parents + delta}
    records = read(OUTPUT / "decision-reassessment.json")["records"]
    for r in records["readouts"]:
        if r["id"].startswith("brad-v3:"):
            assert r["claim_id"] in ids


def test_mandatory_causal_diff_complete() -> None:
    d = read(OUTPUT / "causal-decision-diff.json")
    assert len(d["items"]) == 8
    assert d["items"]["Critical uncertainty"]["status"] == "STABLE"
    assert d["items"]["Historical Maben engagement"]["status"] == "STABLE"
    assert all(item["cause"] for item in d["items"].values())
    assert d["classification"] == "DECISION STABLE"


def test_historical_parent_bytes_and_baseline_preserved() -> None:
    m = verify()
    assert m["canonical_snapshot_sha256"] == digest(SNAPSHOT.read_bytes())
    assert len(m["parents"]) == 3
    assert read(METHODS / "decision-refusal.json")["after"] is None
    canonical = read(SNAPSHOT)["decision"]
    old_inputs = read(BASE / "decision-inputs.json")["baseline"]
    assert DecisionService.digests(
        PROJECT, canonical["protein_id"], old_inputs
    ) == canonical["digests"]


def test_checksum_mutation_refused(tmp_path: Path) -> None:
    root = tmp_path / "copy"
    shutil.copytree(OUTPUT, root)
    write(root / "stage-a.json", {"stage": "A3"})
    with pytest.raises(ValueError, match="checksum"):
        verify(root)


def test_unmanifested_resource_refused(tmp_path: Path) -> None:
    root = tmp_path / "copy"
    shutil.copytree(OUTPUT, root)
    write(root / "untracked.json", {})
    with pytest.raises(ValueError, match="unmanifested"):
        verify(root)


def test_offline_reproduction_without_original_pdf_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    assert replay()["decision"] == "DECISION STABLE"
