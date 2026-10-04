"""Phase 3.5A acceptance: counterfactuals, purity, ordering, replay and boundaries.

Counterfactual states are TEST-ONLY mutations of a deep copy of the stored
evidence; production evidence is never altered.
"""

import copy
import hashlib
import json
import random
import re
import shutil
import socket
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from axis.api.server import ReadAPI
from axis.cellular.service import CellularPharmacologyService
from axis.decision import engine, rules
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.discovery.service import DiscoveryService
from axis.domain.discovery import OutcomeScenario
from axis.domain.models import (
    Claim,
    EntityKind,
    EntityRef,
    HypothesisRevision,
    HypothesisState,
    KnowledgeKind,
    Provenance,
    SourceKind,
)
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordNotFoundError
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ROOT = Path(str(resources.files("axis").joinpath("resources/decision/erap1-axspa/v1")))
REPO = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
FIRED: set[str] = set()


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    PharmacologyService(store).import_package(PROJECT, protein)
    CellularPharmacologyService(store).import_package(PROJECT, protein)
    service = DecisionService(store)
    service.import_package(PROJECT, protein)
    return protein, service


@pytest.fixture(scope="module")
def world():
    with EvidenceStore() as store:
        protein, service = init(store)
        state = service.build(PROJECT, protein, created_at=FIXED)
        yield store, protein, service, state, service.inputs(PROJECT, protein)


@pytest.fixture
def fresh():
    with EvidenceStore() as store:
        protein, service = init(store)
        yield store, protein, service


def run(inputs, mutate=None, **override):
    data = copy.deepcopy(inputs)
    if mutate:
        mutate(data["evidence"])
    data.update(override)
    analysis = engine.analyze(data, with_sensitivity=False)
    FIRED.update(analysis["provenance"]["deterministic_rules"])
    return analysis


def statuses(analysis):
    return {e["id"]: e["status"] for e in analysis["explanations"]}


def uncertainties(analysis):
    return {u["category"]: u for u in analysis["uncertainties"]}


def edge(evidence, name, state, ids=()):
    evidence["edges"][name] = {"state": state, "ids": list(ids)}


# -- production decision is derived, not displayed ----------------------------


def test_production_decision_equals_a_pure_recomputation(world):
    _, _, _, state, inputs = world
    analysis = run(inputs)
    assert analysis["critical_uncertainty_id"] == state["critical_uncertainty_id"]
    assert analysis["recommended_experiment_id"] == state["recommended_experiment_id"]
    assert statuses(analysis) == {e["id"]: e["status"] for e in state["explanations"]}
    assert (
        json.loads(json.dumps(analysis["uncertainties"], default=str))
        == state["uncertainties"]
    )


def test_no_target_specific_branch_in_decision_logic():
    sources = {
        name: (REPO / "axis" / "decision" / name).read_text()
        for name in ("rules.py", "engine.py")
    }
    for name, text in sources.items():
        code = "\n".join(
            line
            for line in text.splitlines()
            if not line.lstrip().startswith(("#", '"'))
        )
        assert not re.search(r"==\s*[\"'](ERAP1|Q9NZ08)", code), name
        assert not re.search(r"(if|elif)[^\n]*(erap1|q9nz08|hla-b27)", code, re.I), name
        # explanation ids are never hard-coded in logic: grounds are the contract
        assert "explanation:" not in text, name


# -- counterfactuals 1-10 --------------------------------------------------------


def test_cf1_resolving_the_winner_promotes_another_or_reports_none(world):
    _, _, _, state, inputs = world

    def resolve(e):
        edge(e, "engagement", "supported", ["engagement-1"])
        e["gap_ids"] = []

    analysis = run(inputs, resolve)
    assert state["critical_uncertainty_id"] == "uncertainty:target_engagement"
    assert (
        uncertainties(analysis)["target_engagement"]["status"]
        == "resolved_for_current_decision"
    )
    assert analysis["critical_uncertainty_id"] not in (
        None,
        "uncertainty:target_engagement",
    )


def test_cf2_removed_support_changes_links_and_never_leaves_a_stale_recommendation(
    world,
):
    _, _, _, state, inputs = world
    removed = {
        *inputs["evidence"]["biochemical_ids"],
        *inputs["evidence"]["genetic_dependency_ids"],
    }

    def drop(e):
        e["biochemical_ids"] = []
        e["genetic_dependency_ids"] = []

    analysis = run(inputs, drop)
    on_target = next(e for e in analysis["explanations"] if e["ground"] == "on_target")
    assert removed
    assert not removed & {link["evidence_id"] for link in on_target["links"]}
    base = next(e for e in state["explanations"] if e["ground"] == "on_target")
    assert len(on_target["links"]) < len(base["links"])

    def drop_phenotype(e):
        e["compound_phenotype_ids"] = []
        e["compound_dependency_uncertain_ids"] = []
        edge(e, "hla", "not_assessed")
        edge(e, "immune", "not_assessed")

    stale = run(inputs, drop_phenotype)
    assert stale["recommended_experiment_id"] != state["recommended_experiment_id"]
    assert stale["critical_uncertainty_id"] == "uncertainty:assay_translation"


