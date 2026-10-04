"""Phase 3.6: experimental results, review and DecisionState v2.

Every result here is SYNTHETIC / TEST-ONLY. Production ERAP1 evidence is never altered.
"""

import hashlib
import json
import re
import shutil
import socket
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx
import pytest
from typer.testing import CliRunner

from axis.api.server import ReadAPI
from axis.cellular.service import CellularPharmacologyService
from axis.cli.main import app
from axis.decision import rules
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.discovery.service import DiscoveryService
from axis.domain.results import ExperimentalResult, ScientificReview
from axis.experiments import policy
from axis.experiments.results import ResultsService
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
SYN = Path(
    str(
        resources.files("axis").joinpath(
            "resources/experimental-results/synthetic/erap1-decision-loop/v1"
        )
    )
)
REPO = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
ENGAGE = "decision:exp:engagement-assay"


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    PharmacologyService(store).import_package(PROJECT, protein)
    CellularPharmacologyService(store).import_package(PROJECT, protein)
    service = DecisionService(store)
    service.import_package(PROJECT, protein)
    ResultsService(store).import_signatures(PROJECT)
    return protein, service


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    path = tmp_path_factory.mktemp("loop") / "template.duckdb"
    with EvidenceStore(path) as store:
        protein, service = init(store)
        service.build(PROJECT, protein, created_at=FIXED)
    return path, protein


@pytest.fixture
def world(template, tmp_path):
    source, protein = template
    path = tmp_path / "world.duckdb"
    shutil.copy(source, path)
    with EvidenceStore(path) as store:
        yield store, protein, DecisionService(store), ResultsService(store), tmp_path


# -- package factories -------------------------------------------------------------


def experiment(
    eid,
    *,
    compound="compound:maben-3",
    perturbagen=None,
    qc="interpretable",
    proposal=ENGAGE,
    deviations=(),
    edges=("engagement",),
    status="synthetic",
):
    scope = (
        {"scope_type": "perturbagen", "scope_id": perturbagen}
        if perturbagen
        else {"scope_type": "compound", "scope_id": compound}
    )
    out = {
        "id": eid,
        "proposal_id": proposal,
        "executed_at": "2026-10-05T08:00:00+00:00",
        "performed_by": "Synthetic fixture",
        "scope": scope,
        "context": {
            "cell_line": "SYNTHETIC line",
            "hla_allele": "unspecified (synthetic)",
        },
        "target_label": "ERAP1",
        "construct": "not reported",
        "assay": "synthetic engagement readout",
        "controls": ["vehicle", "target-depleted cells"],
        "exposure": "phenotype-active exposure (synthetic)",
        "measures_edges": list(edges),
        "endpoints": ["cellular_engagement_signal"],
        "qc": {
            "control_status": "failed" if qc == "non_interpretable" else "passed",
            "technical_validity": "invalid" if qc == "non_interpretable" else "valid",
            "replicate_quality": "adequate",
            "assessment": qc,
            "rationale": "synthetic QC",
        },
        "deviations": list(deviations),
    }
    out[
        "perturbagen"
        if False
        else ("reported_perturbagen" if perturbagen else "compound_id")
    ] = perturbagen or compound
    return out


def result(
    rid,
    eid,
    facets,
    text="synthetic observation",
    *,
    rtype="binary_detection",
    version=1,
    supersedes=None,
    replicates=None,
):
    out = {
        "id": rid,
        "version": version,
        "experiment_id": eid,
        "endpoint": "cellular_engagement_signal",
        "result_type": rtype,
        "qualitative_result": text,
        "replicates": replicates or {"n": 3, "type": "biological"},
        "raw_artifact_ids": ["synthetic:art:raw"],
        "processed_artifact_ids": ["synthetic:art:processed"],
        "analysis": {"method": "vehicle normalization", "version": "synthetic-1"},
        "observed_at": "2026-10-05T08:30:00+00:00",
        "facets": facets,
    }
    if supersedes:
        out["supersedes_id"] = supersedes
    return out


def interpretation(
    iid,
    rid,
    scope_id="compound:maben-3",
    *,
    scope_type="compound",
    state="supported",
    edge="engagement",
    caveats=("single synthetic system",),
):
    return {
        "id": iid,
        "result_id": rid,
        "edge": edge,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "proposed_state": state,
        "statement": f"synthetic interpretation {iid}",
        "rationale": "synthetic",
        "knowledge_kind": "ai_suggestion",
        "caveats": list(caveats),
    }


DETECTED = {"engagement_signal": "detected", "signal_in_target_depleted": "absent"}
NOT_DETECTED = {"engagement_signal": "not_detected"}


def package(tmp, name, experiments, results, interpretations, *, mutate=None):
    base = json.loads((SYN / "manifest.json").read_text())
    base["experiments"], base["results"], base["interpretations"] = (
        experiments,
        results,
        interpretations,
    )
    if mutate:
        mutate(base)
    target = tmp / name
    shutil.copytree(SYN / "raw", target / "raw")
    raw = json.dumps(base, indent=2, sort_keys=True).encode() + b"\n"
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return target


def run_loop(
    world,
    name,
    experiments,
    results,
    interpretations,
    *,
    accept=True,
    rebuild=True,
    **kw,
):
    store, protein, service, results_service, tmp = world
    directory = package(tmp, name, experiments, results, interpretations, **kw)
    summary = results_service.import_package(PROJECT, directory, allow_synthetic=True)
    if accept:
        for r in results:
            results_service.record_review(
                PROJECT,
                "experimental_result",
                f"{r['id']}@v{r['version']}",
                "Dr Example",
                "accepted",
                "QC reviewed",
            )
        for i in interpretations:
            results_service.record_review(
                PROJECT,
                "result_interpretation",
                i["id"],
                "Dr Example",
                "accepted",
                "consistent with the observation",
            )
    state = service.rebuild(PROJECT, protein, created_at=FIXED) if rebuild else None
    return summary, state


def scenario(analysis_state, edge, scope):
    return analysis_state["effective_evidence"]["scoped_edges"].get(edge, {}).get(scope)


# -- baseline and production regression -------------------------------------------


def test_production_erap1_decision_is_unchanged_by_phase_36(world):
    store, protein, service, _, _ = world
    state = service.current(PROJECT, protein)
    assert state["critical_uncertainty_id"] == "uncertainty:target_engagement"
    assert (
        state["recommended_experiment_id"] == "decision:exp:chemical-genetic-engagement"
    )
    assert {e["ground"]: e["status"] for e in state["explanations"]} == {
        "on_target": "partially_supported",
        "off_target": "viable",
        "indirect_pathway": "viable",
        "context_dependent": "viable",
    }
    assert state["evidence"]["edges"]["engagement"]["state"] == "not_assessed"
    assert state["results"]["contributions"] == []
    assert state["synthetic"] is False
    assert state["review"]["pending_expert_review"] > 0
    assert state["review_mode"] == "exploratory"


