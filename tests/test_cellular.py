"""Frozen source replay and synthetic scientific boundary tests."""

import hashlib
import json
import socket
from dataclasses import asdict, replace
from importlib import resources

import duckdb
import httpx
import pytest

from axis.api.server import ReadAPI
from axis.cellular.rules import aggregate, concordance
from axis.cellular.service import CellularPharmacologyService, experiment
from axis.discovery.curation import import_curated_erap1
from axis.domain.cellular import (
    BiologicalContext,
    CellularAssessment,
    CellularExperiment,
    ExperimentalReadout,
    ImmunopeptidomeObservation,
)
from axis.domain.models import ClaimContext
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ROOT = resources.files("axis").joinpath("resources/cellular/erap1-axspa/v1")


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    PharmacologyService(store).import_package(PROJECT, protein)
    service = CellularPharmacologyService(store)
    service.import_package(PROJECT, protein)
    return protein, service


@pytest.fixture(scope="module")
def imported():
    with EvidenceStore() as store:
        protein, service = init(store)
        yield store, protein, service


@pytest.mark.parametrize(
    "states,expected",
    [
        ([], "not_assessed"),
        (["supported"], "supported"),
        (["supported", "contradicted"], "mixed"),
        (["mixed"], "mixed"),
        (["contradicted", "not_assessed"], "contradicted"),
        (["insufficient", "not_assessed"], "insufficient"),
        (["not_applicable"], "not_applicable"),
    ],
)
def test_categorical_chain_aggregation(states, expected):
    assert aggregate(states) == expected


@pytest.mark.parametrize(
    "edge,state,directness,valid",
    [
        ("engagement", "supported", "downstream_phenotype", False),
        ("engagement", "supported", "direct_cellular_interaction", True),
        ("functional", "supported", "functional", True),
        ("hla", "supported", "downstream_phenotype", True),
        ("engagement", "not_assessed", "not_assessed", True),
        ("engagement", "contradicted", "direct_cellular_interaction", True),
    ],
)
def test_direct_engagement_not_inferred(edge, state, directness, valid):
    kwargs = dict(
        id="a",
        experiment_id="e",
        edge=edge,
        state=state,
        rationale="synthetic",
        supporting_readout_ids=("r",),
        directness=directness,
    )
    if valid:
        assert CellularAssessment(**kwargs).state == state
    else:
        with pytest.raises(ValueError):
            CellularAssessment(**kwargs)


@pytest.mark.parametrize(
    "hla,expression,disease,genotype",
    [
        ("HLA-B*27:05", "engineered", "cell line", "K528R"),
        ("HLA-B27 negative", "endogenous", "ankylosing spondylitis", None),
        (None, None, None, None),
        ("HLA-B*40:01", "endogenous", "healthy control", "rs30187 heterozygous"),
    ],
)
def test_context_never_infers_allotype(hla, expression, disease, genotype):
    c = BiologicalContext(
        ClaimContext(genotype=genotype),
        hla_allele=hla,
        hla_expression=expression,
        disease_status=disease,
    )
    assert asdict(c)["erap1_allotype"] is None
    assert c.hla_allele == hla


def synthetic():
    context = BiologicalContext(
        ClaimContext(
            species="human",
            genotype="WT",
            allotype="source-known",
            assay="matched",
            experimental_system="synthetic",
        ),
        cell_line="synthetic",
        hla_allele="HLA-B*27:05",
        hla_expression="engineered",
        disease_status="cell line",
    )
    e = CellularExperiment(
        "e",
        "synthetic",
        "p",
        context,
        "s",
        "loc",
        ("ctrl",),
        modality="knockdown",
        duration="24h",
    )
    r = ExperimentalReadout(
        "r",
        "e",
        "surface FHC",
        "decrease",
        "decrease",
        "HLA_molecular",
        "loc",
        claim_id="claim",
    )
    return e, r


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("decrease", "concordant"),
        ("increase", "discordant"),
    ],
)
def test_synthetic_comparable_concordance(direction, expected):
    e, r = synthetic()
    f = replace(e, id="f", modality="small_molecule")
    assert (
        concordance(
            e, f, r, replace(r, id="rr", experiment_id="f", direction=direction)
        )["state"]
        == expected
    )


def test_unknown_or_different_hla_not_contradiction():
    e, r = synthetic()
    f = replace(
        e,
        id="f",
        modality="small_molecule",
        context=replace(e.context, hla_allele="HLA-B*40:01"),
    )
    assert (
        concordance(e, f, r, replace(r, direction="increase"))["state"]
        == "not_comparable"
    )


