"""Phase 3.5: deterministic, categorical experimental decision engine."""

import copy
import hashlib
import json
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
from axis.domain.decision import (
    DecisionConsequence,
    DecisionState,
    ExplanationEvidenceLink,
    OutcomeInterpretation,
    ScientificUncertainty,
)
from axis.domain.models import (
    Claim,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
)
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ROOT = resources.files("axis").joinpath("resources/decision/erap1-axspa/v1")
FIXED = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
runner = CliRunner()


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    PharmacologyService(store).import_package(PROJECT, protein)
    CellularPharmacologyService(store).import_package(PROJECT, protein)
    service = DecisionService(store)
    service.import_package(PROJECT, protein)
    return protein, service


@pytest.fixture(scope="module")
def imported():
    with EvidenceStore() as store:
        protein, service = init(store)
        state = service.build(PROJECT, protein, created_at=FIXED)
        yield store, protein, service, state


@pytest.fixture
def fresh():
    with EvidenceStore() as store:
        protein, service = init(store)
        yield store, protein, service


def reference_evidence(imported):
    _, _, _, state = imported
    return copy.deepcopy(state["evidence"])


def with_evidence(service, evidence):
    """Make the service read a synthetic evidence state (no store mutation)."""
    service.evidence = lambda project, protein: copy.deepcopy(evidence)  # type: ignore[method-assign]


# -- frozen package ----------------------------------------------------------


def test_package_checksum_and_boundary():
    raw = ROOT.joinpath("manifest.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == ROOT.joinpath("manifest.sha256").read_text().strip()
    )
    package = json.loads(raw)
    assert "AI suggestion" in package["boundary"]
    assert "No experiment has been performed" in package["boundary"]
    assert len(package["candidate_experiments"]) >= 5


def test_import_is_idempotent_and_detects_tampering(fresh, tmp_path):
    store, protein, service = fresh
    assert service.import_package(PROJECT, protein)["candidate_experiments"] == 6
    assert len(store.decisions.profiles(PROJECT, protein)) == 6
    bad = tmp_path / "v1"
    shutil.copytree(Path(str(ROOT)), bad)
    manifest = bad / "manifest.json"
    manifest.write_text(manifest.read_text().replace("On-target", "Altered"))
    with pytest.raises(ValueError, match="checksum"):
        service.import_package(PROJECT, protein, bad)


def test_failed_import_rolls_back(tmp_path):
    with EvidenceStore() as store:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        bad = tmp_path / "v1"
        shutil.copytree(Path(str(ROOT)), bad)
        manifest = json.loads((bad / "manifest.json").read_text())
        manifest["candidate_experiments"][-1]["profile"]["addressed_gap_ids"] = [
            "gap:does-not-exist"
        ]
        raw = json.dumps(manifest).encode()
        (bad / "manifest.json").write_bytes(raw)
        (bad / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())
        service = DecisionService(store)
        with pytest.raises(Exception):  # noqa: B017 - foreign key violation
            service.import_package(PROJECT, protein, bad)
        assert store.decisions.explanations(PROJECT, protein) == []
        assert store.hypotheses.get_optional("AXIS-ERAP1-CURATED-HYP-001") is None
        for table, column in (
            ("proposed_experiments", "experiment_id"),
            ("outcome_scenarios", "scenario_id"),
            ("candidate_experiment_profiles", "experiment_id"),
        ):
            count = store._connection.execute(
                f"SELECT count(*) FROM {table} WHERE {column} LIKE 'decision:exp:%'"
            ).fetchone()[0]
            assert count == 0, table


# -- reference decision --------------------------------------------------------


def test_reference_decision_is_derived_not_hard_coded(imported):
    _, _, _, state = imported
    assert state["version"] == 1
    assert state["critical_uncertainty_id"] == "uncertainty:target_engagement"
    assert (
        state["recommended_experiment_id"] == "decision:exp:chemical-genetic-engagement"
    )
    statuses = {e["id"]: e["status"] for e in state["explanations"]}
    assert statuses == {
        "explanation:context": "viable",
        "explanation:indirect": "viable",
        "explanation:off_target": "viable",
        "explanation:on_target": "partially_supported",
    }
    assert state["status"] == "recorded"
    assert "not scientific truth" in state["disclaimer"]
    assert state["evidence"]["edges"]["engagement"]["state"] == "not_assessed"
    assert state["evidence"]["edges"]["biochemical"]["state"] == "supported"
    assert state["evidence"]["selectivity"]["comparable"] == 0


