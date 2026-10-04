"""Synthetic calculations and frozen source replay; no live provider required."""

import hashlib
import json
import socket
from dataclasses import replace
from datetime import UTC, datetime
from importlib import resources
from urllib.parse import quote

import duckdb
import httpx
import pytest

from axis.api.server import ReadAPI
from axis.discovery.curation import import_curated_erap1
from axis.domain.pharmacology import (
    Assay,
    BioactivityMeasurement,
    ChemicalForm,
    CompoundExternalIdentifier,
    CompoundIdentity,
    MeasurementCondition,
    SelectivityAssessment,
)
from axis.domain.protein import SourceSnapshot
from axis.pharmacology.chemistry import resolve_structure
from axis.pharmacology.selectivity import compare, normalize
from axis.pharmacology.service import PharmacologyService
from axis.sources.chembl import ChEMBLAdapter, parse_activity, parse_frozen
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ROOT = resources.files("axis").joinpath("resources/pharmacology/erap1/v1")


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    service = PharmacologyService(store)
    return protein, service


@pytest.fixture(scope="module")
def imported():
    with EvidenceStore() as store:
        protein, service = init(store)
        identifiers = service.import_package(PROJECT, protein)
        yield store, protein, service, identifiers


def synthetic(endpoint="IC50", op="=", value=10, unit="nM", identifier="m1"):
    return BioactivityMeasurement(
        identifier,
        "c",
        "a",
        endpoint,
        op,
        str(value),
        unit,
        value,
        "s",
        "record",
        "synthetic only",
        chemical_form_id="synthetic:parent",
    )


def assay(target="ERAP1", **kwargs):
    value = Assay(
        "a",
        "synthetic",
        "biochemical_activity",
        target,
        "s",
        "r",
        "synthetic only",
        taxon_id=9606,
        protein_construct_id="construct:" + target,
        construct_mapping_status="exact",
        assay_format="enzyme",
        biological_system="synthetic recombinant",
        substrate="same",
        detection_method="fluorescence",
        conditions=tuple(
            MeasurementCondition(k, v)
            for k, v in {
                "pH": "7.5",
                "buffer": "synthetic buffer",
                "temperature": "25 °C",
                "substrate concentration": "100 µM",
                "enzyme concentration": "4 nM",
                "incubation time": "10 min",
            }.items()
        ),
    )
    return replace(value, **kwargs)


@pytest.mark.parametrize("op", ["=", "<", "<=", ">", ">=", "~"])
def test_original_operator_unit_conversion(op):
    m = synthetic(op=op, value=2.5, unit="µM")
    n = normalize(m)
    assert n.original_value == "2.5" and n.original_unit == "µM"
    assert n.relation_operator == op and n.normalized_value == 2500
    assert n.normalization_method["factor"] == 1000


@pytest.mark.parametrize("endpoint", ["IC50", "EC50", "AC50", "Ki", "Kd"])
def test_endpoint_separation(endpoint):
    assert normalize(synthetic(endpoint=endpoint)).endpoint == endpoint


@pytest.mark.parametrize(
    "unit,factor", [("nM", 1), ("uM", 1000), ("mM", 1e6), ("M", 1e9)]
)
def test_units(unit, factor):
    assert normalize(synthetic(unit=unit)).normalized_value == 10 * factor


def test_percent_missing_and_invalid():
    m = synthetic(endpoint="percent inhibition", value=30, unit="%")
    assert normalize(m).normalized_value is None
    assert normalize(replace(m, value=-10, original_value="-10")).value == -10
    assert replace(m, value=None, original_value=None).value is None
    for fields in (
        {"relation_operator": "!="},
        {"original_unit": "mg/mL"},
        {"value": -1},
        {"value": float("nan")},
        {"original_value": "11"},
    ):
        with pytest.raises(ValueError):
            replace(synthetic(), **fields)
    with pytest.raises(ValueError):
        replace(m, original_unit="nM")


