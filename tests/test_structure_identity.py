import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from importlib import resources
from urllib.parse import quote

import duckdb
import gemmi
import httpx
import pytest

from axis.api.server import ReadAPI
from axis.discovery.curation import import_curated_erap1
from axis.discovery.service import DiscoveryService
from axis.domain.structure import ResidueStatus
from axis.sources.pdb import PDBAdapter, parse_mmcif, validate_pdb_id
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.structures.mapping import coverage, map_residues, mapping_checksum
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ROOT = resources.files("axis").joinpath("resources/structures/erap1/3qnf/v1")
NOW = datetime(2026, 10, 4, tzinfo=UTC)


def init(store):
    import_curated_erap1(store)
    protein = TargetIdentityService(store).import_package(PROJECT)
    return protein, StructureIdentityService(store)


def test_frozen_source_parser_chain_components_and_revision():
    parsed = parse_mmcif(ROOT.joinpath("structure.cif").read_bytes(), "3QNF")
    assert parsed.metadata["experimental_method"] == "X-RAY DIFFRACTION"
    assert parsed.metadata["resolution"] == 3.0
    assert parsed.metadata["revision"] == "2.2"
    assert [c["label_asym_id"] for c in parsed.chains] == ["A", "B", "C"]
    assert [len(c["coordinates"]) for c in parsed.chains] == [696, 802, 800]
    assert all(c["accession"] == "Q9NZ08" and c["taxon"] == 9606 for c in parsed.chains)
    assert len(parsed.components) == 50
    assert sum(c["observation_kind"] == "water" for c in parsed.components) == 39
    assert sum(c["observation_kind"] == "ion" for c in parsed.components) == 3


def test_domain_construct_chain_and_structure_validation():
    with EvidenceStore(":memory:") as store:
        protein, service = init(store)
        identifier = service.import_package(PROJECT, protein)
        result = service.projection(PROJECT, protein, identifier)
        from axis.domain.structure import (
            ChainInstance,
            ExperimentalStructure,
            ProteinConstruct,
        )

        construct = ProteinConstruct(**result["constructs"][0])
        with pytest.raises(ValueError):
            replace(construct, start_residue=0)
        with pytest.raises(ValueError):
            replace(construct, construct_sequence_checksum="0" * 64)
        chain_data = {k: v for k, v in result["chains"][0].items() if k != "coverage"}
        chain = ChainInstance(**chain_data)
        with pytest.raises(ValueError):
            replace(chain, auth_asym_id="")
        with pytest.raises(ValueError):
            replace(chain, sequence_checksum="0" * 64)
        structure = ExperimentalStructure(**result["structure"])
        with pytest.raises(ValueError):
            replace(structure, resolution=-1)
        with pytest.raises(ValueError):
            replace(structure, structure_origin="disease")
        graph = result["identity_graph"]
        assert len(graph["nodes"]) == 7
        assert {edge["relation"] for edge in graph["edges"]} == {
            "represented_by",
            "observed_in",
            "contains",
            "maps_to",
            "sourced_from",
        }


@pytest.mark.parametrize("value", ["../3QNF", "3qnf", "0ABC", "Q9NZ08"])
def test_invalid_pdb_identifier(value):
    with pytest.raises(ValueError):
        validate_pdb_id(value)


@pytest.mark.parametrize("raw", [b"data_bad\n_x 1", b"not mmcif", b"\xff"])
def test_malformed_source(raw):
    with pytest.raises(ValueError):
        parse_mmcif(raw, "3QNF")


def test_optional_source_metadata_unknown():
    block = gemmi.cif.read_string(
        ROOT.joinpath("structure.cif").read_text()
    ).sole_block()
    block.set_pair("_refine.ls_d_res_high", "?")
    block.set_pair("_struct.title", "?")
    parsed = parse_mmcif(block.as_string().encode(), "3QNF")
    assert parsed.metadata["resolution"] is None
    assert parsed.metadata["title"] == "Not reported"


def test_coordinate_residue_disagreement_fails_safely():
    raw = ROOT.joinpath("structure.cif").read_text()
    block = gemmi.cif.read_string(raw).sole_block()
    column = block.find_loop("_atom_site.label_comp_id")
    column[0] = "XXX"
    with pytest.raises(ValueError, match="atom residue"):
        parse_mmcif(block.as_string().encode(), "3QNF")