def test_cf3_contradictory_engagement_stays_a_contradiction(world):
    _, _, _, _, inputs = world

    def contradict(e):
        edge(e, "engagement", "contradicted", ["engagement-negative"])
        e["gap_ids"] = []

    analysis = run(inputs, contradict)
    by = {e["ground"]: e for e in analysis["explanations"]}
    assert by["on_target"]["status"] == "weakened"
    assert any(
        link["relationship"] == "contradicts" and link["evidence_id"] == "engagement"
        for link in by["on_target"]["links"]
    )
    assert any(
        link["relationship"] == "supports" and link["evidence_id"] == "engagement"
        for link in by["off_target"]["links"]
    )
    assert any(
        row.get("edge") == "engagement" and "is contradicted" in row["statement"]
        for row in analysis["position"]["contradicted"]
    )
    assert (
        uncertainties(analysis)["target_engagement"]["status"]
        == "resolved_for_current_decision"
    )
    assert analysis["critical_uncertainty_id"] != "uncertainty:target_engagement"


def test_cf4_biochemical_activity_without_cellular_phenotype(world):
    _, _, _, state, inputs = world

    def only_biochemical(e):
        for key in (
            "compound_phenotype_ids",
            "genetic_phenotype_ids",
            "genetic_dependency_ids",
            "compound_dependency_uncertain_ids",
            "compound_dependency_supported_ids",
            "functional_insufficient_ids",
            "gap_ids",
        ):
            e[key] = []
        e["source_disagreements"] = []
        for name in ("hla", "immune", "engagement", "functional", "exposure"):
            edge(e, name, "not_assessed")

    analysis = run(inputs, only_biochemical)
    assert analysis["critical_uncertainty_id"] == "uncertainty:assay_translation"
    assert analysis["recommended_experiment_id"] is None
    assert analysis["recommendation"] is None
    assert "no unblocked candidate" in analysis["no_experiment_message"]
    assert not any(e["ground"] == "on_target" for e in analysis["explanations"])
    assert analysis["recommended_experiment_id"] != state["recommended_experiment_id"]


def test_cf5_engagement_without_phenotype_differs_from_the_reverse(world):
    _, _, _, state, inputs = world

    def engaged_only(e):
        for key in (
            "compound_phenotype_ids",
            "genetic_dependency_ids",
            "compound_dependency_uncertain_ids",
            "functional_insufficient_ids",
            "gap_ids",
        ):
            e[key] = []
        edge(e, "engagement", "supported", ["engagement-1"])
        edge(e, "hla", "contradicted", ["hla-negative"])

    analysis = run(inputs, engaged_only)
    by = uncertainties(analysis)
    assert "target_engagement" not in by
    assert by["mechanistic_bridge"]["fired_rules"] == ["DECISION-BRIDGE-002"]
    assert not any(e["ground"] == "on_target" for e in analysis["explanations"])
    production = next(
        u for u in state["uncertainties"] if u["category"] == "mechanistic_bridge"
    )
    assert production["fired_rules"] == ["DECISION-BRIDGE-001"]


def test_cf6_phenotype_without_engagement_does_not_establish_the_mechanism(world):
    _, _, _, state, _ = world
    by = {e["ground"]: e for e in state["explanations"]}
    assert by["on_target"]["status"] == "partially_supported"
    assert by["off_target"]["status"] == "viable"
    engagement = next(
        u for u in state["uncertainties"] if u["category"] == "target_engagement"
    )
    assert engagement["status"] == "open"
    assert engagement["decision_relevance"] == "decision_blocking"
    assert state["evidence"]["edges"]["engagement"]["state"] == "not_assessed"


def test_cf7_comparable_selectivity_weakens_but_does_not_eliminate_off_target(world):
    _, _, _, _, inputs = world

    def comparable(e):
        e["selectivity"] = {
            "total": 4,
            "comparable": 4,
            "unresolved_ids": [],
            "comparable_ids": ["sel-1", "sel-2", "sel-3", "sel-4"],
            "by_status": {"Comparable": 4},
        }

    analysis = run(inputs, comparable)
    by = {e["ground"]: e for e in analysis["explanations"]}
    assert by["off_target"]["status"] == "weakened"
    assert by["off_target"]["status"] != "contradicted"
    assert any(
        link["relationship"] == "leaves_unresolved"
        for link in by["off_target"]["links"]
    )
    u = uncertainties(analysis)
    assert u["selectivity"]["status"] == "resolved_for_current_decision"
    assert u["target_engagement"]["decision_relevance"] == "decision_material"
    assert u["target_engagement"]["fired_rules"] == ["DECISION-GAP-001"]


def test_cf8_many_incompatible_measurements_are_not_selectivity(world):
    _, _, _, state, inputs = world
    sel = state["evidence"]["selectivity"]
    assert sel["total"] == 18 and sel["comparable"] == 0
    assert set(sel["by_status"]) == {"Not assessed", "Not directly comparable"}
    assert sel["by_status"]["Not assessed"] == 4

    def many(e):
        e["selectivity"] = {
            "total": 500,
            "comparable": 0,
            "unresolved_ids": [f"sel-{i}" for i in range(500)],
            "comparable_ids": [],
            "by_status": {"Not directly comparable": 500},
        }

    analysis = run(inputs, many)
    u = uncertainties(analysis)
    assert u["selectivity"]["status"] == "open"
    assert "500 not directly comparable" in " ".join(u["selectivity"]["reasons"])
    assert u["target_engagement"]["decision_relevance"] == "decision_blocking"
    keys: set[str] = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                keys.add(key)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(state)
    assert not {k for k in keys if k == "ratio" or k.startswith("ratio_")}
    assert "censor" not in json.dumps(state)


