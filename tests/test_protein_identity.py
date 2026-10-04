import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from importlib import resources
from urllib.parse import quote

import duckdb
import httpx
import pytest

from axis.api.server import ReadAPI
from axis.discovery.curation import import_curated_erap1
from axis.discovery.service import DiscoveryService
from axis.domain.protein import MappingStatus, normalize_sequence, sequence_checksum
from axis.sources.uniprot import UniProtAdapter, parse_record, validate_accession
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
DEMO = "AXIS-DD-ERAP1-001"
ROOT = resources.files("axis").joinpath("resources/targets/erap1/uniprot/v1")
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def parsed():
    return parse_record(
        ROOT.joinpath("record.json").read_bytes(), "Q9NZ08", NOW, expected_taxon=9606
    )


@pytest.mark.parametrize("value", [">header\nABC", "AA-CC", "AA*", "", "A123"])
def test_sequence_rejects_unexpected(value):
    with pytest.raises(ValueError):
        normalize_sequence(value)


def test_sequence_integrity_and_domain_validation():
    assert normalize_sequence(" acd\nBXZJUO ") == "ACDBXZJUO"
    assert sequence_checksum(" acd ") == hashlib.sha256(b"ACD").hexdigest()
    p = parsed()
    with pytest.raises(ValueError):
        replace(p.protein, sequence_length=1)
    with pytest.raises(ValueError):
        replace(p.protein, sequence_checksum="bad")
    with pytest.raises(ValueError):
        replace(p.protein, taxon_id=0)
    with pytest.raises(ValueError):
        replace(p.isoforms[0], sequence_checksum="bad")
    with pytest.raises(ValueError):
        replace(p.isoforms[1], sequence_length=1)
    with pytest.raises(ValueError):
        replace(p.snapshot, retrieval_timestamp=datetime(2026, 1, 1))


def test_pinned_record_identity_isoforms_and_unknown_versions():
    p = parsed()
    assert p.protein.primary_accession == "Q9NZ08"
    assert p.protein.gene_symbol == "ERAP1"
    assert p.protein.taxon_id == 9606
    assert p.protein.sequence_length == 941
    assert p.protein.sequence_version == 3
    assert p.protein.record_version == 218
    assert p.protein.sequence_checksum == (
        "e7a676d4403be4bad98f60d855ac133133ae972ea93b1c2cba8d12ba8f84fb28"
    )
    assert p.isoforms[0].canonical
    assert p.isoforms[0].accession == "Q9NZ08-1"
    assert p.isoforms[0].sequence_version is None
    assert p.isoforms[1].sequence is None
    assert p.snapshot.provider_release is None


@pytest.mark.parametrize("accession", ["ERAP1", "Q9NZ08-1", "../Q9NZ08", ""])
def test_invalid_accession(accession):
    with pytest.raises(ValueError):
        validate_accession(accession)


def test_adapter_missing_optional_fields_malformed_and_wrong_taxon():
    value = json.loads(ROOT.joinpath("record.json").read_bytes())
    for key in ("entryAudit", "proteinDescription", "genes", "comments"):
        value.pop(key)
    p = parse_record(json.dumps(value).encode(), "Q9NZ08", NOW, expected_taxon=9606)
    assert p.protein.recommended_name is None
    assert p.protein.gene_symbol is None
    assert p.protein.sequence_version is None
    assert not p.isoforms
    for raw in (b"null", b"{}", b"not-json"):
        with pytest.raises(ValueError):
            parse_record(raw, "Q9NZ08", NOW, expected_taxon=9606)
    with pytest.raises(ValueError, match="taxon"):
        parse_record(
            ROOT.joinpath("record.json").read_bytes(),
            "Q9NZ08",
            NOW,
            expected_taxon=10090,
        )


@pytest.mark.parametrize("status", [404, 500])
def test_provider_http_failure(status):
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, request=request)
            )
        ) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        UniProtAdapter(client).retrieve("Q9NZ08", NOW, expected_taxon=9606)


def test_provider_network_failure():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(fail)) as client,
        pytest.raises(httpx.ConnectError),
    ):
        UniProtAdapter(client).retrieve("Q9NZ08", NOW, expected_taxon=9606)


def test_provider_release_header():
    raw = ROOT.joinpath("record.json").read_bytes()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=raw, headers={"x-uniprot-release": "test-release"}
            )
        )
    ) as client:
        p = UniProtAdapter(client).retrieve("Q9NZ08", NOW, expected_taxon=9606)
    assert p.snapshot.provider_release == "test-release"