def test_import_never_changes_the_decision_or_creates_a_state(world):
    store, protein, service, results, tmp = world
    before = store.decisions.history(PROJECT, protein)["total"]
    summary = results.import_package(PROJECT, allow_synthetic=True)
    assert (
        summary["decision_state_changed"] is False
        and summary["scientific_status"] == "synthetic_test_fixture"
    )
    assert store.decisions.history(PROJECT, protein)["total"] == before
    assert service.current(PROJECT, protein)["results"]["contributions"] == []


# -- happy path, scope, rollup ------------------------------------------------------


def test_happy_path_partial_resolution_for_one_compound(world):
    store, protein, service, results, tmp = world
    v1 = service.current(PROJECT, protein)
    summary, v2 = run_loop(
        world,
        "happy",
        [experiment("E1")],
        [result("R1", "E1", DETECTED)],
        [interpretation("I1", "R1")],
    )
    assert v2["version"] == 2 and v2["supersedes_id"] == v1["id"]
    rollup = v2["effective_evidence"]["engagement_rollup"]
    assert rollup["status"] == "partial"
    states = {
        f"{s['scope_type']}:{s['scope_id']}": s["state"] for s in rollup["scopes"]
    }
    assert states["compound:compound:maben-3"] == "supported"
    assert states["compound:compound:maben-2"] == "not_assessed"
    assert states["perturbagen:DG013A"] == "not_assessed"
    engagement = next(
        u for u in v2["uncertainties"] if u["category"] == "target_engagement"
    )
    assert engagement["status"] == "partially_resolved"
    assert "DECISION-RESULT-002" in engagement["fired_rules"]
    assert v2["effective_evidence"]["edges"]["engagement"] == "incomplete"
    diff = v2["diff"]
    assert [c["category"] for c in diff["causes"]] == ["new_experimental_evidence"]
    assert diff["decision_changed"]["answer"] == "partially"
    names = [c["name"] for c in diff["scientific_diff"]["evidence_status_changes"]]
    assert any("engagement / compound:compound:maben-3" in n for n in names)
    assert diff["triggering_results"] == ["R1"]
    # DecisionState v1 is preserved byte for byte
    assert json.dumps(
        store.decisions.state(PROJECT, protein, v1["id"]), sort_keys=True
    ) == json.dumps(v1, sort_keys=True)
    assert store.results.state_links(v2["id"])[0]["review_state"] == "accepted"


def test_complete_resolution_changes_the_critical_uncertainty_with_a_rule_path(world):
    store, protein, service, results, tmp = world
    exps = [
        experiment("E3"),
        experiment("E2", compound="compound:maben-2"),
        experiment("EG", perturbagen="DG013A"),
    ]
    res = [
        result(f"R{i}", e["id"], DETECTED)
        for i, e in zip(("3", "2", "G"), exps, strict=True)
    ]
    ints = [
        interpretation("I3", "R3"),
        interpretation("I2", "R2", "compound:maben-2"),
        interpretation("IG", "RG", "DG013A", scope_type="perturbagen"),
    ]
    _, v2 = run_loop(world, "complete", exps, res, ints)
    assert v2["effective_evidence"]["engagement_rollup"]["status"] == "complete"
    assert v2["effective_evidence"]["edges"]["engagement"] == "supported"
    engagement = next(
        u for u in v2["uncertainties"] if u["category"] == "target_engagement"
    )
    assert engagement["status"] == "resolved_for_current_decision"
    assert v2["critical_uncertainty_id"] != "uncertainty:target_engagement"
    sd = v2["diff"]["scientific_diff"]
    assert sd["critical"]["before"] == "uncertainty:target_engagement"
    assert sd["critical"]["because"]["triggering_results"] == ["R2", "R3", "RG"]
    assert v2["diff"]["decision_changed"]["answer"] == "yes"
    # no invented chemical identity for the source-reported perturbagen
    assert (
        store._connection.execute(
            "SELECT count(*) FROM compound_identities"
        ).fetchone()[0]
        == 3
    )
    # removal sensitivity: dropping a result reverts the scientific state
    groups = {r["group"] for r in v2["sensitivity"]["decision_sensitive"]}
    assert {"result:R2", "result:R3", "result:RG"} & groups


def test_compound_isolation_and_unresolved_identity(world):
    _, v2 = run_loop(
        world,
        "isolation",
        [experiment("E3")],
        [result("R3", "E3", DETECTED)],
        [interpretation("I3", "R3")],
    )
    scopes = {
        f"{s['scope_type']}:{s['scope_id']}": s
        for s in v2["effective_evidence"]["engagement_rollup"]["scopes"]
    }
    assert scopes["compound:compound:maben-2"]["contribution_ids"] == []
    assert scopes["perturbagen:DG013A"]["state"] == "not_assessed"
    # compound-scope resolution is not target-level resolution
    answer = world[2].answer(PROJECT, world[1], "resolution_scope")["answer"]
    row = next(r for r in answer if r["uncertainty"] == "uncertainty:target_engagement")
    assert row["level"] == "compound/scope-specific"


def test_result_for_a_scope_that_needs_no_engagement_does_not_change_the_recommendation(
    world,
):
    store, protein, service, _, _ = world
    v1 = service.current(PROJECT, protein)
    _, v2 = run_loop(
        world,
        "unrelated",
        [experiment("E1c", compound="compound:maben-1")],
        [result("R1c", "E1c", DETECTED)],
        [interpretation("I1c", "R1c", "compound:maben-1")],
    )
    assert v2["recommended_experiment_id"] == v1["recommended_experiment_id"]
    assert v2["critical_uncertainty_id"] == v1["critical_uncertainty_id"]
    assert v2["effective_evidence"]["engagement_rollup"]["status"] == "open"
    assert v2["diff"]["decision_changed"]["answer"] in ("no", "partially")
    assert v2["diff"]["scientific_diff"]["critical"] is None


# -- negative, failure, unexpected, partial, deviation -----------------------------


def test_negative_engagement_weakens_on_target_without_concluding_off_target(world):
    _, v2 = run_loop(
        world,
        "negative",
        [experiment("EN")],
        [result("RN", "EN", NOT_DETECTED)],
        [interpretation("IN", "RN", state="contradicted")],
    )
    by = {e["ground"]: e for e in v2["explanations"]}
    assert by["on_target"]["status"] == "weakened"
    assert by["off_target"]["status"] in ("viable", "partially_supported")
    assert by["off_target"]["status"] != "supported"
    assert any(
        link["relationship"] == "supports" and link["evidence_type"] == "interpretation"
        for link in by["off_target"]["links"]
    )
    assert any(
        r["scope"] == "compound:compound:maben-3"
        for r in v2["position"]["contradicted"]
    )