def generic_inputs():
    names = (
        "exposure",
        "biochemical",
        "engagement",
        "functional",
        "hla",
        "immune",
        "disease",
        "clinical",
    )
    evidence = {
        "target_label": "TGT-9",
        "edges": {n: {"state": "not_assessed", "ids": []} for n in names},
        "biochemical_ids": ["m1"],
        "compound_phenotype_ids": ["a1"],
        "genetic_phenotype_ids": [],
        "genetic_dependency_ids": [],
        "compound_dependency_uncertain_ids": ["a1"],
        "compound_dependency_supported_ids": [],
        "functional_insufficient_ids": [],
        "gap_ids": ["g1"],
        "selectivity": {
            "total": 2,
            "comparable": 0,
            "unresolved_ids": ["s1", "s2"],
            "comparable_ids": [],
            "by_status": {"Not assessed": 2},
        },
        "concordance": {
            "concordant": 0,
            "discordant": 0,
            "not_comparable": 0,
            "discordant_ids": [],
        },
        "source_disagreements": [],
        "contexts": {
            "allotype_reported": True,
            "unmatched_context_experiments": 0,
            "hla_alleles": [],
        },
        "structure_ids": [],
        "review": {"pending_expert_review": 0, "accepted": 1},
    }
    evidence["edges"]["biochemical"] = {"state": "supported", "ids": ["m1"]}
    evidence["edges"]["hla"] = {"state": "supported", "ids": ["a1"]}

    def scenario(key, kind, on, off, category):
        return {
            "scenario_id": f"x:{key}",
            "kind": kind,
            "outcome": f"Outcome {key}",
            "interpretation": "i",
            "effects": {
                "e-on": {"effect": on, "rationale": "r"},
                "e-off": {"effect": off, "rationale": "r"},
            },
            "consequence": {
                "category": category,
                "statement": "If so, adapt.",
                "new_uncertainty": None,
            },
        }

    profile = {
        "experiment_id": "x",
        "purpose": "establish_target_engagement",
        "role": "mechanism_discrimination",
        "target_proximity": "target_proximal",
        "disease_relevance": "n/a",
        "considered_for": ["target_engagement"],
        "addressed_gap_ids": [],
        "controls_negative": ["vehicle"],
        "controls_positive": [],
        "primary_endpoint": "p",
        "secondary_endpoints": [],
        "limitations": ["l"],
        "prerequisites": [],
        "required": {},
        "confounders_addressed": ["c"],
        "context_requirements": {},
        "complexity": "low",
        "time_estimate": "unknown",
        "cost": None,
    }
    candidate = {
        "experiment_id": "x",
        "title": "Generic engagement assay",
        "rationale": "r",
        "experimental_system": "generic system",
        "intervention_description": "generic",
        "endpoint_description": "e",
        "knowledge_kind": "ai_suggestion",
        "profile": profile,
        "status": "proposed",
        "result_claim_id": None,
        "scenarios": [
            scenario(
                "1",
                "supportive",
                "strengthens",
                "weakens",
                "strengthen_current_strategy",
            ),
            scenario(
                "2", "negative", "weakens", "strengthens", "weaken_current_strategy"
            ),
            scenario(
                "3",
                "non_interpretable",
                "does_not_discriminate",
                "does_not_discriminate",
                "require_replication",
            ),
        ],
    }
    return {
        "evidence": evidence,
        "explanations": [
            {
                "id": "e-on",
                "ground": "on_target",
                "label": "On target",
                "statement": "s",
                "knowledge_kind": "ai_suggestion",
            },
            {
                "id": "e-off",
                "ground": "off_target",
                "label": "Off target",
                "statement": "s",
                "knowledge_kind": "ai_suggestion",
            },
        ],
        "hypothesis": {
            "id": "H",
            "title": "t",
            "description": "d",
            "state": "draft",
            "revision": 1,
        },
        "candidates": [candidate],
        "constraints": None,
        "promoted": [],
        "statuses": {},
    }


def test_cf9_a_non_erap1_target_needs_no_erap1_or_hla_assumptions():
    analysis = engine.analyze(generic_inputs(), with_sensitivity=False)
    FIRED.update(analysis["provenance"]["deterministic_rules"])
    assert analysis["critical_uncertainty_id"] == "uncertainty:target_engagement"
    assert analysis["recommended_experiment_id"] == "x"
    text = json.dumps(
        {
            k: analysis[k]
            for k in ("uncertainties", "critical", "explanations", "position")
        }
    )
    assert "TGT-9" in text
    for forbidden in ("ERAP1", "HLA-B27", "axSpA", "immunopeptid"):
        assert forbidden not in text, forbidden
    assert analysis["recommendation"]["why_this_experiment"]["explanations_separated"]


def test_cf10_no_actionable_uncertainty_yields_no_experiment(world):
    _, _, _, _, inputs = world

    def everything_resolved(e):
        edge(e, "engagement", "supported", ["engagement-1"])
        edge(e, "disease", "supported", ["disease-1"])
        e["gap_ids"] = []
        e["compound_dependency_uncertain_ids"] = []
        e["compound_dependency_supported_ids"] = ["dep-1"]
        e["functional_insufficient_ids"] = []
        e["source_disagreements"] = []
        e["contexts"] = {
            "allotype_reported": True,
            "unmatched_context_experiments": 0,
            "hla_alleles": [],
        }
        e["selectivity"] = {
            "total": 2,
            "comparable": 2,
            "unresolved_ids": [],
            "comparable_ids": ["s1", "s2"],
            "by_status": {"Comparable": 2},
        }

    analysis = run(inputs, everything_resolved)
    assert analysis["critical_uncertainty_id"] is None
    assert analysis["recommended_experiment_id"] is None
    assert analysis["recommendation"] is None
    assert analysis["critical"]["message"].endswith("currently justified.")
    assert analysis["no_experiment_message"] == engine.NO_EXPERIMENT
    assert all(
        u["status"] in ("resolved_for_current_decision", "not_actionable")
        for u in analysis["uncertainties"]
    )