def test_no_scores_or_probabilities_anywhere(imported):
    _, _, _, state = imported
    banned = {
        "score",
        "probability",
        "information_gain",
        "entropy",
        "posterior",
        "confidence",
    }

    def walk(value, path=""):
        if isinstance(value, dict):
            for key, item in value.items():
                assert not any(word in key.lower() for word in banned), path + key
                walk(item, path + key + ".")
        elif isinstance(value, list):
            for item in value:
                walk(item, path)
        else:
            assert not isinstance(value, float), path

    trace = {k: v for k, v in state.items() if k != "evidence"}
    walk(trace)


def test_position_is_traceable_and_unresolved_listed(imported):
    _, _, _, state = imported
    position = state["position"]
    assert any("Biochemical" in item["statement"] for item in position["supported"])
    assert any(
        "Sources disagree" in item["statement"] for item in position["contradicted"]
    )
    assert any(
        "directly engage ERAP1" in item["statement"] for item in position["unresolved"]
    )
    for group in position.values():
        for item in group:
            assert item["refs"], item


def test_critical_trace_shows_every_alternative(imported):
    _, _, _, state = imported
    critical = state["critical"]
    ids = {u["id"] for u in state["uncertainties"]}
    assert {a["uncertainty_id"] for a in critical["alternatives"]} == ids - {
        critical["selected"]
    }
    assert all(a["reason"].startswith("not selected") for a in critical["alternatives"])
    assert any("selectivity is unresolved" in r for r in critical["reasons"])
    assert critical["rule"] == "DECISION-CRIT-001"


# -- uncertainties ------------------------------------------------------------


def test_uncertainty_missing_engagement_conflict_selectivity_context(imported):
    _, _, _, state = imported
    by = {u["category"]: u for u in state["uncertainties"]}
    engagement = by["target_engagement"]
    assert engagement["status"] == "open"
    assert engagement["decision_relevance"] == "decision_blocking"
    assert engagement["fired_rules"] == ["DECISION-GAP-001", "DECISION-GAP-002"]
    assert by["selectivity"]["resolvability"] == "indirectly_testable"
    assert by["genetic_context"]["status"] == "open"
    assert any("allotype" in r for r in by["genetic_context"]["reasons"])
    assert "reproducibility" in by
    assert "surface free heavy chain" in by["reproducibility"]["reasons"][0]
    assert by["disease_relevance"]["decision_relevance"] == "informative"


def test_non_actionable_uncertainties_are_not_selectable(imported):
    _, _, _, state = imported
    by = {u["category"]: u for u in state["uncertainties"]}
    assert by["clinical_translation"]["status"] == "not_actionable"
    assert state["critical_uncertainty_id"] != by["clinical_translation"]["id"]


def test_absence_of_evidence_is_not_contradiction(imported):
    _, _, _, state = imported
    for explanation in state["explanations"]:
        assert explanation["status"] != "contradicted"
        if explanation["id"] != "explanation:on_target":
            assert not any(
                link["relationship"] == "contradicts" for link in explanation["links"]
            )


def test_resolved_gap_changes_status_and_critical(imported):
    evidence = reference_evidence(imported)
    evidence["edges"]["engagement"]["state"] = "supported"
    uncertainties = {u.category: u for u in rules.derive_uncertainties(evidence)}
    assert uncertainties["target_engagement"].status == "resolved_for_current_decision"
    assert uncertainties["target_engagement"].decision_relevance == "informative"
    ids = {u.category for u in rules.derive_uncertainties(evidence)}
    assert "target_dependency" in ids