def test_provider_failure_and_invalid_id_no_request():
    def failure(request):
        return httpx.Response(404, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(failure)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        PDBAdapter(client).retrieve("3QNF")

    def no_network(request):
        raise AssertionError("unexpected network")

    with (
        httpx.Client(transport=httpx.MockTransport(no_network)) as client,
        pytest.raises(ValueError),
    ):
        PDBAdapter(client).retrieve("invalid")


def test_source_numbering_offset_insertion_code_unresolved_and_truncations():
    canonical = "ACDEFGHIKLMNPQRSTVWY"
    chain = canonical[2:-2]
    rows = map_residues(
        canonical,
        chain,
        "C",
        [(1, 16, 3, 18)],
        {i: (str(i + 100), "A" if i == 5 else None) for i in range(1, 17)},
        set(range(1, 17)) - {7},
    )
    assert rows[0].canonical_position == 3
    assert rows[0].author_residue_number == "101"
    assert rows[4].insertion_code == "A"
    assert rows[6].status == ResidueStatus.UNRESOLVED
    assert sum(r.status == ResidueStatus.OUTSIDE for r in rows) == 4
    assert coverage(rows, 20)["canonical_with_coordinates"] == 15
    with pytest.raises(ValueError):
        replace(rows[0], canonical_position=0)
    with pytest.raises(ValueError):
        replace(rows[0], author_residue_number=None)
    assert mapping_checksum(rows) == mapping_checksum(rows)


def test_substitution_not_automatically_engineered_or_disease_variant():
    canonical = "ACDEFGHIKLMNPQRSTVWY"
    chain = "G" + canonical[1:]
    args = (
        canonical,
        chain,
        "C",
        [(1, 20, 1, 20)],
        {i: (str(i), None) for i in range(1, 21)},
        set(range(1, 21)),
    )
    assert map_residues(*args)[0].status == ResidueStatus.MISMATCH
    assert (
        map_residues(*args, {1: "source variant"})[0].status
        == ResidueStatus.SUBSTITUTION
    )
    assert (
        map_residues(*args, {1: "engineered mutation"})[0].status
        == ResidueStatus.ENGINEERED
    )


def test_multiple_segments_preserve_internal_insertions_and_deletions():
    rows = map_residues(
        "ACDEFGHIKL",
        "ACDYFGHIKL",
        "C",
        [(1, 3, 1, 3), (5, 10, 5, 10)],
        {i: (str(i), None) for i in range(1, 11)},
        set(range(1, 11)),
    )
    assert rows[3].status == ResidueStatus.INSERTION
    assert rows[-1].canonical_position == 4
    assert rows[-1].status == ResidueStatus.DELETION


@pytest.mark.parametrize("segments", [[], [(1, 4, 1, 3)], [(1, 4, 1, 4), (1, 4, 1, 4)]])
def test_ambiguous_or_unsupported_mapping_rejected(segments):
    with pytest.raises(ValueError):
        map_residues("AAAA", "AAAA", "C", segments, {}, set())


def test_wrong_sequence_mapping_rejected():
    with pytest.raises(ValueError):
        map_residues("AAAA", "WWWW", "C", [(1, 4, 1, 4)], {}, set())


def test_offline_replay_duplicate_identity_and_no_claims(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("offline source replay attempted network")

    monkeypatch.setattr(httpx.Client, "get", no_network)
    outputs = []
    for _ in range(2):
        with EvidenceStore() as store:
            protein, service = init(store)
            identifier = service.import_package(PROJECT, protein)
            assert service.import_package(PROJECT, protein) == identifier
            data = service.projection(PROJECT, protein, identifier)
            mapping = service.mapping(PROJECT, protein, identifier)
            assert [
                g["transformation"]["mapping_sha256"] for g in mapping["chains"]
            ] == [
                "9038e56a15bb463abbc032d1a73fe87abec87d12672123de3712f02716ea9ef3",
                "ae0761a2ab94c3116f31866ed801196e76916da82010051992f23ba8e1dee1fb",
                "1ce473b3e1962983c880f2ac02ac52c363633ebd5a6b5b60d689115c20c2c7de",
            ]
            outputs.append((data, mapping))
            assert store.statistics().claims == 14
            assert [c["coverage"]["unresolved_mapped"] for c in data["chains"]] == [
                245,
                139,
                141,
            ]
            assert data["constructs"][0]["start_residue"] == 1
            assert data["constructs"][0]["end_residue"] == 941
            assert len(data["constructs"][0]["tags"]) == 13
            assert len(data["constructs"][0]["construct_sequence"]) == 954
            assert not data["constructs"][0]["substitutions"]
            assert (
                store.structures.coordinates(identifier)
                == ROOT.joinpath("structure.cif").read_bytes()
            )
    assert outputs[0] == outputs[1]


def test_wrong_taxon_and_cross_reference_fail_before_writes():
    for tag, value in [
        ("_entity_src_gen.pdbx_gene_src_ncbi_taxonomy_id", "10090"),
        ("_struct_ref.pdbx_db_accession", "WRONG"),
    ]:
        block = gemmi.cif.read_string(
            ROOT.joinpath("structure.cif").read_text()
        ).sole_block()
        block.find_values(tag)[0] = value
        with EvidenceStore() as store:
            protein, service = init(store)
            with pytest.raises(ValueError):
                service.ingest(
                    PROJECT, protein, block.as_string().encode(), "3QNF", NOW, None
                )
            assert store.structures.list_ids(PROJECT, protein) == []


def test_atomic_rollback_immutability_and_package_checksum(monkeypatch, tmp_path):
    with EvidenceStore() as store:
        protein, service = init(store)
        original = store.structures.insert_mapping

        def fail(*args, **kwargs):
            raise ValueError("mapping failure")

        monkeypatch.setattr(store.structures, "insert_mapping", fail)
        with pytest.raises(ValueError):
            service.import_package(PROJECT, protein)
        assert (
            store._connection.execute(
                "SELECT count(*) FROM experimental_structures"
            ).fetchone()[0]
            == 0
        )
        monkeypatch.setattr(store.structures, "insert_mapping", original)
        identifier = service.import_package(PROJECT, protein)
        snapshot = store.targets.snapshot(
            store.structures.structure(identifier)["source_snapshot_id"]
        )
        with pytest.raises(RecordConflictError):
            store.targets.insert_snapshot(replace(snapshot, metadata_json="{}"))
        from axis.domain.structure import ExperimentalStructure

        structure = ExperimentalStructure(**store.structures.structure(identifier))
        with pytest.raises(ValueError):
            store.structures.insert_structure(structure, b"wrong bytes")
        with pytest.raises(RecordConflictError):
            store.structures.insert_structure(
                replace(structure, title="changed"),
                store.structures.coordinates(identifier),
            )
        for name in ("manifest.json", "manifest.sha256", "structure.cif"):
            (tmp_path / name).write_bytes(ROOT.joinpath(name).read_bytes())
        (tmp_path / "structure.cif").write_bytes(b"tampered")
        with pytest.raises(ValueError, match="checksum"):
            service.import_package(PROJECT, protein, tmp_path)


def test_structure_read_api_target_and_project_isolation():
    with EvidenceStore() as store:
        protein, service = init(store)
        DiscoveryService(store).create_erap1_demo()
        identifier = service.import_package(PROJECT, protein)
        api = ReadAPI(store)
        base = f"/api/projects/{PROJECT}/targets/{quote(protein, safe='')}/structures"
        assert api.get(base, {})["total"] == 1
        detail = f"{base}/{quote(identifier, safe='')}"
        assert api.get(detail, {})["structure"]["provider_structure_id"] == "3QNF"
        assert len(api.get(detail + "/chains", {})["chains"]) == 3
        assert len(api.get(detail + "/mapping", {})["chains"]) == 3
        assert (
            api.get(detail + "/provenance", {})["snapshot"]["provider"] == "wwPDB/RCSB"
        )
        coords = api.get(detail + "/coordinates", {})
        assert (
            hashlib.sha256(coords["content"].encode()).hexdigest()
            == coords["raw_sha256"]
        )
        for path in (
            detail.replace(PROJECT, "AXIS-DD-ERAP1-001"),
            base + "/unknown",
            base.replace(quote(protein, safe=""), "unknown"),
        ):
            with pytest.raises(RecordNotFoundError):
                api.get(path, {})


def test_migration_5_to_6_upgrade_and_readonly_reopen(tmp_path):
    path = tmp_path / "schema5.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        root = resources.files("axis.storage.migrations")
        for item in sorted(root.iterdir(), key=lambda item: item.name):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 5:
                connection.execute(item.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with EvidenceStore(path) as store:
        protein, service = init(store)
        identifier = service.import_package(PROJECT, protein)
        assert store.statistics().schema_version == 8
    with EvidenceStore(path, read_only=True) as store:
        assert len(store.structures.chains(identifier)) == 3
        assert store.statistics().schema_version == 8