def test_empty_candidate_and_explanation_sets_are_explicit(world):
    _, _, _, _, inputs = world
    none = run(inputs, candidates=[])
    assert none["recommended_experiment_id"] is None
    assert none["critical_uncertainty_id"] is not None
    assert "no unblocked candidate" in none["no_experiment_message"]
    nothing = run(inputs, explanations=[])
    assert nothing["explanations"] == []
    assert nothing["recommendation"] is None  # nothing separates no explanations
    assert (
        "accepted discriminating outcome mappings" in nothing["no_experiment_message"]
    )


# -- purity, ordering, rule versioning -------------------------------------------


def test_rules_are_pure_and_deterministic_without_network(world):
    _, _, _, state, inputs = world

    def deny(*args, **kwargs):
        raise AssertionError("network disabled")

    snapshot = copy.deepcopy(inputs)
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
    ):
        first = engine.analyze(inputs)
        second = engine.analyze(inputs)
    assert inputs == snapshot  # inputs never mutated
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )
    ev = copy.deepcopy(inputs["evidence"])
    assert [u.id for u in rules.derive_uncertainties(ev)] == [
        u.id for u in rules.derive_uncertainties(ev)
    ]
    assert ev == inputs["evidence"]


def shuffled(value, rnd):
    if isinstance(value, dict):
        items = list(value.items())
        rnd.shuffle(items)
        return {k: shuffled(v, rnd) for k, v in items}
    if isinstance(value, list):
        out = [shuffled(v, rnd) for v in value]
        if all(isinstance(v, str | dict) for v in out):
            rnd.shuffle(out)
        return out
    return value


@pytest.mark.parametrize("seed", range(6))
def test_input_order_never_changes_the_decision(world, seed):
    _, _, _, _, inputs = world
    rnd = random.Random(seed)
    reordered = copy.deepcopy(inputs)
    reordered["evidence"] = shuffled(reordered["evidence"], rnd)
    rnd.shuffle(reordered["candidates"])
    rnd.shuffle(reordered["explanations"])
    for candidate in reordered["candidates"]:
        rnd.shuffle(candidate["scenarios"])
    base = engine.analyze(inputs, with_sensitivity=False)
    other = engine.analyze(reordered, with_sensitivity=False)
    assert json.dumps(base, sort_keys=True, default=str) == json.dumps(
        other, sort_keys=True, default=str
    )
    assert other["recommended_experiment_id"] == base["recommended_experiment_id"]


def test_ties_are_reported_not_resolved_by_identifier(world):
    _, _, _, _, inputs = world
    data = copy.deepcopy(inputs)
    twin = copy.deepcopy(
        next(
            c
            for c in data["candidates"]
            if c["experiment_id"] == "decision:exp:engagement-assay"
        )
    )
    twin["experiment_id"] = "decision:exp:aaa-twin"
    twin["profile"]["experiment_id"] = twin["experiment_id"]
    twin["title"] = "Twin of the engagement assay"
    data["candidates"].append(twin)
    analysis = engine.analyze(data, with_sensitivity=False)
    tied = {c["experiment_id"]: c for c in analysis["candidates"]}
    original = tied["decision:exp:engagement-assay"]
    assert original["tied_with"] == ["decision:exp:aaa-twin"]
    assert "tied" in tied["decision:exp:aaa-twin"]["reason"]
    assert "display convention" in " ".join(
        [original["reason"], tied["decision:exp:aaa-twin"]["reason"]]
    )


def test_evidence_change_and_methodology_change_are_distinguishable(fresh, monkeypatch):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    base_inputs = service.inputs(PROJECT, protein)

    # A: evidence changes, rules constant
    changed = copy.deepcopy(base_inputs["evidence"])
    edge(changed, "engagement", "supported", ["engagement-1"])
    changed["gap_ids"] = []
    monkeypatch.setattr(
        service, "evidence", lambda project, protein, *_: copy.deepcopy(changed)
    )
    second = service.build(PROJECT, protein, created_at=FIXED)
    assert second["diff"]["cause"] == ["evidence"]
    assert "stored evidence changed" in second["diff"]["cause_summary"]
    assert second["methodology"] == first["methodology"]
    assert second["digests"]["evidence"] != first["digests"]["evidence"]
    monkeypatch.undo()

    # B: rules change, evidence constant
    with EvidenceStore() as other:
        protein_b, service_b = init(other)
        v1 = service_b.build(PROJECT, protein_b, created_at=FIXED)
        monkeypatch.setattr(rules, "RULES_VERSION", "axis-decision-next")
        v2 = service_b.build(PROJECT, protein_b, created_at=FIXED)
        assert v2["diff"]["cause"] == ["methodology"]
        assert "methodology" in v2["diff"]["cause_summary"]
        assert v2["digests"]["evidence"] == v1["digests"]["evidence"]
        assert v2["methodology"]["rules_version"] == "axis-decision-next"
        assert (
            v2["methodology"]["rules_fingerprint"]
            != v1["methodology"]["rules_fingerprint"]
        )
        assert v2["critical_uncertainty_id"] == v1["critical_uncertainty_id"]