def test_rules_have_stable_identifiers_and_versions():
    assert rules.RULES_VERSION == "axis-decision-1"
    for rule_id, rule in rules.RULES.items():
        assert rule.id == rule_id and rule.version == "1"
        assert rule.description and rule.inputs and rule.output and rule.rationale
    assert "DECISION-GAP-001" in rules.RULES


# -- competing explanations ------------------------------------------------------


def link(relationship, identifier="x"):
    return ExplanationEvidenceLink("e", relationship, "gap", identifier, "R", "why")


@pytest.mark.parametrize(
    "relationships,expected",
    [
        (["supports"], "supported"),
        (["supports", "leaves_unresolved"], "partially_supported"),
        (["supports", "context_limits"], "partially_supported"),
        (["leaves_unresolved"], "viable"),
        (["context_limits"], "unresolved"),
        (["contradicts"], "contradicted"),
        (["supports", "contradicts"], "weakened"),
    ],
)
def test_explanation_status_from_links(relationships, expected):
    assert rules.explanation_status([link(r) for r in relationships]) == expected


def test_explanation_without_grounds_is_rejected_and_excluded(fresh, imported):
    store, protein, service = fresh
    evidence = reference_evidence(imported)
    evidence["functional_insufficient_ids"] = []
    assert (
        rules.explanation_links(evidence, "indirect_pathway", "explanation:indirect")
        == []
    )
    with pytest.raises(ValueError, match="grounded"):
        rules.explanation_status([])
    with_evidence(service, evidence)
    state = service.build(PROJECT, protein, created_at=FIXED)
    assert "explanation:indirect" not in {e["id"] for e in state["explanations"]}
    assert state["excluded_explanations"][0]["id"] == "explanation:indirect"
    assert "mechanistic_bridge" not in {u["category"] for u in state["uncertainties"]}


def test_contradicted_explanation_via_engagement_and_selectivity(imported):
    evidence = reference_evidence(imported)
    evidence["edges"]["engagement"]["state"] = "supported"
    evidence["selectivity"] = {"total": 2, "comparable": 2, "unresolved_ids": []}
    links = rules.explanation_links(evidence, "off_target", "explanation:off_target")
    assert rules.explanation_status(links) == "contradicted"
    assert not rules.off_target_viable(evidence)
    evidence["concordance"]["discordant_ids"] = ["a:b"]
    weakened = rules.explanation_links(evidence, "off_target", "explanation:off_target")
    assert rules.explanation_status(weakened) == "weakened"


def test_context_limited_explanation(imported):
    _, _, _, state = imported
    context = next(e for e in state["explanations"] if e["id"] == "explanation:context")
    assert {x["relationship"] for x in context["links"]} == {
        "leaves_unresolved",
        "context_limits",
    }


def test_domain_validation():
    with pytest.raises(ValueError):
        ScientificUncertainty(
            "u", "bogus", "q", "open", "peripheral", "unknown", "r", ("R",)
        )
    with pytest.raises(ValueError, match="rule"):
        ScientificUncertainty(
            "u", "other", "q", "open", "peripheral", "unknown", "r", ()
        )
    with pytest.raises(ValueError, match="conditionally"):
        DecisionConsequence("s", "supportive", "stop_for_now", "Run the experiment now")
    with pytest.raises(ValueError):
        OutcomeInterpretation("s", "e", "probable", "x")


# -- critical uncertainty selection ----------------------------------------------


def uncertainty(
    identifier, category, relevance, resolvability, affected, status="open"
):
    return ScientificUncertainty(
        identifier,
        category,
        "q",
        status,
        relevance,
        resolvability,
        "r",
        ("R",),
        affected_explanation_ids=tuple(affected),
    )


def test_selection_blocking_testable_beats_downstream_and_peripheral():
    a = uncertainty(
        "A", "target_engagement", "decision_blocking", "directly_testable", ["x", "y"]
    )
    b = uncertainty(
        "B", "disease_relevance", "decision_material", "directly_testable", ["x", "y"]
    )
    c = uncertainty("C", "clinical_translation", "peripheral", "directly_testable", [])
    info = {"target_engagement": {"count": 1, "consequences": 2}}
    selection = rules.select_critical([c, b, a], {"x", "y"}, info)
    assert selection["selected"] == "A"
    reasons = {x["uncertainty_id"]: x["reason"] for x in selection["alternatives"]}
    assert "decision relevance" in reasons["B"]
    assert "decision relevance" in reasons["C"]
    resolved = uncertainty(
        "A",
        "target_engagement",
        "informative",
        "directly_testable",
        ["x"],
        "resolved_for_current_decision",
    )
    assert rules.select_critical([c, b, resolved], {"x", "y"}, info)["selected"] == "B"