@pytest.mark.parametrize(
    "op,expected,key",
    [
        ("=", 100, "ratio"),
        (">", 1000, "ratio_lower_bound"),
        (">=", 1000, "ratio_lower_bound"),
        ("<", 1000, "ratio_upper_bound"),
        ("<=", 1000, "ratio_upper_bound"),
    ],
)
def test_exact_and_censored_comparison(op, expected, key):
    p = synthetic()
    q = synthetic(op=op, value=1000 if op == "=" else 10000, identifier="m2")
    result = compare(p, q, assay(), assay("ERAP2"))
    assert result["comparability_status"] == "Comparable"
    assert result[key] == expected
    assert result["transformation"]["numerator"] == "m2"
    if op != "=":
        assert result["ratio"] is None
        assert result["lower_inclusive" if ">" in op else "upper_inclusive"] == (
            "=" in op
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"substrate": "different"},
        {"assay_type": "cellular_phenotype"},
        {"taxon_id": 10090},
        {"conditions": ()},
        {"construct_mapping_status": "unknown", "protein_construct_id": None},
        {"source_snapshot_id": "other"},
    ],
)
def test_contexts_reject_ratios(changes):
    result = compare(
        synthetic(), synthetic(identifier="m2"), assay(), assay("ERAP2", **changes)
    )
    assert result["comparability_status"] == "Not directly comparable"
    assert result["ratio"] is None


def test_missing_endpoint_and_censor_ambiguity():
    assert (
        compare(synthetic(), None, assay(), None)["comparability_status"]
        == "Not assessed"
    )
    for m in (synthetic(endpoint="Ki"), synthetic(op="~"), synthetic(op=">")):
        p = synthetic(op=">" if m.relation_operator == ">" else "=")
        assert compare(p, m, assay(), assay("ERAP2"))["ratio"] is None
    assert (
        compare(synthetic(), synthetic(endpoint="Ki"), assay(), assay("ERAP2"))[
            "comparability_status"
        ]
        == "Not directly comparable"
    )


def test_rdkit_stereo_salt_unresolved_and_checksum():
    explicit = resolve_structure("N[C@@H](C)C(=O)O")
    unknown = resolve_structure("NC(C)C(=O)O")
    assert "@" in explicit["isomeric_smiles"]
    assert "@" not in unknown["isomeric_smiles"]
    salt = resolve_structure("[Na+].CC(=O)[O-]")
    parent = resolve_structure("CC(=O)O")
    assert salt["inchi_key"] != parent["inchi_key"]
    assert "." in salt["isomeric_smiles"]
    assert explicit == resolve_structure("N[C@@H](C)C(=O)O")
    assert "<svg" in explicit["depiction_svg"]
    assert not explicit["transformation"]["parameters"]["salt_stripping"]
    with pytest.raises(ValueError):
        resolve_structure("invalid")
    unresolved = CompoundIdentity("unknown", "Compound X", "s")
    assert unresolved.depiction_svg is None
    for form in ("salt", "parent", "racemate", "unspecified"):
        assert ChemicalForm("f", "c", form, "s", "synthetic").form_type == form


def test_frozen_vertical_source_errors_not_promoted(imported):
    store, protein, service, ids = imported
    repo = store.pharmacology
    assert len(ids) == 3
    assert (
        service.detail(PROJECT, protein, "compounds", ids[0])["compound"][
            "stereochemistry_status"
        ]
        == "unknown"
    )
    c = service.detail(PROJECT, protein, "compounds", ids[1])
    assert c["compound"]["molecular_formula"] == "C21H30N4O3"
    assert any(
        i["external_id"] == "CHEMBL4456470" and i["mapping_status"] == "rejected"
        for i in c["identifiers"]
    )
    measurements = repo.collection(PROJECT, protein, "measurements", 100, 0)["items"]
    assert len(measurements) == 15
    assert {m["relation_operator"] for m in measurements} == {"=", ">"}
    assert len(repo.collection(PROJECT, protein, "assays", 100, 0)["items"]) == 7
    lnpep = repo.collection(PROJECT, protein, "assays", 100, 0, {"target": "LNPEP"})[
        "items"
    ][0]
    assert lnpep["reported_accession"] == "Q8C129" and lnpep["taxon_id"] == 10090
    assert all(
        a["protein_construct_id"] is None and a["protein_identity_id"] is None
        for a in repo.collection(PROJECT, protein, "assays", 100, 0)["items"]
    )
    comparisons = repo.collection(PROJECT, protein, "selectivity", 100, 0)["items"]
    assert {s["comparability_status"] for s in comparisons} == {
        "Not assessed",
        "Not directly comparable",
    }
    assert all(s["ratio"] is None for s in comparisons)
    assert store.structures.list_ids(PROJECT, protein) == []
    assert store.statistics().claims == 14