def test_technical_failure_is_not_a_biological_negative(world):
    store, protein, service, results, tmp = world
    v1 = service.current(PROJECT, protein)
    _, v2 = run_loop(
        world,
        "failure",
        [experiment("EF", qc="non_interpretable")],
        [
            result(
                "RF",
                "EF",
                {"assay_validity": "failed"},
                "positive control failed",
                rtype="technical_failure",
            )
        ],
        [interpretation("IF", "RF", state="contradicted")],
    )
    ledger = results.ledger(PROJECT)
    assert ledger[0]["eligibility"]["state"] == "ineligible_qc_failure"
    assert ledger[0]["eligibility"]["rule"] == "RESULT-QC-001"
    assert ledger[0]["scenario_match"] == "non_interpretable"
    assert v2["id"] == v1["id"]  # no scientific change, no new state
    assert store.decisions.history(PROJECT, protein)["total"] == 1


def test_unexpected_result_is_preserved_not_force_fitted(world):
    _, v2 = run_loop(
        world,
        "unexpected",
        [experiment("EU")],
        [result("RU", "EU", {"unrelated_observation": "observed"})],
        [interpretation("IU", "RU", state="insufficient")],
    )
    unexpected = next(
        u
        for u in v2["uncertainties"]
        if u["id"].startswith("uncertainty:unexpected_result")
    )
    assert unexpected["fired_rules"] == ["DECISION-RESULT-003"]
    overall = next(
        m for m in world[0].results.matches("RU@v1") if m["outcome_scenario_id"] is None
    )
    assert overall["relationship"] == "outside_predefined_scenarios"
    assert "outside the predefined outcome scenarios" in overall["rationale"]
    assert world[0].results.matches("RU@v1") == [
        overall
    ]  # no scenario was force-fitted


def test_partial_scenario_match_stays_partial(world):
    _, _ = run_loop(
        world,
        "partial",
        [experiment("EP")],
        [
            result(
                "RP",
                "EP",
                {
                    "engagement_signal": "detected",
                    "signal_in_target_depleted": "present",
                },
            )
        ],
        [interpretation("IP", "RP", state="insufficient")],
        rebuild=False,
    )
    matches = {m["outcome_scenario_id"]: m for m in world[0].results.matches("RP@v1")}
    assert (
        matches["decision:exp:engagement-assay:s1"]["relationship"]
        == "partially_matches"
    )
    assert matches[None]["relationship"] == "partially_matches"


def test_design_deviation_limits_or_invalidates_interpretation(world):
    store, protein, service, results, tmp = world
    limits = {
        "field": "context.hla_allele",
        "proposed": "HLA-B*27:05",
        "actual": "other context",
        "type": "context",
        "rationale": "model unavailable",
        "relevance": "limits_interpretation",
    }
    run_loop(
        world,
        "dev-limits",
        [experiment("ED", deviations=[limits])],
        [result("RD", "ED", DETECTED)],
        [interpretation("ID", "RD")],
        rebuild=False,
    )
    entry = results.ledger(PROJECT)[0]
    assert entry["eligibility"]["state"] == "eligible_with_caveat"
    assert any(
        "design deviation" in c and "context.hla_allele" in c
        for c in entry["eligibility"]["caveats"]
    )
    assert store.results.deviations("ED")[0]["actual_value"] == "other context"
    invalid = dict(limits, relevance="invalidates_comparison", field="endpoint")
    run_loop(
        world,
        "dev-invalid",
        [experiment("EI", deviations=[invalid])],
        [result("RI", "EI", DETECTED)],
        [interpretation("II", "RI")],
        rebuild=False,
    )
    bad = next(x for x in results.ledger(PROJECT) if x["result_id"] == "RI")
    assert bad["eligibility"]["state"] == "ineligible_design_deviation"


def test_edge_must_be_measured_and_does_not_cascade(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "edge",
        [experiment("EE")],
        [result("RE", "EE", DETECTED)],
        [interpretation("IE", "RE", edge="functional")],
        rebuild=False,
    )
    assert (
        results.ledger(PROJECT)[0]["eligibility"]["state"]
        == "ineligible_edge_not_measured"
    )
    _, v2 = run_loop(
        world,
        "edge2",
        [experiment("EE2")],
        [result("RE2", "EE2", DETECTED)],
        [interpretation("IE2", "RE2")],
    )
    v1 = store.decisions.history(PROJECT, protein)["items"][-1]
    for edge in (
        "functional",
        "hla",
        "immune",
        "disease",
        "clinical",
        "biochemical",
        "exposure",
    ):
        assert (
            v2["effective_evidence"]["edges"][edge]
            == v1["evidence"]["edges"][edge]["state"]
        ), edge
    assert v2["evidence"]["contexts"]["hla_alleles"] == ["HLA-B*27:05"]


# -- review workflow ---------------------------------------------------------------


def test_review_pending_is_exploratory_only(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "pending",
        [experiment("EV")],
        [result("RV", "EV", DETECTED)],
        [interpretation("IV", "RV")],
        accept=False,
        rebuild=False,
    )
    entry = results.ledger(PROJECT, "exploratory")[0]
    assert (
        entry["eligibility"]["state"] == "pending_review"
        and entry["eligibility"]["eligible"]
    )
    assert not results.ledger(PROJECT, "reviewed")[0]["eligibility"]["eligible"]
    preview = service.impact_preview(PROJECT, protein, "IV")
    assert (
        preview["label"] == "Preview — not current decision"
        and preview["applied"] is False
    )
    assert store.decisions.history(PROJECT, protein)["total"] == 1  # nothing stored
    exploratory = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert exploratory["results"]["contributions"][0]["review_state"] == "pending"
    assert (
        "pending scientific review"
        in exploratory["position"]["supported"][-1]["caveats"][-1]
    )
    reviewed = service.rebuild(PROJECT, protein, mode="reviewed", created_at=FIXED)
    assert reviewed["results"]["contributions"] == []
    assert reviewed["review_mode"] == "reviewed"


def test_accepting_creates_a_review_status_change_not_new_evidence(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "reviewcause",
        [experiment("ER")],
        [result("RR", "ER", DETECTED)],
        [interpretation("IR", "RR")],
        accept=False,
        rebuild=True,
    )
    results.record_review(
        PROJECT, "experimental_result", "RR@v1", "Dr Example", "accepted", "ok"
    )
    results.record_review(
        PROJECT, "result_interpretation", "IR", "Dr Example", "accepted", "ok"
    )
    v3 = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert [c["category"] for c in v3["diff"]["causes"]] == ["review_status_change"]
    assert v3["diff"]["causes"][0]["items"][0] == {
        "interpretation_id": "IR",
        "result_id": "RR",
        "before": "pending",
        "after": "accepted",
    }
    assert "review" in v3["diff"]["cause"] and "evidence" not in v3["diff"]["cause"]


def test_result_accepted_interpretation_rejected(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "rej",
        [experiment("EJ")],
        [result("RJ", "EJ", DETECTED)],
        [interpretation("IJ", "RJ")],
        accept=False,
        rebuild=False,
    )
    results.record_review(
        PROJECT, "experimental_result", "RJ@v1", "Dr Example", "accepted", "valid data"
    )
    results.record_review(
        PROJECT, "result_interpretation", "IJ", "Dr Example", "rejected", "too strong"
    )
    entry = results.ledger(PROJECT)[0]
    assert (entry["result_review"], entry["interpretation_review"]) == (
        "accepted",
        "rejected",
    )
    assert entry["eligibility"]["state"] == "rejected"
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert state["results"]["contributions"] == []
    assert state["effective_evidence"]["edges"]["engagement"] == "not_assessed"
    assert (
        store.results.result(PROJECT, "RJ@v1")["id"] == "RJ"
    )  # the result remains stored