def test_selection_prefers_more_explanations_separated_then_resolvability():
    a = uncertainty(
        "A", "genetic_context", "decision_material", "directly_testable", ["x"]
    )
    b = uncertainty(
        "B", "selectivity", "decision_material", "directly_testable", ["x", "y"]
    )
    assert rules.select_critical([a, b], {"x", "y"}, {})["selected"] == "B"
    c = uncertainty(
        "C", "selectivity", "decision_material", "indirectly_testable", ["x"]
    )
    assert rules.select_critical([c, a], {"x"}, {})["selected"] == "A"


def test_resolving_critical_uncertainty_promotes_another(fresh, imported):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    evidence = reference_evidence(imported)
    evidence["edges"]["engagement"]["state"] = "supported"
    evidence["gap_ids"] = []
    with_evidence(service, evidence)
    second = service.build(PROJECT, protein, created_at=FIXED)
    assert first["critical_uncertainty_id"] == "uncertainty:target_engagement"
    assert second["critical_uncertainty_id"] == "uncertainty:target_dependency"
    assert second["supersedes_id"] == first["id"]
    changes = second["diff"]["changes"]
    assert any(c.startswith("Engagement: not assessed → supported") for c in changes)
    assert any(c.startswith("Critical uncertainty:") for c in changes)
    assert any(
        c.startswith("Recommended experiment:") or "Uncertainty target engagement" in c
        for c in changes
    )


# -- candidate experiments -------------------------------------------------------


def test_discrimination_unit():
    separating = {
        "s1": {"a": "strengthens", "b": "weakens"},
        "s2": {"a": "weakens", "b": "strengthens"},
    }
    flat = {
        "s1": {"a": "weakens", "b": "weakens"},
        "s2": {"a": "does_not_discriminate", "b": "does_not_discriminate"},
    }
    assert rules.discrimination(separating, {"a", "b"})["separated_pairs"] == [
        ("a", "b")
    ]
    result = rules.discrimination(flat, {"a", "b"})
    assert result["low_discrimination"] and result["separated_pairs"] == []
    assert rules.discrimination(separating, {"a"})["low_discrimination"]


def test_replication_is_flagged_low_discrimination(imported):
    _, _, _, state = imported
    item = next(
        c
        for c in state["candidates"]
        if c["experiment_id"] == "decision:exp:phenotype-replication"
    )
    assert (
        item["low_discrimination"] and item["discrimination"]["separated_pairs"] == []
    )
    assert item["profile"]["role"] == "replication"
    assert item["role_label"].startswith("low discrimination")
    assert "low discrimination" in item["reason"]
    chosen = next(
        c
        for c in state["candidates"]
        if c["experiment_id"] == state["recommended_experiment_id"]
    )
    assert len(chosen["discrimination"]["separated_pairs"]) > 0


def test_candidates_for_critical_uncertainty_are_ranked_without_scores(imported):
    _, _, _, state = imported
    ranked = sorted(
        (c for c in state["candidates"] if c["rank"]), key=lambda c: c["rank"]
    )
    assert [c["experiment_id"] for c in ranked][0] == state["recommended_experiment_id"]
    assert 2 <= len(ranked) <= 5
    assert {c["rank"] for c in ranked} == set(range(1, len(ranked) + 1))
    other = [c for c in state["candidates"] if not c["rank"]]
    assert other and all(c["reason"].startswith("not compared") for c in other)