def test_repository_immutability_identifiers_and_wrong_target(imported):
    store, protein, service, ids = imported
    row = store.pharmacology.record("compounds", ids[0])
    c = CompoundIdentity(**row)
    with pytest.raises(RecordConflictError):
        store.pharmacology.insert_compound(replace(c, preferred_name="changed"))
    with pytest.raises(RecordConflictError):
        store.pharmacology.insert_identifier(
            CompoundExternalIdentifier(
                "clash",
                ids[1],
                "ChEMBL",
                "CHEMBL1700161",
                "chembl:maben-37",
                "resolved",
            )
        )
    with pytest.raises(ValueError):
        store.pharmacology.insert_assay(
            replace(
                assay("ERAP2"), protein_identity_id=protein, reported_accession="Q9NZ08"
            )
        )
    with pytest.raises(ValueError):
        Assay("x", "x", "made-up", "ERAP1", "s", "r", "source")


def test_api_bounded_filters_provenance_scope(imported):
    store, protein, _, ids = imported
    api = ReadAPI(store)
    base = f"/api/projects/{PROJECT}/targets/{quote(protein, safe='')}"
    assert api.get(base + "/compounds", {"limit": ["2"]})["has_more"]
    assert (
        api.get(base + "/compounds/" + quote(ids[0], safe=""), {})["snapshot"][
            "provider"
        ]
        == "primary-publication"
    )
    page = api.get(base + "/measurements", {"target": ["ERAP2"], "endpoint": ["IC50"]})
    assert page["total"] == 2
    m = page["items"][0]
    detail = api.get(
        base + "/measurements/" + quote(m["id"], safe="") + "/provenance", {}
    )
    assert detail["record"]["relation_operator"] == ">"
    assert detail["assay"]["substrate"] == "R-AMC"
    for kind in ("compounds", "assays", "measurements", "selectivity"):
        assert api.get(base + "/" + kind, {})["total"] > 0
        with pytest.raises(RecordNotFoundError):
            api.get(base + "/" + kind + "/unknown", {})
        with pytest.raises(RecordNotFoundError):
            api.get(base.replace(PROJECT, "AXIS-DD-ERAP1-001") + "/" + kind, {})
    with pytest.raises(ValueError):
        api.get(base + "/measurements", {"endpoint": ["IC50", "Ki"]})
    with pytest.raises(ValueError):
        api.get(base + "/measurements", {"limit": ["101"]})


def test_source_adapter_lossless_without_live_access():
    parsed = parse_frozen(ROOT.joinpath("chembl-extract.json").read_bytes())
    m = next(a for a in parsed["activities"] if a["activity_id"] == 19151094)
    assert parse_activity(m)["relation"] == "<="
    with pytest.raises(ValueError):
        ChEMBLAdapter().retrieve_record("molecule", "../unsafe")