def test_persisted_states_are_immutable_across_later_changes(fresh, monkeypatch):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    snapshot = json.dumps(
        store.decisions.state(PROJECT, protein, first["id"]), sort_keys=True
    )
    service.set_constraints(PROJECT, "Dr Example", available_models=["cells"])
    monkeypatch.setattr(rules, "RULES_VERSION", "axis-decision-next")
    service.build(PROJECT, protein, created_at=FIXED)
    service.import_package(PROJECT, protein)  # fixture replay
    assert (
        json.dumps(store.decisions.state(PROJECT, protein, first["id"]), sort_keys=True)
        == snapshot
    )
    assert store.decisions.history(PROJECT, protein)["total"] == 2


def test_hypothesis_revision_is_used_and_never_substituted(fresh):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    stored = store.hypotheses.get(first["hypothesis_id"])
    assert first["hypothesis_revision"] == stored.current.revision == 1
    assert first["hypothesis"]["description"] == stored.current.description
    assert first["hypothesis"]["state"] == "draft"
    store.hypotheses.append_revision(
        first["hypothesis_id"],
        HypothesisRevision(
            2,
            datetime(2026, 10, 5, tzinfo=UTC),
            HypothesisState.ACTIVE,
            "Revised working formulation.",
            "Researcher revision.",
        ),
    )
    second = service.build(PROJECT, protein, created_at=FIXED)
    assert second["hypothesis_revision"] == 2
    assert second["hypothesis"]["description"] == "Revised working formulation."
    assert second["diff"]["cause"] == ["methodology"]
    assert (
        store.decisions.state(PROJECT, protein, first["id"])["hypothesis_revision"] == 1
    )


# -- store-level determinism -----------------------------------------------------


def reversed_cellular_package(tmp_path):
    source = Path(
        str(resources.files("axis").joinpath("resources/cellular/erap1-axspa/v1"))
    )
    target = tmp_path / "cellular"
    shutil.copytree(source, target)
    package = json.loads((target / "manifest.json").read_text())
    for key in ("experiments", "readouts", "assessments", "gaps", "immunopeptidome"):
        package[key] = list(reversed(package[key]))
    raw = json.dumps(package).encode()
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())
    return target


def test_database_insertion_order_does_not_change_the_decision(world, tmp_path):
    _, _, _, state, _ = world
    with EvidenceStore() as store:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(
            PROJECT, protein, reversed_cellular_package(tmp_path)
        )
        service = DecisionService(store)
        service.import_package(PROJECT, protein)
        other = service.build(PROJECT, protein, created_at=FIXED)
    assert json.dumps(other["evidence"], sort_keys=True) == json.dumps(
        state["evidence"], sort_keys=True
    )
    for key in (
        "critical_uncertainty_id",
        "recommended_experiment_id",
        "explanations",
        "uncertainties",
        "candidates",
    ):
        assert json.dumps(other[key], sort_keys=True) == json.dumps(
            state[key], sort_keys=True
        ), key


def test_duplicate_replay_creates_no_duplicate_entities(fresh):
    store, protein, service = fresh
    service.build(PROJECT, protein, created_at=FIXED)
    counts = lambda: {  # noqa: E731
        table: store._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "decision_explanations",
            "decision_states",
            "decision_uncertainties",
            "candidate_experiment_profiles",
            "outcome_scenarios",
            "outcome_interpretations",
            "decision_consequences",
            "hypotheses",
            "hypothesis_revisions",
        )
    }
    before = counts()
    service.import_package(PROJECT, protein)
    service.build(PROJECT, protein, created_at=FIXED)
    assert counts() == before


def test_llm_and_network_free_replay_is_identical_from_frozen_resources():
    def deny(*args, **kwargs):
        raise AssertionError("no network or model access is permitted")

    outputs = []
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
        patch.dict("sys.modules", {"anthropic": None, "openai": None}),
    ):
        for _ in range(2):
            with EvidenceStore() as store:
                protein, service = init(store)
                outputs.append(
                    json.dumps(
                        service.build(PROJECT, protein, created_at=FIXED),
                        sort_keys=True,
                    )
                )
    assert outputs[0] == outputs[1]
    for path in (REPO / "axis" / "decision").glob("*.py"):
        text = path.read_text()
        assert not re.search(
            r"^\s*(import|from)\s+(anthropic|openai|httpx|requests|urllib)", text, re.M
        ), path


# -- isolation and boundaries ----------------------------------------------------


def test_project_and_compound_isolation(fresh):
    store, protein, service = fresh
    state = service.build(PROJECT, protein, created_at=FIXED)
    DiscoveryService(store).create_erap1_demo()
    with pytest.raises(RecordNotFoundError):
        store.decisions.state("AXIS-DD-ERAP1-001", protein, state["id"])
    assert store.decisions.latest_state("AXIS-DD-ERAP1-001", protein) is None
    with pytest.raises(RecordNotFoundError):
        ReadAPI(store).get("/api/projects/AXIS-DD-ERAP1-001/explanations", {})
    coverage = state["evidence"]["compound_coverage"]
    rows = {c["compound_id"]: c for c in coverage["compounds"]}
    assert rows["compound:maben-1"] == {
        "compound_id": "compound:maben-1",
        "biochemical": True,
        "cellular_phenotype": False,
    }
    assert rows["compound:maben-2"]["cellular_phenotype"] is True
    assert coverage["unresolved_identity_perturbagens"]
    assert not any("dg013" in c["compound_id"].lower() for c in coverage["compounds"])
    reasons = " ".join(
        next(u for u in state["uncertainties"] if u["category"] == "target_engagement")[
            "reasons"
        ]
    )
    assert "not pooled across compounds" in reasons
    assert "unresolved chemical identity" in reasons