def test_cost_time_feasibility_are_not_invented(imported):
    _, _, _, state = imported
    for item in state["candidates"]:
        assert item["cost"] == "not provided"
        assert item["profile"]["time_estimate"] == "unknown"
        assert item["feasibility"]["level"] == "unknown"
        assert (
            "not assessed against local resource constraints"
            in item["feasibility"]["note"]
        )
    assert state["constraints"]["note"].startswith("Feasibility not assessed")


def test_interpretability_rule_levels():
    profile = {
        "controls_negative": ["v"],
        "controls_positive": [],
        "target_proximity": "target_proximal",
        "confounders_addressed": ["c"],
    }
    assert (
        rules.interpretability(profile, ["supportive", "negative", "alternative"])[
            "level"
        ]
        == "high"
    )
    assert (
        rules.interpretability(profile, ["supportive", "non_interpretable"])["level"]
        == "moderate"
    )
    weak = profile | {"target_proximity": "downstream", "confounders_addressed": []}
    assert (
        rules.interpretability(weak, ["supportive", "non_interpretable"])["level"]
        == "low"
    )
    empty = profile | {"controls_negative": []}
    assert rules.interpretability(empty, ["a"])["level"] == "unknown"


def test_investigator_constraints_change_feasibility_and_exclusion(fresh):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    service.set_constraints(
        PROJECT,
        "Dr Example",
        available_models=["HLA-B27-positive cell line", "ERAP1-depleted control"],
        available_assays=["cellular engagement assay"],
        available_compounds=["engagement readout reagent"],
        excluded_experiment_ids=["decision:exp:chemical-genetic-engagement"],
    )
    second = service.build(PROJECT, protein, created_at=FIXED)
    levels = {
        c["experiment_id"]: c["feasibility"]["level"] for c in second["candidates"]
    }
    assert levels["decision:exp:chemical-genetic-engagement"] == "blocked"
    assert levels["decision:exp:engagement-assay"] == "feasible_with_current_resources"
    assert second["recommended_experiment_id"] == "decision:exp:engagement-assay"
    assert second["recommended_experiment_id"] != first["recommended_experiment_id"]
    assert second["supersedes_id"] == first["id"]
    assert "Investigator constraints changed" in second["diff"]["changes"]
    with pytest.raises(ValueError, match="next version"):
        from axis.domain.decision import DecisionConstraints

        store.decisions.add_constraints(
            DecisionConstraints("dup", PROJECT, 1, FIXED, "x")
        )


# -- outcomes and consequences ---------------------------------------------------


def test_outcome_tree_has_all_kinds_and_conditional_consequences(imported):
    _, _, _, state = imported
    scenarios = state["recommendation"]["outcome_scenarios"]
    kinds = {s["kind"] for s in scenarios}
    assert {"supportive", "negative", "alternative", "non_interpretable"} <= kinds
    for scenario in scenarios:
        assert scenario["prospective"] is True
        assert scenario["consequence"]["statement"].startswith("If ")
        assert not scenario["consequence"]["statement"].lower().startswith("run ")
    negative = next(s for s in scenarios if s["kind"] == "negative")
    assert negative["consequence"]["category"] == "weaken_current_strategy"
    assert {e["effect"] for e in negative["explanation_effects"]} >= {
        "weakens",
        "strengthens",
    }
    uninterpretable = next(s for s in scenarios if s["kind"] == "non_interpretable")
    assert {e["effect"] for e in uninterpretable["explanation_effects"]} == {
        "does_not_discriminate"
    }
    assert uninterpretable["consequence"]["new_uncertainty"]


def test_what_would_change_our_mind(imported):
    _, _, _, state = imported
    mind = state["what_would_change_our_mind"]
    assert "prospective" in mind["label"]
    assert mind["would_weaken"] and mind["would_strengthen"]
    first = mind["would_weaken"][0]
    assert first["hypothesis_id"] == state["hypothesis_id"]
    assert first["experiment_id"] == state["recommended_experiment_id"]
    assert first["explanation_effects"]


def test_why_this_experiment_section(imported):
    _, _, _, state = imported
    why = state["recommendation"]["why_this_experiment"]
    assert why["explanations_separated"]
    assert why["why_current_evidence_cannot_answer"]
    assert why["remains_unresolved"]
    assert state["recommendation"]["controls"]["positive"]