def test_accepted_with_caveat_propagates_the_caveat(world):
    store, protein, service, results, tmp = world
    directory = package(
        tmp,
        "caveat",
        [experiment("EC")],
        [result("RC", "EC", DETECTED)],
        [interpretation("IC", "RC")],
    )
    results.import_package(PROJECT, directory, allow_synthetic=True)
    results.record_review(
        PROJECT, "experimental_result", "RC@v1", "Dr Example", "accepted", "ok"
    )
    with pytest.raises(ValueError, match="requires the caveat"):
        results.record_review(
            PROJECT,
            "result_interpretation",
            "IC",
            "Dr Example",
            "accepted_with_caveat",
            "ok",
        )
    results.record_review(
        PROJECT,
        "result_interpretation",
        "IC",
        "Dr Example",
        "accepted_with_caveat",
        "limited",
        caveat="one cell line only",
    )
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    row = next(
        r
        for r in state["position"]["supported"]
        if r.get("scope") == "compound:compound:maben-3"
    )
    assert (
        "one cell line only" in row["caveats"]
        and "single synthetic system" in row["caveats"]
    )
    assert (
        state["results"]["contributions"][0]["eligibility_state"]
        == "eligible_with_caveat"
    )


def test_reviewer_conflict_is_never_resolved_by_majority(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "conflict",
        [experiment("EK")],
        [result("RK", "EK", DETECTED)],
        [interpretation("IK", "RK")],
        accept=False,
        rebuild=False,
    )
    results.record_review(
        PROJECT, "result_interpretation", "IK", "Reviewer A", "accepted", "a"
    )
    results.record_review(
        PROJECT, "result_interpretation", "IK", "Reviewer B", "rejected", "b"
    )
    results.record_review(
        PROJECT, "result_interpretation", "IK", "Reviewer C", "accepted", "c"
    )
    state = results.review_state(PROJECT, "result_interpretation", "IK")
    assert state["state"] == "conflict" and len(state["history"]) == 3
    assert results.ledger(PROJECT)[0]["eligibility"]["state"] == "review_conflict"
    # a reviewer may change their own mind; both entries stay in history
    results.record_review(
        PROJECT, "result_interpretation", "IK", "Reviewer B", "accepted", "reconsidered"
    )
    after = results.review_state(PROJECT, "result_interpretation", "IK")
    assert after["state"] == "accepted" and len(after["history"]) == 4


def test_ai_cannot_review_its_own_science(world):
    _, _, _, results, _ = world
    for name in ("AXIS AI", "Claude", "AI assistant", "gpt-4 model"):
        with pytest.raises(ValueError, match="AI cannot accept its own science"):
            ScientificReview(
                "r", PROJECT, "experimental_result", "x", name, "accepted", "why", FIXED
            )
    ScientificReview(
        "r",
        PROJECT,
        "experimental_result",
        "x",
        "Dr Chai Smith",
        "accepted",
        "why",
        FIXED,
    )
    with pytest.raises(ValueError):
        ScientificReview(
            "r",
            PROJECT,
            "experimental_result",
            "x",
            "Dr Example",
            "accepted",
            "why",
            FIXED,
            reviewer_kind="ai",
        )


def test_review_policy_is_explicit_and_versioned():
    assert policy.POLICY_ID == "decision-review-policy-v1"
    assert policy.MODES == ("exploratory", "reviewed")
    assert len(policy.policy_fingerprint()) == 64
    assert set(policy.RESULT_RULES) >= {
        "RESULT-QC-001",
        "RESULT-REV-001",
        "RESULT-EDGE-001",
        "RESULT-CTX-001",
    }
    state = policy.review_state(
        [
            {
                "id": "1",
                "reviewer": "A",
                "decision": "accepted",
                "caveat": None,
                "reviewed_at": "2026-01-01",
            },
            {
                "id": "2",
                "reviewer": "A",
                "decision": "pending",
                "caveat": None,
                "reviewed_at": "2026-01-02",
            },
        ]
    )
    assert state["state"] == "pending"  # a reviewer may withdraw their acceptance


def test_scenario_mapping_review_controls_ranking(world):
    store, protein, service, results, tmp = world
    exploratory = service.current(PROJECT, protein)
    assert exploratory["review_dependencies"]["pending_mappings_used"] > 0
    reviewed = service.rebuild(PROJECT, protein, mode="reviewed", created_at=FIXED)
    assert reviewed["recommended_experiment_id"] is None
    assert (
        "accepted discriminating outcome mappings" in reviewed["no_experiment_message"]
    )
    assert reviewed["review_dependencies"]["review_excluded"]
    assert (
        reviewed["evidence"]["edges"]["hla"]["state"] == "not_assessed"
    )  # pending assessments excluded
    # accept the engagement-assay design and its mappings, reject the rival's mappings
    for scenario_id, explanation in store._connection.execute(
        "SELECT scenario_id, explanation_id FROM outcome_interpretations "
        "WHERE scenario_id LIKE 'decision:exp:engagement-assay:%'"
    ).fetchall():
        results.record_review(
            PROJECT,
            "scenario_mapping",
            f"{scenario_id}|{explanation}",
            "Dr Example",
            "accepted",
            "reviewed",
        )
    results.record_review(
        PROJECT, "candidate_design", ENGAGE, "Dr Example", "accepted", "design reviewed"
    )
    rejected = service.rebuild(PROJECT, protein, mode="exploratory", created_at=FIXED)
    assert rejected["review_mode"] == "exploratory"


def test_rejected_mapping_does_not_silently_stay_active(world):
    store, protein, service, results, tmp = world
    base = service.current(PROJECT, protein)
    assert (
        base["recommended_experiment_id"] == "decision:exp:chemical-genetic-engagement"
    )
    for scenario_id, explanation in store._connection.execute(
        "SELECT scenario_id, explanation_id FROM outcome_interpretations "
        "WHERE scenario_id LIKE 'decision:exp:chemical-genetic-engagement:%'"
    ).fetchall():
        results.record_review(
            PROJECT,
            "scenario_mapping",
            f"{scenario_id}|{explanation}",
            "Dr Example",
            "rejected",
            "unsupported mapping",
        )
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert state["recommended_experiment_id"] == "decision:exp:engagement-assay"
    assert state["diff"]["cause"] == ["review"]
    assert any(
        x["type"] == "scenario_mapping" and x["state"] == "rejected"
        for x in state["review_dependencies"]["review_excluded"]
    )