def test_imported_boundaries_and_scopes(imported):
    store, protein, service = imported
    assert store.statistics().schema_version == 12
    assert store.cellular.collection(PROJECT, protein, "experiments")["total"] == 11
    assert (
        store.cellular.collection(PROJECT, protein, "assessments", 100)["total"] == 37
    )
    for compound in ("compound:maben-2", "compound:maben-3"):
        chain = {
            e["edge"]: e for e in service.chain(PROJECT, protein, compound)["edges"]
        }
        assert chain["biochemical"]["state"] == "supported"
        assert chain["engagement"]["state"] == "not_assessed"
        assert chain["functional"]["state"] == "insufficient"
        assert chain["disease"]["state"] == "not_assessed"
        assert chain["clinical"]["state"] == "not_assessed"
        assert all(
            a["disease_relevance"] == "mechanistic_model"
            for a in chain["hla"]["assessments"]
        )
    assert not store.cellular.collection(
        PROJECT, protein, "experiments", compound="compound:maben-1"
    )["items"]
    assert all(
        e["state"] == "not_assessed"
        for e in service.chain(PROJECT, protein, "compound:maben-1")["edges"]
        if e["edge"] != "biochemical"
    )
    packet = service.review_packet(PROJECT, protein)
    assert packet["automatic_acceptance"] is False
    assert all(
        v == "pending" for r in packet["items"] for v in r["review_decisions"].values()
    )
    assert len(service.gaps(PROJECT, protein)["items"]) == 4
    assert len(service.gaps(PROJECT, protein, "compound:maben-2")["items"]) == 1
    assert all(
        c["state"] == "not_comparable"
        for c in service.comparisons(PROJECT, protein)["items"]
    )
    with pytest.raises(RecordNotFoundError):
        store.cellular.detail(PROJECT, protein, "experiments", "missing")
    with pytest.raises(RecordNotFoundError):
        store.cellular.collection("wrong-project", protein, "experiments")
    with pytest.raises(ValueError):
        store.cellular.collection(PROJECT, protein, "experiments", 101)


def test_aggregate_immunopeptidome_and_source(imported):
    store, protein, _ = imported
    value = store.cellular.collection(PROJECT, protein, "immunopeptidome")["items"][0]
    assert "11–13" in value["aggregate_observation"]
    assert value["hla_allele"] is None
    assert not value["raw_peptide_data_imported"]
    with pytest.raises(ValueError):
        ImmunopeptidomeObservation(**(value | {"raw_peptide_data_imported": True}))


def test_offline_twostore_replay_and_immutable_history(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("network disabled")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(httpx.Client, "request", deny)
    results = []
    for _ in range(2):
        with EvidenceStore() as store:
            import_curated_erap1(store)
            historical = store._connection.execute(
                "SELECT * FROM claims ORDER BY identifier"
            ).fetchall()
            protein = TargetIdentityService(store).import_package(PROJECT)
            PharmacologyService(store).import_package(PROJECT, protein)
            measurements = store.pharmacology.collection(
                PROJECT, protein, "measurements", 100, 0
            )
            service = CellularPharmacologyService(store)
            a = service.import_package(PROJECT, protein)
            assert a == service.import_package(PROJECT, protein)
            assert (
                historical
                == store._connection.execute(
                    "SELECT * FROM claims ORDER BY identifier"
                ).fetchall()
            )
            assert measurements == store.pharmacology.collection(
                PROJECT, protein, "measurements", 100, 0
            )
            results.append(
                [
                    store.cellular.collection(PROJECT, protein, k, 100)
                    for k in (
                        "experiments",
                        "readouts",
                        "assessments",
                        "immunopeptidome",
                    )
                ]
                + [service.chain(PROJECT, protein), service.gaps(PROJECT, protein)]
            )
    assert results[0] == results[1]


def test_conflict_rollback(imported):
    store, protein, _ = imported
    data = store.cellular.collection(PROJECT, protein, "experiments")["items"][0]
    with pytest.raises(RecordConflictError), store._transaction():
        store.cellular.add_experiment(
            PROJECT, protein, replace(experiment(data), label="changed")
        )
    assert store.cellular.detail(PROJECT, protein, "experiments", data["id"]) == data


@pytest.mark.parametrize(
    "route",
    [
        "experiments",
        "readouts",
        "assessments",
        "immunopeptidome",
        "evidence-chain",
        "engagement",
        "gaps",
        "concordance",
        "review-packet",
        "decision",
    ],
)
def test_api(imported, route):
    store, protein, _ = imported
    root = f"/api/projects/{PROJECT}/targets/{protein}/cellular"
    assert ReadAPI(store).get(root + "/" + route, {})
    assert ReadAPI(store).get(root, {})["edges"]
    with pytest.raises(ValueError):
        ReadAPI(store).get(root, {"endpoint": ["IC50"]})


def test_package_checksum():
    assert hashlib.sha256(ROOT.joinpath("manifest.json").read_bytes()).hexdigest() == (
        ROOT.joinpath("manifest.sha256").read_text().strip()
    )
    package = json.loads(ROOT.joinpath("manifest.json").read_text())
    assert not any(
        e["compound_id"]
        for e in package["experiments"]
        if e["reported_perturbagen"] == "DG013A"
    )


def test_migration_7_to_8(tmp_path):
    path = tmp_path / "legacy7.duckdb"
    migrations = resources.files("axis.storage.migrations")
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY, name VARCHAR NOT NULL)"
        )
        for item in sorted(migrations.iterdir(), key=lambda x: x.name):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 7:
                connection.execute(item.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with pytest.raises(ValueError, match="migration"):
        EvidenceStore(path, read_only=True)
    with EvidenceStore(path) as store:
        assert store.statistics().schema_version == 12
        protein, service = init(store)
        expected = service.chain(PROJECT, protein)
    with EvidenceStore(path, read_only=True) as store:
        assert CellularPharmacologyService(store).chain(PROJECT, protein) == expected