def test_graph_paths_and_link_tables(imported):
    store, protein, _, state = imported
    kinds = {e["kind"] for e in state["graph"]["edges"]}
    assert {"addressed_by", "discriminates", "affects", "informs"} <= kinds
    assert all(e["basis"] for e in state["graph"]["edges"])
    assert (
        len(store.decisions.gap_links("decision:exp:chemical-genetic-engagement")) == 4
    )
    assert "explanation:on_target" in store.decisions.discriminates(
        "decision:exp:chemical-genetic-engagement"
    )
    assert store.decisions.interpretations("decision:exp:engagement-assay")


# -- versioning ------------------------------------------------------------------


def test_replay_is_idempotent_and_states_immutable(fresh):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    again = service.build(PROJECT, protein, created_at=datetime.now(UTC))
    assert again["id"] == first["id"]
    assert store.decisions.history(PROJECT, protein)["total"] == 1
    altered = dict(first, rationale="tampered")
    state = DecisionState(
        first["id"],
        PROJECT,
        protein,
        1,
        first["hypothesis_id"],
        1,
        FIXED,
        "x",
        first["evidence_digest"],
        first["rules_version"],
        "r",
    )
    with pytest.raises(RecordConflictError):
        store.decisions.add_state(state, altered)
    with pytest.raises(ValueError, match="immutable"):
        DecisionState(
            "s", PROJECT, protein, 1, "h", 1, FIXED, "x", "d", "v", "r", status="edited"
        )


def test_investigator_status_events_create_new_version_and_guard_completion(fresh):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    experiment = first["recommended_experiment_id"]
    with pytest.raises(ValueError, match="cannot move"):
        service.set_experiment_status(PROJECT, experiment, "completed", "Dr Example")
    with pytest.raises(ValueError, match="investigator"):
        service.set_experiment_status(PROJECT, experiment, "investigator_selected", " ")
    service.set_experiment_status(
        PROJECT, experiment, "investigator_selected", "Dr Example"
    )
    second = service.build(PROJECT, protein, created_at=FIXED)
    assert second["version"] == 2
    assert experiment in second["provenance"]["investigator_approved"]
    item = next(c for c in second["candidates"] if c["experiment_id"] == experiment)
    assert item["status"] == "investigator_selected"
    for to in ("planned", "in_progress"):
        service.set_experiment_status(PROJECT, experiment, to, "Dr Example")
    with pytest.raises(ValueError, match="result claim"):
        service.set_experiment_status(PROJECT, experiment, "completed", "Dr Example")
    observation = Claim(
        "RESULT-1",
        EntityRef(EntityKind.GENE, "ENSG00000164307", "ERAP1", "Ensembl"),
        "engages",
        EntityRef(EntityKind.GENE, "ENSG00000164307", "ERAP1", "Ensembl"),
        KnowledgeKind.AXIS_OBSERVATION,
        Provenance(SourceKind.AXIS_PIPELINE, "lab", FIXED),
    )
    store.claims.add(observation)
    with pytest.raises(ValueError, match="experimental_result"):
        service.set_experiment_status(
            PROJECT, experiment, "completed", "Dr Example", result_claim_id="RESULT-1"
        )
    store.claims.add(
        Claim(
            "RESULT-2",
            observation.subject,
            "engages",
            observation.object,
            KnowledgeKind.EXPERIMENTAL_RESULT,
            Provenance(SourceKind.RESEARCHER, "lab", FIXED),
        )
    )
    done = service.set_experiment_status(
        PROJECT, experiment, "completed", "Dr Example", result_claim_id="RESULT-2"
    )
    assert done["to"] == "completed"
    with pytest.raises(ValueError, match="cannot move"):
        service.set_experiment_status(PROJECT, experiment, "planned", "Dr Example")