def test_rejected_cellular_assessment_is_excluded(world):
    store, protein, service, results, tmp = world
    ids = [
        a["id"]
        for a in store.cellular.collection(PROJECT, protein, "assessments", 100)[
            "items"
        ]
        if a["edge"] in ("hla", "immune")
    ]
    for identifier in ids:
        results.record_review(
            PROJECT,
            "evidence_assessment",
            identifier,
            "Dr Example",
            "rejected",
            "extraction unreliable",
        )
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert state["evidence"]["compound_phenotype_ids"] == []
    assert state["critical_uncertainty_id"] == "uncertainty:assay_translation"


# -- versioning: correction, withdrawal, duplicate, corruption ---------------------


def test_correction_supersedes_and_history_keeps_the_old_version(world):
    store, protein, service, results, tmp = world
    _, v2 = run_loop(
        world,
        "orig",
        [experiment("EX")],
        [result("RX", "EX", NOT_DETECTED, "no signal")],
        [interpretation("IX1", "RX", state="contradicted")],
    )
    assert (
        next(e for e in v2["explanations"] if e["ground"] == "on_target")["status"]
        == "weakened"
    )
    corrected = [
        result(
            "RX",
            "EX",
            DETECTED,
            "signal detected (corrected)",
            version=2,
            supersedes="RX@v1",
        )
    ]
    directory = package(
        tmp,
        "corr",
        [experiment("EX")],
        corrected,
        [interpretation("IX2", "RX")],
    )
    # the interpretation must reference the new version row; build it explicitly
    manifest = json.loads((directory / "manifest.json").read_text())
    results.import_package(PROJECT, directory, allow_synthetic=True)
    results.record_review(
        PROJECT, "experimental_result", "RX@v2", "Dr Example", "accepted", "corrected"
    )
    results.record_review(
        PROJECT, "result_interpretation", "IX2", "Dr Example", "accepted", "corrected"
    )
    assert manifest["results"][0]["version"] == 2
    ledger = {x["interpretation_id"]: x for x in results.ledger(PROJECT)}
    assert ledger["IX1"]["eligibility"]["state"] == "superseded"
    assert ledger["IX2"]["eligibility"]["eligible"]
    v3 = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert {c["id"] for c in v3["results"]["contributions"]} == {"IX2"}
    assert {c["id"] for c in v2["results"]["contributions"]} == {
        "IX1"
    }  # v2 still names v1 of the result
    assert [x["interpretation_id"] for x in store.results.state_links(v2["id"])] == [
        "IX1"
    ]
    with pytest.raises(ValueError, match="supersede the previous version"):
        store.results.add_result(
            ExperimentalResult(
                "RX",
                5,
                PROJECT,
                "EX",
                "cellular_engagement_signal",
                "binary_detection",
                FIXED,
                "x",
                qualitative_result="skipped versions",
                supersedes_id="RX@v4",
            )
        )


def test_withdrawal_updates_the_decision_without_deleting_history(world):
    store, protein, service, results, tmp = world
    v1 = service.current(PROJECT, protein)
    _, v2 = run_loop(
        world,
        "withdraw",
        [experiment("EW")],
        [result("RW", "EW", DETECTED)],
        [interpretation("IW", "RW")],
    )
    results.withdraw(PROJECT, "RW@v1", "Dr Example", "wrong plate")
    v3 = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert v3["results"]["contributions"] == []
    assert v3["diff"]["causes"][0]["category"] == "evidence_removed"
    assert v3["diff"]["causes"][0]["items"][0]["reason"] == "withdrawn"
    assert v3["effective_evidence"]["edges"] == v1["effective_evidence"]["edges"]
    assert [
        s["version"] for s in store.decisions.history(PROJECT, protein)["items"]
    ] == [3, 2, 1]
    assert json.dumps(
        store.decisions.state(PROJECT, protein, v2["id"]), sort_keys=True
    ) == json.dumps(v2, sort_keys=True)
    # v3 is scientifically equal to v1 but is a new, separate state
    assert v3["id"] != v1["id"]
    assert v3["critical_uncertainty_id"] == v1["critical_uncertainty_id"]


def test_duplicate_import_is_idempotent_and_conflicts_fail(world):
    store, protein, service, results, tmp = world
    directory = package(
        tmp,
        "dup",
        [experiment("ED1")],
        [result("RD1", "ED1", DETECTED)],
        [interpretation("ID1", "RD1")],
    )
    first = results.import_package(PROJECT, directory, allow_synthetic=True)

    def counts():
        return [
            store._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in (
                "experimental_results",
                "result_interpretations",
                "performed_experiments",
                "experiment_artifacts",
                "scenario_match_assessments",
            )
        ]

    before = counts()
    assert (
        results.import_package(PROJECT, directory, allow_synthetic=True)[
            "manifest_sha256"
        ]
        == first["manifest_sha256"]
    )
    assert counts() == before
    changed = package(
        tmp,
        "dup2",
        [experiment("ED1")],
        [result("RD1", "ED1", DETECTED, "a different observation")],
        [interpretation("ID1", "RD1")],
    )
    with pytest.raises(RecordConflictError):
        results.import_package(PROJECT, changed, allow_synthetic=True)
    assert counts() == before  # transactional


def test_artifact_checksums_detect_corruption(world):
    store, protein, service, results, tmp = world
    directory = package(
        tmp,
        "art",
        [experiment("EA")],
        [result("RA", "EA", DETECTED)],
        [interpretation("IA", "RA")],
    )
    results.import_package(PROJECT, directory, allow_synthetic=True)
    assert results.verify_artifacts(PROJECT, directory) == []
    target = directory / "raw" / "engagement-plate-reader.tsv"
    target.write_text(target.read_text() + "tampered\n")
    problems = results.verify_artifacts(PROJECT, directory)
    assert {"artifact": "synthetic:art:raw", "problem": "checksum mismatch"} in problems
    with pytest.raises(ValueError, match="checksum mismatch"):
        results.validate_package(PROJECT, directory, allow_synthetic=True)
    artifact = store.results.artifact("synthetic:art:raw")
    assert len(artifact["sha256"]) == 64 and artifact["size_bytes"] > 0


# -- validation, immutability, synthetic gate --------------------------------------


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda m: m["results"][0].update(experiment_id="nope"), "unknown experiment"),
        (
            lambda m: m["results"][0].update(endpoint="other_endpoint"),
            "is not an endpoint",
        ),
        (
            lambda m: m["results"][0].update(knowledge_kind="axis_observation"),
            "experimental_result",
        ),
        (
            lambda m: m["experiments"][0].update(compound_id="compound:invented"),
            "unknown compound",
        ),
        (lambda m: m.update(project_id="other"), "project does not match"),
        (lambda m: m.update(importer_version="axis-results-0"), "importer version"),
        (
            lambda m: m["results"][0].update(raw_artifact_ids=["missing"]),
            "unknown artifact",
        ),
        (
            lambda m: m["interpretations"][0].update(result_id="missing"),
            "unknown result",
        ),
        (lambda m: m["experiments"][0].update(measures_edges=[]), "measures_edges"),
        (
            lambda m: m.update(not_real_experimental_evidence=False),
            "not_real_experimental_evidence",
        ),
    ],
)
def test_import_validation_fails_loudly(world, mutate, message):
    store, protein, service, results, tmp = world
    directory = package(
        tmp,
        "bad",
        [experiment("EB")],
        [result("RB", "EB", DETECTED)],
        [interpretation("IB", "RB")],
        mutate=mutate,
    )
    with pytest.raises(ValueError, match=message):
        results.import_package(PROJECT, directory, allow_synthetic=True)
    assert (
        store._connection.execute(
            "SELECT count(*) FROM experimental_results"
        ).fetchone()[0]
        == 0
    )


