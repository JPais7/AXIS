"""Counterfactual boundary tests, not proof of scientific truth."""

import copy
import json
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from axis.evidence_addendum import (
    PREFIX,
    audit,
    claim_eligible,
    engagement_eligible,
    measurements_comparable,
    scientific_boundary_errors,
)


def resources():
    root = files("axis").joinpath(PREFIX)
    return (
        json.loads(root.joinpath("candidate-studies.json").read_text()),
        json.loads(root.joinpath("claims.json").read_text()),
    )


def test_offline_replay(monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("network prohibited")

    monkeypatch.setattr(socket, "socket", deny)
    first = audit()
    assert first == audit()
    assert first["integrity_errors"] == []
    assert first["source_assertions"] == first["pending_source_assertions"] == 21
    assert first["actions"]["INTEGRATE"] == 10
    assert not first["new_canonical_decision"]


@pytest.mark.parametrize(
    "access", ["ABSTRACT_ONLY", "SUPPLEMENT_ONLY", "METADATA_ONLY", "INACCESSIBLE"]
)
def test_insufficient_access_never_eligible(access):
    assert not claim_eligible(
        {"action": "INTEGRATE", "accessibility": access, "methods_sufficient": True}
    )


@pytest.mark.parametrize("field", ["methods_sufficient", "primary"])
def test_oa_not_sufficient_by_itself(field):
    study = {
        "action": "INTEGRATE",
        "accessibility": "FULL_TEXT_ACCESSIBLE",
        "methods_sufficient": True,
        "primary": True,
    }
    study[field] = False
    assert not claim_eligible(study)


@pytest.mark.parametrize(
    "kind",
    ["cellular phenotype", "protein binding", "lysate binding", "crystal structure"],
)
def test_binding_and_phenotype_not_engagement(kind):
    assert not engagement_eligible({"kind": kind, "methods_inspected": True})


def test_engagement_requires_exposure_and_specificity():
    observation = {
        k: True
        for k in (
            "intact_cell",
            "direct_or_validated_proximal_readout",
            "exposure_matched",
            "specificity_controls",
            "methods_inspected",
        )
    }
    assert engagement_eligible(observation)
    for key in observation:
        altered = dict(observation, **{key: False})
        assert not engagement_eligible(altered)


def test_selectivity_context_and_censoring():
    assay = {
        "substrate": "YTAFTIPSI",
        "endpoint": "IC50",
        "species": "human",
        "matrix": "biochemical",
        "conditions": "defined",
        "operator": "<",
        "value": 4.0,
    }
    assert measurements_comparable(assay, dict(assay))
    assert not measurements_comparable(assay, dict(assay, substrate="Arg-AMC"))
    assert not measurements_comparable(assay, dict(assay, matrix="cellular"))
    assert assay["operator"] == "<"  # Predicate does not rewrite a censored value.


@pytest.mark.parametrize(
    "flag",
    [
        "clinical_efficacy",
        "chemical_genetic_dependency",
        "therapeutic_direction_established",
        "direct_cellular_engagement",
    ],
)
def test_no_mechanistic_layer_jump(flag):
    studies, claims = resources()
    claims[0][flag] = True
    assert scientific_boundary_errors(studies, claims)


def test_inaccessible_potentially_material_study_is_isolated():
    studies, claims = resources()
    corilagin = next(s for s in studies if s["id"] == "corilagin-2025")
    assert corilagin["materiality"] == "POTENTIALLY_MATERIAL"
    assert not any(c["study_id"] == corilagin["id"] for c in claims)
    fake = copy.deepcopy(claims[0])
    fake["id"] = "fake-corilagin"
    fake["study_id"] = corilagin["id"]
    assert scientific_boundary_errors(studies, claims + [fake])


def test_as_allotype_and_mr_boundaries():
    studies, claims = resources()
    by_id = {s["id"]: s for s in studies}
    assert "not all axSpA" in by_id["wang-2022"]["disease_relevance"]
    assert by_id["wang-2022"]["context"]["functional_PBMC_donors"].startswith("7 ")
    assert "not full ERAP1" in by_id["tedeschi-2023"]["context"]["genotype"]
    assert "MR" in by_id["wu-mr-2025"]["design"]
    assert not any(c["study_id"] == "wu-mr-2025" for c in claims)


def test_impact_and_commercial_provenance():
    root = files("axis").joinpath(PREFIX)
    decision = json.loads(root.joinpath("decision-impact.json").read_text())
    assert decision["review_status"] == "pending_review"
    assert (
        decision["critical_uncertainty"]["before"]
        == decision["critical_uncertainty"]["after"]
    )
    assert decision["recommended_experiment"]["classification"] == "REFINED_EXPERIMENT"
    assert decision["chemical_learning"]["new_standardized_measurements_imported"] == 0
    assert (
        decision["commercial"]["disclaimer"] == "Independent scientific review pending."
    )
    assert "bounded addendum" in decision["commercial"]["coverage_wording"]
    assert "not adjudicated" in decision["commercial"]["inaccessible_wording"]


def test_review_promotion_and_context_loss_fail_closed():
    studies, claims = resources()
    claims[0]["review_status"] = "accepted"
    claims[0]["experimental_context"] = {}
    errors = scientific_boundary_errors(studies, claims)
    assert any(e.startswith("unauthorized_review_promotion") for e in errors)
    assert any(e.startswith("context_lost") for e in errors)


def test_resource_tampering_is_detected(tmp_path):
    source = files("axis").joinpath(PREFIX)
    for child in source.iterdir():
        shutil.copyfile(str(child), tmp_path / child.name)
    target = tmp_path / "summary.json"
    target.write_text(target.read_text() + "\n")
    assert "checksum_mismatch:summary.json" in audit(tmp_path)["integrity_errors"]


def test_chemical_observations_are_not_learning_rows():
    root = files("axis").joinpath(PREFIX)
    chemical = json.loads(root.joinpath("chemical-matter.json").read_text())
    record = next(r for r in chemical["records"] if r["name"].endswith("compound 7"))
    assert all(r["operator"] == "<" for r in record["selectivity"])
    assert chemical["selectivity_ratios"] == "NOT DIRECTLY COMPARABLE"
    assert audit()["chemical_learning"]["new_standardized_measurements_imported"] == 0


def test_new_commercial_statements_drill_down_to_sources():
    repo = Path(__file__).resolve().parents[1]
    trace = json.loads(
        (repo / ("reports/commercial/erap1-axspa/v1.1/traceability.json")).read_text()
    )
    _, claims = resources()
    claim_ids = {c["id"] for c in claims}
    for statement in trace:
        if statement["commercial_statement_id"].startswith("CM"):
            assert statement["review_status"] == "pending_review"
            assert statement["impact_ids"]
            assert statement["source_chain"]
            for source in statement["source_chain"]:
                assert source["id"] in claim_ids
                assert source["experiment_id"]
                assert source["source_locator"]["section"]
                assert source["experimental_context"]