def test_epistemic_boundaries_and_explicit_promotion(fresh):
    store, protein, service = fresh
    state = service.build(PROJECT, protein, created_at=FIXED)
    assert state["hypothesis"]["knowledge_kind"] == "ai_suggestion"
    assert all(e["knowledge_kind"] == "ai_suggestion" for e in state["explanations"])
    experiment = store.proposed_experiments.get(state["recommended_experiment_id"])
    assert experiment.knowledge_kind == KnowledgeKind.AI_SUGGESTION
    scenarios = store.outcome_scenarios.list_for_experiment(experiment.experiment_id)
    assert scenarios and all(s.possible_outcome for s in scenarios)
    assert state["recommendation"]["status"] == "proposed"
    assert "No experiment has been performed" in state["disclaimer"]
    assert state["provenance"]["investigator_approved"] == []
    service.promote_explanation(
        PROJECT, "explanation:on_target", "Dr Example", "reviewed"
    )
    with pytest.raises(ValueError, match="already"):
        service.promote_explanation(PROJECT, "explanation:on_target", "Dr Example")
    with pytest.raises(RecordNotFoundError):
        service.promote_explanation(PROJECT, "explanation:nope", "Dr Example")
    promoted = service.build(PROJECT, protein, created_at=FIXED)
    on_target = next(
        e for e in promoted["explanations"] if e["id"] == "explanation:on_target"
    )
    assert on_target["knowledge_kind"] == "researcher_hypothesis"
    assert "explanation:on_target" in promoted["provenance"]["investigator_approved"]
    assert "explanation:on_target" not in promoted["provenance"]["ai_generated"]


def test_grounded_answers_read_only_stored_state(imported):
    _, protein, service, state = imported
    assert service.answer(PROJECT, protein, "why_critical")["answer"]
    against = service.answer(PROJECT, protein, "evidence_against")["answer"]
    assert any("disagree" in item["statement"] for item in against)
    why_not = service.answer(
        PROJECT, protein, "why_not", "decision:exp:phenotype-replication"
    )["answer"][0]
    assert "low discrimination" in why_not
    assert service.answer(PROJECT, protein, "what_would_change_our_mind")["answer"]
    with pytest.raises(ValueError):
        service.answer(PROJECT, protein, "invent_a_fact")


# -- storage ---------------------------------------------------------------------


def test_migration_9_clean_and_legacy_upgrade(tmp_path):
    path = tmp_path / "schema8.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        root = resources.files("axis.storage.migrations")
        for item in sorted(root.iterdir(), key=lambda item: item.name):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 8:
                connection.execute(item.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with EvidenceStore(path) as store:
        assert store.statistics().schema_version == 9
        protein, service = init(store)
        service.build(PROJECT, protein, created_at=FIXED)
    with EvidenceStore(path, read_only=True) as store:
        assert store.statistics().schema_version == 9
        assert store.decisions.latest_state(
            PROJECT, store.targets.project_ids(PROJECT)[0]
        )
    with EvidenceStore() as clean:
        assert clean.statistics().schema_version == 9


def test_referential_integrity_and_child_rows(imported):
    store, protein, _, state = imported
    db = store._connection
    assert db.execute(
        "SELECT count(*) FROM decision_uncertainties WHERE decision_state_id=?",
        [state["id"]],
    ).fetchone()[0] == len(state["uncertainties"])
    assert db.execute(
        "SELECT count(*) FROM decision_explanation_links WHERE decision_state_id=?",
        [state["id"]],
    ).fetchone()[0] == sum(len(e["links"]) for e in state["explanations"])
    assert (
        db.execute("SELECT count(*) FROM critical_uncertainty_assessments").fetchone()[
            0
        ]
        == 1
    )
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO outcome_interpretations VALUES "
            "('missing-scenario','explanation:on_target','weakens','x')"
        )
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO decision_experiment_gaps VALUES "
            "('decision:exp:engagement-assay','gap:none')"
        )


def test_project_isolation_and_unknown_scope(imported):
    store, protein, service, state = imported
    with pytest.raises(RecordNotFoundError):
        store.decisions.state("other-project", protein, state["id"])
    with pytest.raises(RecordNotFoundError):
        store.decisions.profile(
            PROJECT, "protein:other", "decision:exp:engagement-assay"
        )
    with pytest.raises(RecordNotFoundError):
        service.candidate(PROJECT, protein, "decision:exp:missing")
    assert store.decisions.history(PROJECT, protein, 5)["has_more"] is False
    with pytest.raises(ValueError):
        store.decisions.history(PROJECT, protein, 0)