def test_two_independent_stores_network_blocked_replay(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network prohibited")

    monkeypatch.setattr(httpx, "get", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    outputs = []
    for _ in range(2):
        with EvidenceStore() as store:
            protein, service = init(store)
            claims_before = store.statistics().claims
            ids = service.import_package(PROJECT, protein)
            service.import_package(PROJECT, protein)
            assert store.statistics().claims == claims_before
            output = {
                kind: store.pharmacology.collection(PROJECT, protein, kind, 100, 0)
                for kind in ("compounds", "assays", "measurements", "selectivity")
            }
            output["details"] = [
                service.detail(PROJECT, protein, "compounds", i) for i in ids
            ]
            outputs.append(output)
    assert outputs[0] == outputs[1]


def test_checksum_conflict_rolls_back(tmp_path):
    for item in ROOT.iterdir():
        if item.is_file():
            (tmp_path / item.name).write_bytes(item.read_bytes())
    compounds = json.loads((tmp_path / "compounds.json").read_text())
    compounds[1]["expected_formula"] = "WRONG"
    encoded = json.dumps(compounds).encode()
    (tmp_path / "compounds.json").write_bytes(encoded)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["files"]["compounds.json"] = hashlib.sha256(encoded).hexdigest()
    manifest_raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(manifest_raw)
    (tmp_path / "manifest.sha256").write_text(hashlib.sha256(manifest_raw).hexdigest())
    with EvidenceStore() as store:
        protein, service = init(store)
        with pytest.raises(ValueError, match="formula conflict"):
            service.import_package(PROJECT, protein, tmp_path)
        assert (
            store.pharmacology.collection(PROJECT, protein, "compounds", 100, 0)[
                "total"
            ]
            == 0
        )
        assert (
            store._connection.execute(
                "SELECT count(*) FROM source_snapshots "
                "WHERE provider='primary-publication'"
            ).fetchone()[0]
            == 0
        )


def test_migration_6_to_7_preserves_legacy(tmp_path):
    path = tmp_path / "legacy6.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,"
            "name VARCHAR,applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        for item in sorted(
            resources.files("axis.storage.migrations").iterdir(), key=lambda i: i.name
        ):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 6:
                conn.execute(item.read_text())
                conn.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with pytest.raises(ValueError, match="migration"):
        EvidenceStore(path, read_only=True)
    with EvidenceStore(path) as store:
        assert store.statistics().schema_version == 9
        protein, service = init(store)
        service.import_package(PROJECT, protein)
    with EvidenceStore(path, read_only=True) as store:
        assert (
            store.pharmacology.collection(PROJECT, protein, "compounds", 100, 0)[
                "total"
            ]
            == 3
        )


def test_duplicates_conflicts_and_unlinked_measurement_scope(imported):
    store, protein, service, _ = imported
    original = store.pharmacology.record("measurements", "measurement:maben:1")
    with pytest.raises(RuntimeError, match="fixture rollback"), store._transaction():
        m = replace(
            BioactivityMeasurement(**original),
            id="test:disagreement",
            original_value="500",
            value=500,
            normalized_value=None,
            normalized_unit=None,
            normalization_method={},
        )
        store.pharmacology.insert_measurement(normalize(m))
        with pytest.raises(RecordNotFoundError):
            service.detail(PROJECT, protein, "measurements", m.id)
        store.pharmacology.link_measurement(PROJECT, protein, m.id)
        detail = service.detail(PROJECT, protein, "measurements", m.id)
        assert detail["potential_disagreements"]["items"][0]["id"] == original["id"]
        duplicate = replace(m, id="test:independent-duplicate")
        store.pharmacology.insert_measurement(normalize(duplicate))
        store.pharmacology.link_measurement(PROJECT, protein, duplicate.id)
        assert (
            store.pharmacology.collection(PROJECT, protein, "measurements", 100, 0)[
                "total"
            ]
            == 17
        )
        raise RuntimeError("fixture rollback")


def test_explicit_construct_binding_cellular_context_and_graph(imported):
    """Synthetic fixture linkage, NOT a claim that Maben used 3QNF material."""
    store, protein, service, ids = imported
    graph = service.detail(PROJECT, protein, "compounds", ids[1])["identity_graph"]
    assert "compares" in {e["relation"] for e in graph["edges"]}
    assert not any("treat" in e["relation"] for e in graph["edges"])
    with pytest.raises(RuntimeError, match="fixture rollback"), store._transaction():
        sid = "snapshot:synthetic-assay"
        store.targets.insert_snapshot(
            SourceSnapshot(
                sid,
                "synthetic",
                "unit-test",
                datetime(2026, 10, 4, tzinfo=UTC),
                "https://example.org/synthetic-not-real-experiment",
                hashlib.sha256(b"synthetic").hexdigest(),
                "application/json",
                "test-1",
            )
        )
        structure = StructureIdentityService(store).import_package(PROJECT, protein)
        construct = store.structures.constructs(structure)[0]["id"]
        a = replace(
            assay(),
            id="test:binding",
            assay_type="binding",
            protein_identity_id=protein,
            reported_accession="Q9NZ08",
            protein_construct_id=construct,
            source_snapshot_id=sid,
        )
        store.pharmacology.insert_assay(a)
        assert (
            store.pharmacology.record("assays", a.id)["protein_construct_id"]
            == construct
        )
        with pytest.raises(ValueError, match="construct"):
            store.pharmacology.insert_assay(
                replace(a, id="test:wrong", protein_construct_id="missing")
            )
        cell = replace(
            a,
            id="test:cell",
            assay_type="cellular_phenotype",
            protein_identity_id=None,
            protein_construct_id=None,
            construct_mapping_status="unknown",
            cell_line="synthetic",
            conditions=(),
        )
        store.pharmacology.insert_assay(cell)
        assert store.pharmacology.record("assays", cell.id)["conditions"] == []
        raise RuntimeError("fixture rollback")


def test_numeric_overflow_and_fabricated_ratio_rejected(imported):
    with pytest.raises(ValueError, match="overflow"):
        normalize(synthetic(value=1e308, unit="M"))
    store, _, _, _ = imported
    row = store.pharmacology.record(
        "selectivity", "selectivity:measurement:maben:3:measurement:maben:4"
    )
    value = SelectivityAssessment(**row)
    with pytest.raises(ValueError, match="cannot produce"):
        replace(value, ratio=29)
    with pytest.raises(ValueError, match="computed"):
        store.pharmacology.insert_assessment(
            replace(
                value,
                comparability_status="Comparable",
                ratio=29,
                transformation={"invented": True},
            )
        )