def test_chemical_identity_and_context_epistemology(world):
    _, _, _, state, _ = world
    text = json.dumps(state)
    assert "CHEMBL" not in text.upper().replace(
        "CHEMBL-", "CHEMBL"
    )  # no provider mapping resurrected
    assert "CHEMBL" not in text
    ev = state["evidence"]
    assert ev["contexts"]["hla_alleles"] == ["HLA-B*27:05"]
    assert ev["contexts"]["unmatched_context_experiments"] > 0
    assert ev["contexts"]["allotype_reported"] is False
    maben = [
        link
        for e in state["explanations"]
        for link in e["links"]
        if "maben" in link["evidence_id"]
        and link["rationale"].startswith("Compound phenotype reported")
    ]
    assert maben
    assert all(
        "H-2Kb" in link["rationale"] and "no HLA allele reported" in link["rationale"]
        for link in maben
    )
    assert ev["edges"]["disease"]["state"] == "not_assessed"
    assert ev["edges"]["clinical"]["state"] == "not_assessed"
    assert not re.search(r"validated (across|target|in axspa)", text.lower())


def test_layers_are_not_collapsed_and_structure_never_supports(world):
    _, _, _, state, _ = world
    edges = state["evidence"]["edges"]
    assert edges["biochemical"]["state"] == "supported"
    assert edges["engagement"]["state"] == "not_assessed"
    assert edges["functional"]["state"] == "insufficient"
    supported = {row["edge"] for row in state["position"]["supported"]}
    assert {"biochemical", "hla", "immune", "exposure"} == supported
    assert not {"engagement", "functional", "disease", "clinical"} & supported
    assert not any(
        link["evidence_type"] == "structure"
        for e in state["explanations"]
        for link in e["links"]
    )
    _, _, _, _, inputs = world
    analysis = run(inputs, lambda e: e.update(structure_ids=["structure:synthetic"]))
    structural = uncertainties(analysis)["structural_mechanism"]
    assert structural["status"] == "not_actionable"
    assert structural["decision_relevance"] == "peripheral"
    assert analysis["critical_uncertainty_id"] != structural["id"]
    assert not any(
        link["evidence_type"] == "structure"
        for e in analysis["explanations"]
        for link in e["links"]
    )


def test_prospective_scenarios_and_proposals_never_count_as_evidence(fresh):
    store, protein, service = fresh
    before = service.evidence(PROJECT, protein)
    experiment = "decision:exp:engagement-assay"
    store.outcome_scenarios.add(
        OutcomeScenario(
            "decision:exp:engagement-assay:extra",
            experiment,
            "Engagement is observed",
            "positive",
        )
    )
    after = service.evidence(PROJECT, protein)
    assert after == before  # a prospective scenario is never evidence
    with pytest.raises(ValueError, match="no stored DecisionConsequence"):
        service.build(PROJECT, protein, created_at=FIXED)
    assert store.decisions.latest_state(PROJECT, protein) is None


def test_closed_loop_with_a_synthetic_result_never_overwrites_the_proposal(
    fresh, monkeypatch
):
    store, protein, service = fresh
    first = service.build(PROJECT, protein, created_at=FIXED)
    experiment = first["recommended_experiment_id"]
    for status in ("investigator_selected", "planned", "in_progress"):
        service.set_experiment_status(PROJECT, experiment, status, "Dr Example")
    gene = EntityRef(EntityKind.GENE, "SYN-1", "SYN-1", "TEST")
    store.claims.add(
        Claim(
            "SYNTHETIC-RESULT-1",
            gene,
            "engages",
            gene,
            KnowledgeKind.EXPERIMENTAL_RESULT,
            Provenance(SourceKind.RESEARCHER, "synthetic-test", FIXED),
        )
    )
    service.set_experiment_status(
        PROJECT,
        experiment,
        "completed",
        "Dr Example",
        result_claim_id="SYNTHETIC-RESULT-1",
    )
    changed = copy.deepcopy(service.inputs(PROJECT, protein)["evidence"])
    edge(changed, "engagement", "supported", ["synthetic-engagement"])
    changed["gap_ids"] = []
    monkeypatch.setattr(
        service, "evidence", lambda project, protein, *_: copy.deepcopy(changed)
    )
    second = service.build(PROJECT, protein, created_at=FIXED)
    item = next(c for c in second["candidates"] if c["experiment_id"] == experiment)
    assert (
        item["status"] == "completed"
        and item["result_claim_id"] == "SYNTHETIC-RESULT-1"
    )
    assert second["critical_uncertainty_id"] != first["critical_uncertainty_id"]
    proposal = store.proposed_experiments.get(experiment)
    assert proposal.knowledge_kind == KnowledgeKind.AI_SUGGESTION
    assert (
        store.claims.get("SYNTHETIC-RESULT-1").knowledge_kind
        == KnowledgeKind.EXPERIMENTAL_RESULT
    )
    assert first["results"]["synthetic"] is False
    assert not first["results"]["contributions"]


# -- review status, sensitivity, provenance --------------------------------------


def test_pending_review_is_visible_and_excluding_it_changes_the_decision(world):
    _, _, _, state, _ = world
    assert state["review"]["pending_expert_review"] > 0
    assert state["review"]["accepted"] == 0
    assert state["review"]["message"].startswith(
        "This recommendation depends on evidence"
    )
    sensitivity = state["sensitivity"]
    assert sensitivity["method"].startswith("categorical")
    decisive = {row["group"]: row for row in sensitivity["decision_sensitive"]}
    pending = decisive["pending_review_cellular"]
    assert any("critical uncertainty" in c for c in pending["changes"])
    assert any("recommended experiment" in c for c in pending["changes"])
    assert "compound_phenotype" in decisive
    covered = {
        r["group"]
        for k in ("decision_sensitive", "explanation_sensitive", "non_decisive")
        for r in sensitivity[k]
    }
    assert {"biochemical", "engagement"} <= covered or "biochemical" in covered
    assert isinstance(sensitivity["non_decisive"], list)