def test_offline_replay_duplicate_mapping_and_no_automatic_claims(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network attempted during frozen replay")

    monkeypatch.setattr(httpx.Client, "get", no_network)
    projections = []
    for _ in range(2):
        with EvidenceStore() as store:
            import_curated_erap1(store)
            service = TargetIdentityService(store)
            identifier = service.import_package(PROJECT)
            assert service.import_package(PROJECT) == identifier
            projection = service.projection(PROJECT, identifier)
            projections.append(projection)
            assert store.statistics().claims == 14
            assert len(store.targets.by_accession("uniprot", "Q9NZ08")) == 1
            assert len(store.targets.for_gene("HGNC-symbol", "ERAP1")) == 1
            assert store.targets.canonical_isoform(identifier).accession == "Q9NZ08-1"
            mapping = store.targets.mappings(identifier)[0]
            assert mapping.status == MappingStatus.VERIFIED
            with pytest.raises(ValueError):
                replace(mapping, status="verified")
            with pytest.raises(RecordConflictError):
                store.targets.insert_mapping(replace(mapping, taxon_id=10090))
    assert projections[0] == projections[1]


def test_conflicting_sequence_and_version_rejected_without_overwrite():
    with EvidenceStore() as store:
        import_curated_erap1(store)
        service = TargetIdentityService(store)
        original = service.import_package(PROJECT)
        p = parsed()
        seq = "A" + p.protein.sequence[1:]
        protein = replace(
            p.protein, sequence=seq, sequence_checksum=sequence_checksum(seq)
        )
        with pytest.raises(RecordConflictError):
            service.ingest(
                PROJECT, replace(p, protein=protein), "HGNC-symbol", "ERAP1", 9606
            )
        assert store.targets.protein(original).sequence != seq
        assert len(store.targets.by_accession("uniprot", "Q9NZ08")) == 1
        with pytest.raises(RecordConflictError):
            service.ingest(
                PROJECT,
                replace(p, protein=replace(p.protein, sequence_version=4)),
                "HGNC-symbol",
                "ERAP1",
                9606,
            )


def test_metadata_refresh_retains_old_snapshot():
    with EvidenceStore() as store:
        import_curated_erap1(store)
        service = TargetIdentityService(store)
        old = service.import_package(PROJECT)
        p = parsed()
        new = service.ingest(PROJECT, p, "HGNC-symbol", "ERAP1", 9606)
        assert old != new
        assert len(store.targets.by_accession("uniprot", "Q9NZ08")) == 2
        assert store.targets.protein(old).source_snapshot_id != p.snapshot.id


def test_transaction_rolls_back_partial_ingestion(monkeypatch):
    with EvidenceStore() as store:
        import_curated_erap1(store)

        def fail(value):
            raise ValueError("injected isoform failure")

        monkeypatch.setattr(store.targets, "insert_isoform", fail)
        with pytest.raises(ValueError):
            TargetIdentityService(store).import_package(PROJECT)
        assert not store.targets.by_accession("uniprot", "Q9NZ08")
        assert (
            store._connection.execute(
                "SELECT count(*) FROM source_snapshots"
            ).fetchone()[0]
            == 0
        )


def test_package_checksums_and_tampering(tmp_path):
    for name in ("manifest.json", "manifest.sha256", "record.json"):
        (tmp_path / name).write_bytes(ROOT.joinpath(name).read_bytes())
    with EvidenceStore() as store:
        import_curated_erap1(store)
        (tmp_path / "record.json").write_bytes(b"{}")
        with pytest.raises(ValueError, match="source checksum"):
            TargetIdentityService(store).import_package(PROJECT, tmp_path)
        (tmp_path / "manifest.json").write_bytes(b"{}")
        with pytest.raises(ValueError, match="manifest checksum"):
            TargetIdentityService(store).import_package(PROJECT, tmp_path)


def test_api_identity_provenance_unknown_and_project_isolation():
    with EvidenceStore() as store:
        import_curated_erap1(store)
        DiscoveryService(store).create_erap1_demo()
        identifier = TargetIdentityService(store).import_package(PROJECT)
        api = ReadAPI(store)
        base = f"/api/projects/{PROJECT}/targets"
        assert api.get(base, {})["total"] == 1
        detail = f"{base}/{quote(identifier, safe='')}"
        assert api.get(detail, {})["protein"]["primary_accession"] == "Q9NZ08"
        assert api.get(detail + "/protein", {})["protein"]["taxon_id"] == 9606
        assert len(api.get(detail + "/isoforms", {})["isoforms"]) == 2
        assert api.get(detail + "/provenance", {})["snapshot"]["provider"] == "UniProt"
        assert api.get(f"/api/projects/{DEMO}/targets", {})["total"] == 0
        with pytest.raises(RecordNotFoundError):
            api.get(f"/api/projects/{DEMO}/targets/{quote(identifier, safe='')}", {})
        with pytest.raises(RecordNotFoundError):
            api.get(base + "/unknown", {})


def test_upgrade_reopen_and_read_only(tmp_path):
    path = tmp_path / "upgrade.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        migrations = resources.files("axis.storage.migrations")
        for item in sorted(migrations.iterdir(), key=lambda item: item.name):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 4:
                connection.execute(item.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
    with EvidenceStore(path) as store:
        import_curated_erap1(store)
        identifier = TargetIdentityService(store).import_package(PROJECT)
        assert store.statistics().schema_version == 10
    with EvidenceStore(path, read_only=True) as reopened:
        assert reopened.targets.protein(identifier).sequence_length == 941
        assert reopened.statistics().schema_version == 10


def test_nonhuman_record_cannot_map_to_human_gene_project():
    raw = json.loads(ROOT.joinpath("record.json").read_bytes())
    raw["organism"]["taxonId"] = 10090
    raw["organism"]["scientificName"] = "Mus musculus"
    p = parse_record(json.dumps(raw).encode(), "Q9NZ08", NOW, expected_taxon=10090)
    with EvidenceStore() as store:
        import_curated_erap1(store)
        with pytest.raises(ValueError, match="human HGNC"):
            TargetIdentityService(store).ingest(
                PROJECT, p, "HGNC-symbol", "ERAP1", 10090
            )
        assert not store.targets.project_ids(PROJECT)