def test_malformed_values_are_rejected_by_the_domain(world):
    base = dict(
        project_id=PROJECT,
        performed_experiment_id="E",
        endpoint="e",
        recorded_at=FIXED,
        recorded_by="x",
    )
    with pytest.raises(ValueError, match="requires a unit"):
        ExperimentalResult(
            id="r",
            version=1,
            result_type="numeric_measurement",
            numeric_value=4.5,
            **base,
        )
    with pytest.raises(ValueError, match="finite"):
        ExperimentalResult(
            id="r",
            version=1,
            result_type="numeric_measurement",
            numeric_value=float("nan"),
            unit="uM",
            **base,
        )
    with pytest.raises(ValueError, match="does not carry a number"):
        ExperimentalResult(
            id="r",
            version=1,
            result_type="binary_detection",
            numeric_value=1.0,
            unit="x",
            **base,
        )
    with pytest.raises(ValueError, match="experimental_result"):
        from axis.domain.models import KnowledgeKind

        ExperimentalResult(
            id="r",
            version=1,
            result_type="count",
            numeric_value=3.0,
            knowledge_kind=KnowledgeKind.AXIS_OBSERVATION,
            **base,
        )
    value = ExperimentalResult(
        id="r",
        version=1,
        result_type="numeric_measurement",
        numeric_value=42.0,
        operator="=",
        unit="percent",
        uncertainty="± 18",
        statistics={"sd": 18.0, "p": 0.04},
        **base,
    )
    assert (
        value.uncertainty == "± 18" and value.statistics["p"] == 0.04
    )  # preserved, not collapsed


def test_synthetic_gate_and_label(world):
    store, protein, service, results, tmp = world
    with pytest.raises(ValueError, match="allow-synthetic"):
        results.import_package(PROJECT)
    manifest = json.loads((SYN / "manifest.json").read_text())
    assert manifest["scientific_status"] == "synthetic_test_fixture"
    assert manifest["not_real_experimental_evidence"] is True
    assert "SYNTHETIC" in manifest["label"]
    results.import_package(PROJECT, allow_synthetic=True)
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert state["synthetic"] is True and state["results"]["synthetic"] is True
    assert state["results"]["contributions"][0]["synthetic"] is True


def test_results_are_immutable(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "imm",
        [experiment("EM")],
        [result("RM", "EM", DETECTED)],
        [interpretation("IM", "RM")],
        rebuild=False,
    )
    # AXIS repositories expose no update path for results at all
    assert not hasattr(store.results, "update_result")
    with pytest.raises(RecordConflictError):
        store.results.add_review(
            ScientificReview(
                store.results.reviews(PROJECT)[0]["id"],
                PROJECT,
                "experimental_result",
                "RM@v1",
                "Dr Example",
                "rejected",
                "overwrite",
                FIXED,
            )
        )
    assert len(store.results.reviews(PROJECT)) == 2


# -- causality, ordering, replay -----------------------------------------------------


def test_rule_change_and_result_change_are_attributed_differently(world, monkeypatch):
    store, protein, service, results, tmp = world
    _, v2 = run_loop(
        world,
        "causal",
        [experiment("EQ")],
        [result("RQ", "EQ", DETECTED)],
        [interpretation("IQ", "RQ")],
    )
    assert v2["diff"]["cause"] == ["evidence", "review"] or v2["diff"]["cause"] == [
        "evidence"
    ]
    assert v2["diff"]["causes"][0]["category"] == "new_experimental_evidence"
    monkeypatch.setattr(rules, "RULES_VERSION", "axis-decision-next")
    v3 = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert v3["diff"]["cause"] == ["methodology"]
    assert [c["category"] for c in v3["diff"]["causes"]] == ["methodology_change"]
    assert v3["diff"]["scientific_diff"]["evidence_status_changes"] == []


def test_import_order_does_not_change_the_decision(template, tmp_path):
    source, protein = template
    exps = [experiment("EA3"), experiment("EA2", compound="compound:maben-2")]
    res = [result("RA3", "EA3", DETECTED), result("RA2", "EA2", NOT_DETECTED)]
    ints = [
        interpretation("IA3", "RA3"),
        interpretation("IA2", "RA2", "compound:maben-2", state="contradicted"),
    ]
    outcomes = []
    for order in ((0, 1), (1, 0)):
        path = tmp_path / f"order{order[0]}.duckdb"
        shutil.copy(source, path)
        with EvidenceStore(path) as store:
            results = ResultsService(store)
            for index in order:
                directory = package(
                    tmp_path,
                    f"o{order[0]}{index}",
                    [exps[index]],
                    [res[index]],
                    [ints[index]],
                )
                results.import_package(PROJECT, directory, allow_synthetic=True)
            for r in res:
                results.record_review(
                    PROJECT,
                    "experimental_result",
                    f"{r['id']}@v1",
                    "Dr Example",
                    "accepted",
                    "ok",
                )
            for i in ints:
                results.record_review(
                    PROJECT,
                    "result_interpretation",
                    i["id"],
                    "Dr Example",
                    "accepted",
                    "ok",
                )
            state = DecisionService(store).rebuild(PROJECT, protein, created_at=FIXED)
            outcomes.append(
                {
                    k: json.dumps(state[k], sort_keys=True, default=str)
                    for k in (
                        "effective_evidence",
                        "uncertainties",
                        "explanations",
                        "critical_uncertainty_id",
                        "recommended_experiment_id",
                    )
                }
            )
    assert outcomes[0] == outcomes[1]


def test_two_store_network_off_llm_off_replay():
    def deny(*args, **kwargs):
        raise AssertionError("no network or model access is permitted")

    states = []
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
        patch.dict("sys.modules", {"anthropic": None, "openai": None}),
    ):
        for _ in range(2):
            with EvidenceStore() as store:
                protein, service = init(store)
                service.build(PROJECT, protein, created_at=FIXED)
                results = ResultsService(store)
                results.import_package(PROJECT, allow_synthetic=True)
                results.record_review(
                    PROJECT,
                    "experimental_result",
                    "synthetic:res:engagement-maben3@v1",
                    "Dr Example",
                    "accepted",
                    "frozen test review",
                )
                results.record_review(
                    PROJECT,
                    "result_interpretation",
                    "synthetic:int:engagement-maben3",
                    "Dr Example",
                    "accepted",
                    "frozen test review",
                )
                state = service.rebuild(PROJECT, protein, created_at=FIXED)
                states.append(json.dumps(state, sort_keys=True, default=str))
    assert states[0] == states[1]
    assert json.loads(states[0])["version"] == 2
    for path in (REPO / "axis" / "experiments").glob("*.py"):
        assert not re.search(
            r"^\s*(import|from)\s+(anthropic|openai|httpx|requests|urllib)",
            path.read_text(),
            re.M,
        ), path