def test_every_displayed_statement_has_an_epistemic_class(world):
    _, _, _, state, _ = world
    allowed = {
        "source_assertion",
        "experimental_result",
        "axis_observation",
        "axis_inference",
        "ai_suggestion",
        "researcher_hypothesis",
    }
    kinds = [
        row["epistemic_kind"] for rows in state["position"].values() for row in rows
    ]
    kinds += [u["epistemic_kind"] for u in state["uncertainties"]]
    kinds += [e["knowledge_kind"] for e in state["explanations"]]
    kinds += [c["epistemic_kind"] for c in state["candidates"]]
    kinds += [s["epistemic_kind"] for s in state["recommendation"]["outcome_scenarios"]]
    kinds += [state["hypothesis"]["knowledge_kind"]]
    assert kinds and set(kinds) <= allowed


def test_every_link_terminates_in_a_stored_record_with_a_source_locator(world):
    store, protein, _, state, _ = world
    tables = {
        "measurement": ("bioactivity_measurements", "id"),
        "cellular_assessment": ("cellular_assessments", "id"),
        "gap": ("open_questions", "question_id"),
        "selectivity_assessment": ("selectivity_assessments", "id"),
        "readout": ("experimental_readouts", "id"),
    }
    checked = 0
    for explanation in state["explanations"]:
        for link in explanation["links"]:
            if link["evidence_type"] in tables:
                table, column = tables[link["evidence_type"]]
                assert store._connection.execute(
                    f"SELECT 1 FROM {table} WHERE {column}=?", [link["evidence_id"]]
                ).fetchone(), link
                checked += 1
    assert checked > 30
    assessment = next(
        link["evidence_id"]
        for e in state["explanations"]
        for link in e["links"]
        if link["evidence_type"] == "cellular_assessment"
    )
    detail = store.cellular.detail(PROJECT, protein, "assessments", assessment)
    experiment = store.cellular.detail(
        PROJECT, protein, "experiments", detail["experiment_id"]
    )
    assert experiment["source_id"] and experiment["locator"]
    readouts = [
        r
        for r in store.cellular.collection(PROJECT, protein, "readouts", 100)["items"]
        if r["experiment_id"] == experiment["id"]
    ]
    assert readouts and all(r["locator"] for r in readouts)
    first = readouts[0]
    if first["claim_id"]:
        assert store.claims.get(first["claim_id"]).provenance.source_identifier


def test_outcome_tree_text_is_conditional_and_every_branch_names_effects(world):
    _, _, _, state, _ = world
    for scenario in state["recommendation"]["outcome_scenarios"]:
        assert scenario["prospective"] is True
        assert scenario["consequence"]["statement"].startswith("If ")
        assert scenario["explanation_effects"]
    negative = [
        s
        for s in state["recommendation"]["outcome_scenarios"]
        if s["kind"] == "negative"
    ]
    assert negative
    assert any(
        e["effect"] in ("weakens", "contradicts") and "on_target" in e["explanation_id"]
        for e in negative[0]["explanation_effects"]
    )
    assert (
        state["candidates"]
        and next(
            c
            for c in state["candidates"]
            if c["experiment_id"] == state["recommended_experiment_id"]
        )["falsification"]["falsifying"]
    )


# -- integrity, fixture, migration, frontend --------------------------------------


def test_fixture_contains_wording_only_no_evidence_or_decisions():
    package = json.loads((ROOT / "manifest.json").read_text())
    assert set(package["explanations"][0]) == {"id", "ground", "label", "statement"}
    forbidden = {
        "status",
        "recommended",
        "critical",
        "uncertainties",
        "evidence",
        "links",
        "rank",
        "score",
    }
    assert not forbidden & set(package)
    for candidate in package["candidate_experiments"]:
        assert not forbidden & set(candidate) - {"profile"}
    assert "AI suggestion" in package["boundary"]


def test_integrity_failures_fail_loudly(fresh, tmp_path):
    store, protein, service = fresh
    for mutate, message in (
        (lambda m: m.update(importer_version="axis-decision-0"), "importer"),
    ):
        bad = tmp_path / message
        shutil.copytree(ROOT, bad)
        manifest = json.loads((bad / "manifest.json").read_text())
        mutate(manifest)
        raw = json.dumps(manifest).encode()
        (bad / "manifest.json").write_bytes(raw)
        (bad / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())
        with pytest.raises(ValueError, match=message):
            service.import_package(PROJECT, protein, bad)
    bad = tmp_path / "scenario"
    shutil.copytree(ROOT, bad)
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["candidate_experiments"][0]["scenarios"][0]["kind"] = "triumphant"
    raw = json.dumps(manifest).encode()
    (bad / "manifest.json").write_bytes(raw)
    (bad / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())
    with EvidenceStore() as other:
        protein_b, service_b = init(other)
    with EvidenceStore() as clean:
        import_curated_erap1(clean)
        protein_c = TargetIdentityService(clean).import_package(PROJECT)
        PharmacologyService(clean).import_package(PROJECT, protein_c)
        CellularPharmacologyService(clean).import_package(PROJECT, protein_c)
        with pytest.raises(ValueError):
            DecisionService(clean).import_package(PROJECT, protein_c, bad)
        with pytest.raises(ValueError, match="not imported"):
            DecisionService(clean).build(PROJECT, protein_c)
    with pytest.raises(RecordNotFoundError):
        service.current("no-such-project", protein)
    with pytest.raises(Exception):  # noqa: B017 - unknown project
        service.build("no-such-project", protein)