# -- offline replay --------------------------------------------------------------


def test_two_stores_produce_identical_decisions_offline():
    def deny(*args, **kwargs):
        raise AssertionError("network disabled")

    results = []
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
    ):
        for _ in range(2):
            with EvidenceStore() as store:
                protein, service = init(store)
                results.append(
                    canonical(service.build(PROJECT, protein, created_at=FIXED))
                )
    assert results[0] == results[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, default=str)


# -- API and CLI -----------------------------------------------------------------


def test_api_routes_and_errors(imported):
    store, protein, _, state = imported
    api = ReadAPI(store)
    base = f"/api/projects/{PROJECT}"
    assert api.get(f"{base}/decision", {})["state"]["id"] == state["id"]
    assert api.get(f"{base}/decision/history", {})["items"][0]["id"] == state["id"]
    uncertainties = api.get(f"{base}/uncertainties", {})
    assert uncertainties["critical"]["selected"] == "uncertainty:target_engagement"
    assert len(api.get(f"{base}/explanations", {})["items"]) == 4
    experiments = api.get(f"{base}/candidate-experiments", {})
    assert (
        experiments["recommended_experiment_id"] == state["recommended_experiment_id"]
    )
    detail = api.get(f"{base}/candidate-experiments/decision:exp:engagement-assay", {})
    assert detail["scenarios"] and detail["addressed_gap_ids"]
    assert all(
        x["consequence"]["statement"].startswith("If ") for x in detail["scenarios"]
    )
    trace = api.get(f"{base}/decision-trace", {})
    assert trace["trace"]["rules_fired"] and trace["graph"]["edges"]
    with pytest.raises(RecordNotFoundError):
        api.get(f"{base}/candidate-experiments/missing", {})
    with pytest.raises(RecordNotFoundError):
        api.get(f"{base}/decision/unknown", {})
    with pytest.raises(Exception):  # noqa: B017 - unknown project
        api.get("/api/projects/nope/decision", {})
    with pytest.raises(ValueError):
        api.get(f"{base}/decision", {"compound": ["x"]})


def test_api_get_never_builds_or_uses_network():
    def deny(*args, **kwargs):
        raise AssertionError("network disabled")

    with EvidenceStore() as store:
        protein, _ = init(store)
        api = ReadAPI(store)
        with (
            patch.object(socket.socket, "connect", deny),
            patch.object(httpx.Client, "request", deny),
        ):
            empty = api.get(f"/api/projects/{PROJECT}/decision", {})
            assert empty["state"] is None and "axis decision build" in empty["message"]
            with pytest.raises(RecordNotFoundError):
                api.get(f"/api/projects/{PROJECT}/explanations", {})
        assert store.decisions.latest_state(PROJECT, protein) is None


def test_cli_build_show_explain_history(tmp_path):
    database = str(tmp_path / "cli.duckdb")
    with EvidenceStore(database) as store:
        protein, _ = init(store)
        store.decisions  # noqa: B018 - ensure repository exists

    def run(*arguments):
        result = runner.invoke(app, ["--database", database, "decision", *arguments])
        assert result.exit_code == 0, result.output
        return result.output

    assert "DecisionState v1" in run("build", PROJECT)
    assert "DecisionState v1" in run("build", PROJECT)  # idempotent
    assert "Critical uncertainty: uncertainty:target_engagement" in run("show", PROJECT)
    assert "decision:exp:chemical-genetic-engagement" in run("experiments", PROJECT)
    assert "decision blocking" in run("explain", PROJECT)
    assert "low discrimination" in run(
        "explain",
        PROJECT,
        "--question",
        "why_not",
        "--experiment",
        "decision:exp:phenotype-replication",
    )
    assert "v1 decision-state:1" in run("history", PROJECT)
    run("constraints", PROJECT, "--investigator", "Dr Example", "--model", "cells")
    assert "DecisionState v2" in run("build", PROJECT)