# -- answers, API, CLI -----------------------------------------------------------------


def test_what_did_this_experiment_teach_us(world):
    store, protein, service, results, tmp = world
    results.import_package(PROJECT, allow_synthetic=True)
    results.record_review(
        PROJECT,
        "experimental_result",
        "synthetic:res:engagement-maben3@v1",
        "Dr Example",
        "accepted",
        "ok",
    )
    results.record_review(
        PROJECT,
        "result_interpretation",
        "synthetic:int:engagement-maben3",
        "Dr Example",
        "accepted",
        "ok",
    )
    service.rebuild(PROJECT, protein, created_at=FIXED)
    teach = service.answer(
        PROJECT, protein, "what_did_experiment_teach", "synthetic:exp:engagement-maben3"
    )["answer"]
    text = " ".join(teach)
    for needle in (
        "The experiment observed",
        "Eligibility under the review policy",
        "maps this to the engagement edge",
        "DECISION-RESULT-001",
        "DECISION-RESULT-002",
        "Did the decision change?",
        "Still unresolved",
    ):
        assert needle in text, needle
    predicted = service.answer(
        PROJECT, protein, "was_result_predicted", "synthetic:exp:engagement-maben3"
    )["answer"][0]
    assert predicted["overall"] == "matches"
    assert any(
        s["scenario"] == "decision:exp:engagement-assay:s1"
        and s["relationship"] == "matches"
        for s in predicted["scenarios"]
    )
    trust = service.answer(
        PROJECT, protein, "what_if_not_trusted", "synthetic:exp:engagement-maben3"
    )["answer"]
    assert (
        trust["decision_without_the_result"]["recommended"]
        == "decision:exp:chemical-genetic-engagement"
    )
    assert trust["review_states"] == {"synthetic:int:engagement-maben3": "accepted"}
    timeline = service.timeline(PROJECT)
    kinds = [t["kind"] for t in timeline]
    assert {"decision_state", "result_imported", "review"} <= set(kinds)
    with pytest.raises(RecordNotFoundError):
        service.answer(PROJECT, protein, "what_did_experiment_teach", "nope")


def test_api_exposes_the_loop_read_only(world):
    store, protein, service, results, tmp = world
    results.import_package(PROJECT, allow_synthetic=True)
    service.rebuild(PROJECT, protein, created_at=FIXED)
    api = ReadAPI(store)
    base = f"/api/projects/{PROJECT}"
    items = api.get(f"{base}/performed-experiments", {})["items"]
    assert (
        items[0]["synthetic"] is True
        and items[0]["scope"] == "compound:compound:maben-3"
    )
    detail = api.get(
        f"{base}/performed-experiments/synthetic:exp:engagement-maben3", {}
    )
    assert (
        detail["synthetic"]
        and detail["qc"]["assessment"] == "interpretable"
        and detail["proposal"]["knowledge_kind"] == "ai_suggestion"
    )
    ledger = api.get(f"{base}/results", {})
    assert (
        ledger["total"] == 1
        and ledger["items"][0]["eligibility"]["state"] == "pending_review"
    )
    row = "synthetic:res:engagement-maben3@v1"
    result = api.get(f"{base}/results/{row}", {})
    assert result["observed"]["facets"]["engagement_signal"] == "detected"
    assert result["artifacts"][0]["sha256"] and result["scenario_matches"]
    review = api.get(f"{base}/results/{row}/review", {})
    assert (
        review["review"]["state"] == "pending"
        and review["packet"]["reviewer_decision"] == "pending"
    )
    impact = api.get(
        f"{base}/results/{row}/decision-impact",
        {"interpretation": ["synthetic:int:engagement-maben3"]},
    )
    assert impact["applied"] is False and impact["label"].startswith("Preview")
    queue = api.get(f"{base}/review-queue", {})
    assert queue["mappings_total"] == 84 and queue[
        "scenario_mapping_review_counts"
    ] == {"pending": 84}
    assert (
        api.get(f"{base}/scenario-mappings", {"limit": ["5"]})["items"][0][
            "knowledge_kind"
        ]
        == "ai_suggestion"
    )
    assert api.get(f"{base}/decision/timeline", {})["items"]
    with pytest.raises(ValueError):
        api.get(f"{base}/results/{row}/decision-impact", {})
    with pytest.raises(RecordNotFoundError):
        api.get(f"{base}/results/nope@v1", {})
    with pytest.raises(RecordNotFoundError):
        api.get("/api/projects/AXIS-DD-ERAP1-001/results/x", {})
    assert api.get(f"{base}/decision/diff", {"from": ["1"], "to": ["2"]})["diff"][
        "causes"
    ]
    # GET never records a review or creates a state
    assert store.decisions.history(PROJECT, protein)["total"] == 2
    assert store.results.reviews(PROJECT) == []


def test_cli_loop(world, tmp_path):
    store, protein, service, results, tmp = world
    runner = CliRunner()
    path = tmp_path / "cli.duckdb"
    with EvidenceStore(path) as other:
        init(other)
        DecisionService(other).build(
            PROJECT, other.targets.project_ids(PROJECT)[0], created_at=FIXED
        )

    def run(*arguments, code=0):
        result = runner.invoke(app, ["--database", str(path), *arguments])
        assert result.exit_code == code, result.output
        return result.output

    run("experiment", "result", "import", PROJECT, code=1)  # synthetic needs the flag
    assert '"results": 1' in run(
        "experiment", "result", "validate", PROJECT, "--allow-synthetic"
    )
    assert '"decision_state_changed": false' in run(
        "experiment", "result", "import", PROJECT, "--allow-synthetic"
    )
    assert "pending_review" in run(
        "experiment", "result", "list", PROJECT
    ) and "[SYNTHETIC]" in run("experiment", "result", "list", PROJECT)
    run(
        "experiment",
        "result",
        "review",
        PROJECT,
        "--object-type",
        "experimental_result",
        "--object-id",
        "synthetic:res:engagement-maben3@v1",
        "--decision",
        "accepted",
        "--reviewer",
        "Dr Example",
        "--rationale",
        "ok",
    )
    run(
        "experiment",
        "result",
        "review",
        PROJECT,
        "--object-type",
        "result_interpretation",
        "--object-id",
        "synthetic:int:engagement-maben3",
        "--decision",
        "accepted",
        "--reviewer",
        "Dr Example",
        "--rationale",
        "ok",
    )
    run(
        "experiment",
        "result",
        "review",
        PROJECT,
        "--object-type",
        "result_interpretation",
        "--object-id",
        "x",
        "--decision",
        "accepted",
        "--reviewer",
        "AXIS",
        "--rationale",
        "ok",
        code=1,
    )
    assert "Preview — not current decision" in run(
        "experiment",
        "result",
        "impact",
        PROJECT,
        "--interpretation",
        "synthetic:int:engagement-maben3",
    )
    assert "Did the decision change?" in run("decision", "rebuild", PROJECT)
    assert "new_experimental_evidence" in run("decision", "diff", PROJECT)
    assert '"overall"' in run(
        "decision",
        "explain",
        PROJECT,
        "--question",
        "was_result_predicted",
        "--experiment",
        "synthetic:exp:engagement-maben3",
    )
    assert "Review packet" not in run(
        "experiment", "result", "packet", PROJECT, "synthetic:res:engagement-maben3@v1"
    )