def test_migrations_001_to_008_are_unchanged_and_009_is_additive():
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((REPO / "axis/storage/migrations").glob("00[1-8]_*.sql"))
    }
    import subprocess

    for name, digest in expected.items():
        original = subprocess.run(
            ["git", "show", f"11458e2:axis/storage/migrations/{name}"],
            capture_output=True,
            cwd=REPO,
        )
        if original.returncode == 0:
            assert hashlib.sha256(original.stdout).hexdigest() == digest, name
    sql = (REPO / "axis/storage/migrations/009_experimental_decision.sql").read_text()
    assert not re.search(r"\b(DROP|ALTER|DELETE|UPDATE|CASCADE)\b", sql, re.I)
    assert sql.count("CREATE TABLE") == 14


def test_referenced_scientific_history_cannot_be_deleted(world):
    store, _, _, _, _ = world
    import duckdb

    for statement in (
        "DELETE FROM hypotheses WHERE identifier='AXIS-ERAP1-CURATED-HYP-001'",
        "DELETE FROM decision_explanations WHERE id='explanation:on_target'",
        "DELETE FROM proposed_experiments "
        "WHERE experiment_id='decision:exp:engagement-assay'",
    ):
        with pytest.raises(duckdb.ConstraintException):
            store._connection.execute(statement)


def test_frontend_renders_server_decisions_and_contains_no_scientific_logic():
    text = (REPO / "web/src/decision.ts").read_text()
    assert not re.search(r"ERAP1|HLA-B27|axSpA", text)
    assert not re.search(r"[=!]==?\s*['\"]DECISION-", text)
    assert "decision:exp:" not in text.replace(
        "(explanation|uncertainty|decision:exp)", ""
    )
    assert not re.search(
        r"\b(probabilit|confidence|information.gain|posterior|entropy)\b",
        text.replace("No probabilities are assigned", ""),
        re.I,
    )
    assert "Best experiment" not in text and "best experiment" not in text


def test_api_and_cli_use_the_same_engine(world, tmp_path):
    store, protein, service, state, _ = world
    from typer.testing import CliRunner

    from axis.cli.main import app

    database = str(tmp_path / "consistency.duckdb")
    with EvidenceStore(database) as other:
        init(other)
    result = CliRunner().invoke(
        app, ["--database", database, "decision", "build", PROJECT]
    )
    assert result.exit_code == 0, result.output
    assert state["critical_uncertainty_id"] in result.output
    assert state["recommended_experiment_id"] in result.output
    api = ReadAPI(store).get(f"/api/projects/{PROJECT}/decision-trace", {})
    assert api["sensitivity"] == state["sensitivity"]


# -- coverage of the rule inventory ----------------------------------------------


PHASE35A_RULES = {
    r
    for r in rules.RULES
    if not r.startswith(("DECISION-RESULT", "DECISION-REPRO-002", "DECISION-REVIEW"))
}


def test_zz_every_phase35a_rule_fired_in_at_least_one_scenario_in_this_module():
    assert PHASE35A_RULES <= FIRED, sorted(PHASE35A_RULES - FIRED)


def test_recommendation_is_a_function_of_evidence_rules_and_candidate_design(world):
    _, _, _, state, inputs = world
    outcomes = {state["recommended_experiment_id"]}
    # investigator constraints change feasibility
    constrained = copy.deepcopy(inputs)
    constrained["constraints"] = {
        "id": "c",
        "available_models": [],
        "available_compounds": [],
        "available_assays": [],
        "available_equipment": [],
        "external_collaborations": [],
        "excluded_experiment_ids": ["decision:exp:chemical-genetic-engagement"],
    }
    outcomes.add(
        engine.analyze(constrained, with_sensitivity=False)["recommended_experiment_id"]
    )
    # a different critical uncertainty
    outcomes.add(
        run(
            inputs,
            lambda e: (edge(e, "engagement", "supported", ["x"]), e.update(gap_ids=[])),
        )["recommended_experiment_id"]
    )
    # a different candidate design (flattened outcome mappings) changes the answer
    flat = copy.deepcopy(inputs)
    for candidate in flat["candidates"]:
        if candidate["experiment_id"] == "decision:exp:chemical-genetic-engagement":
            for scenario in candidate["scenarios"]:
                for effect in scenario["effects"].values():
                    effect["effect"] = "does_not_discriminate"
    outcomes.add(
        engine.analyze(flat, with_sensitivity=False)["recommended_experiment_id"]
    )
    # no phenotype: nothing recommended
    outcomes.add(
        run(inputs, lambda e: e.update(compound_phenotype_ids=[]))[
            "recommended_experiment_id"
        ]
    )
    assert len(outcomes) >= 3, outcomes
    assert None in outcomes
    assert "decision:exp:engagement-assay" in outcomes


def test_truncated_evidence_is_refused_not_silently_dropped(fresh, monkeypatch):
    store, protein, service = fresh
    real = store.cellular.collection

    def window(project, protein_id, kind, *args, **kwargs):
        page = real(project, protein_id, kind, *args, **kwargs)
        return {**page, "has_more": True} if kind == "assessments" else page

    monkeypatch.setattr(store.cellular, "collection", window)
    with pytest.raises(ValueError, match="refuses to run on truncated evidence"):
        service.evidence(PROJECT, protein)