# -- generic model, migration, hygiene -------------------------------------------------


def test_result_model_is_target_neutral_and_works_for_a_generic_target(world):
    text = (REPO / "axis/domain/results.py").read_text() + (
        REPO / "axis/experiments/policy.py"
    ).read_text()
    for word in ("ERAP1", "HLA", "axSpA", "immunopeptid", "B27"):
        assert word not in text, word
    store, protein, service, results, tmp = world
    DiscoveryService(store).create_erap1_demo()
    from axis.domain.results import (
        ExperimentalArtifact,
        PerformedExperiment,
        ResultInterpretation,
    )

    project = "AXIS-DD-ERAP1-001"
    store.results.add_artifact(
        ExperimentalArtifact("g:art", project, "g/raw.csv", "a" * 64, "text/csv", 10)
    )
    store.results.add_experiment(
        PerformedExperiment(
            "g:exp",
            project,
            None,
            "target",
            "TGT-X",
            ("biochemical",),
            ("signal",),
            "synthetic_test_fixture",
            context={"system": "generic"},
            target_label="TGT-X",
            source_artifact_ids=("g:art",),
        )
    )
    row = store.results.add_result(
        ExperimentalResult(
            "g:res",
            1,
            project,
            "g:exp",
            "signal",
            "numeric_measurement",
            FIXED,
            "tester",
            numeric_value=3.0,
            unit="dimensionless",
            raw_artifact_ids=("g:art",),
        )
    )
    from axis.domain.models import KnowledgeKind

    store.results.add_interpretation(
        ResultInterpretation(
            "g:int",
            row,
            "biochemical",
            "target",
            "TGT-X",
            "supported",
            "s",
            "r",
            KnowledgeKind.AI_SUGGESTION,
        )
    )
    results.record_review(
        project, "experimental_result", row, "Dr Example", "accepted", "ok"
    )
    results.record_review(
        project, "result_interpretation", "g:int", "Dr Example", "accepted", "ok"
    )
    entry = results.ledger(project, "reviewed")[0]
    assert entry["eligibility"]["state"] == "eligible" and entry["scope_id"] == "TGT-X"
    assert (
        entry["scenario_match"] == "ambiguous"
    )  # no proposal, no scenarios: nothing is forced


def test_migration_010_is_additive_and_upgrades_from_009(tmp_path):
    import subprocess

    root = REPO / "axis/storage/migrations"
    for path in sorted(root.glob("00[1-9]_*.sql")):
        original = subprocess.run(
            ["git", "show", f"ef03951:axis/storage/migrations/{path.name}"],
            capture_output=True,
            cwd=REPO,
        )
        if original.returncode == 0:
            assert (
                hashlib.sha256(original.stdout).hexdigest()
                == hashlib.sha256(path.read_bytes()).hexdigest()
            ), path.name
    sql = (root / "010_experimental_results.sql").read_text()
    assert not re.search(r"\b(DROP|ALTER|DELETE|UPDATE|CASCADE)\b", sql, re.I)
    assert sql.count("CREATE TABLE") == 12
    path = tmp_path / "schema9.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        for item in sorted(
            resources.files("axis.storage.migrations").iterdir(), key=lambda i: i.name
        ):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 9:
                connection.execute(item.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with EvidenceStore(path) as store:
        assert store.statistics().schema_version == 10
        protein, service = init(store)
        ResultsService(store).import_package(PROJECT, allow_synthetic=True)
    with EvidenceStore(path, read_only=True) as store:
        assert store.statistics().schema_version == 10
        assert store.results.results(PROJECT)
    with EvidenceStore() as clean:
        assert clean.statistics().schema_version == 10


def test_every_phase_36_rule_fired_in_this_module(world):
    """DECISION-RESULT-001/002/003, REPRO-002 and REVIEW-001 are exercised above."""
    store, protein, service, results, tmp = world
    exps = [experiment("EZ1"), experiment("EZ2")]
    res = [result("RZ1", "EZ1", DETECTED), result("RZ2", "EZ2", NOT_DETECTED)]
    ints = [
        interpretation("IZ1", "RZ1"),
        interpretation("IZ2", "RZ2", state="contradicted"),
    ]
    _, state = run_loop(world, "mixed", exps, res, ints)
    scope = state["effective_evidence"]["scoped_edges"]["engagement"][
        "compound:compound:maben-3"
    ]
    assert scope["state"] == "mixed"  # contradiction preserved, not averaged
    repro = next(
        u for u in state["uncertainties"] if u["category"] == "reproducibility"
    )
    assert "DECISION-REPRO-002" in repro["fired_rules"]
    assert state["review_dependencies"]["mode"] == "exploratory"
    fired = set(state["provenance"]["deterministic_rules"]) | {
        r for u in state["uncertainties"] for r in u["fired_rules"]
    }
    assert {"DECISION-RESULT-002", "DECISION-REPRO-002"} <= fired


def test_completed_is_not_the_same_as_interpretable(world):
    store, protein, service, results, tmp = world
    run_loop(
        world,
        "life",
        [experiment("EL", qc="non_interpretable")],
        [
            result(
                "RL",
                "EL",
                {"assay_validity": "failed"},
                rtype="technical_failure",
            )
        ],
        [],
        rebuild=False,
    )
    for status in ("investigator_selected", "planned", "in_progress"):
        service.set_experiment_status(PROJECT, ENGAGE, status, "Dr Example")
    with pytest.raises(ValueError, match="completed only with"):
        service.set_experiment_status(PROJECT, ENGAGE, "completed", "Dr Example")
    service.set_experiment_status(
        PROJECT, ENGAGE, "completed", "Dr Example", result_claim_id="RL@v1"
    )
    with pytest.raises(ValueError, match="matching quality assessment"):
        service.set_experiment_status(
            PROJECT, ENGAGE, "completed_interpretable", "Dr Example"
        )
    service.set_experiment_status(
        PROJECT, ENGAGE, "completed_non_interpretable", "Dr Example"
    )
    state = service.rebuild(PROJECT, protein, created_at=FIXED)
    assert (
        next(c for c in state["candidates"] if c["experiment_id"] == ENGAGE)["status"]
        == "completed_non_interpretable"
    )
