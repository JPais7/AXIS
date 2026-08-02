from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from axis.cli import main
from axis.domain import Provenance, SourceKind, Study
from axis.ingestion import GeoMatrixDownload, GeoMatrixFile, GeoSearchPage
from axis.storage import EvidenceStore

runner = CliRunner()
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def make_study() -> Study:
    return Study(
        identifier="GSE234339",
        title="RIOK3 in ankylosing spondylitis",
        summary="RNA-seq of whole blood.",
        source=SourceKind.GEO,
        organisms=("Homo sapiens",),
        experiment_type="Expression profiling by high throughput sequencing",
        sample_count=8,
        platform_ids=("GPL24676",),
        publication_ids=("PMID:38974235",),
        bioproject_id="PRJNA982001",
        provenance=Provenance(
            source_kind=SourceKind.GEO,
            source_identifier="GSE234339",
            retrieved_at=NOW,
            source_uri="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE234339",
            checksum="sha256:example",
        ),
    )


def test_info_creates_database_and_reports_empty_store(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "axis.duckdb"

    result = runner.invoke(main.app, ["--database", str(database), "info"])

    assert result.exit_code == 0
    assert database.exists()
    assert "Schema version" in result.stdout
    assert "2" in result.stdout
    assert "Studies" in result.stdout


def test_studies_and_study_read_local_metadata(tmp_path: Path) -> None:
    database = tmp_path / "axis.duckdb"
    study = make_study()
    with EvidenceStore(database) as store:
        store.studies.add(study)

    listing = runner.invoke(
        main.app,
        ["--database", str(database), "studies"],
    )
    detail = runner.invoke(
        main.app,
        ["--database", str(database), "study", "gse234339"],
    )

    assert listing.exit_code == 0
    assert "GSE234339" in listing.stdout
    assert "RIOK3" in listing.stdout
    assert detail.exit_code == 0
    assert "PMID:38974235" in detail.stdout
    assert "sha256:example" in detail.stdout


def test_missing_study_returns_nonzero_exit_code(tmp_path: Path) -> None:
    database = tmp_path / "axis.duckdb"

    result = runner.invoke(
        main.app,
        ["--database", str(database), "study", "GSE999999"],
    )

    assert result.exit_code == 1
    assert "is not stored" in result.output


def test_search_persists_results_without_real_network(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database = tmp_path / "axis.duckdb"
    study = make_study()

    class FakeGeoClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "FakeGeoClient":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def search(self, query: str, *, limit: int, offset: int) -> GeoSearchPage:
            return GeoSearchPage(query, 1, offset, (study,))

    monkeypatch.setattr(main, "GeoClient", FakeGeoClient)  # type: ignore[attr-defined]

    result = runner.invoke(
        main.app,
        [
            "--database",
            str(database),
            "search",
            "axial spondyloarthritis",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "GSE234339" in result.stdout
    with EvidenceStore(database) as store:
        assert store.studies.get("GSE234339") == study


def test_download_saves_matrix_and_reports_manifest(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    matrix_path = tmp_path / "geo" / "GSE234339" / "matrix.txt.gz"
    manifest_path = matrix_path.parent / "manifest.json"

    class FakeDownloader:
        def __enter__(self) -> "FakeDownloader":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def download(self, accession: str, *, output_root: Path) -> GeoMatrixDownload:
            assert accession == "GSE234339"
            assert output_root == tmp_path / "geo"
            return GeoMatrixDownload(
                accession=accession,
                retrieved_at=NOW,
                files=(
                    GeoMatrixFile(
                        filename=matrix_path.name,
                        path=matrix_path,
                        source_uri="https://example.test/matrix.txt.gz",
                        size_bytes=42,
                        checksum="sha256:example",
                    ),
                ),
                manifest_path=manifest_path,
            )

    monkeypatch.setattr(  # type: ignore[attr-defined]
        main, "GeoMatrixDownloader", FakeDownloader
    )

    result = runner.invoke(
        main.app,
        [
            "download",
            "GSE234339",
            "--output",
            str(tmp_path / "geo"),
        ],
    )

    assert result.exit_code == 0
    assert "Downloaded GSE234339" in result.stdout
    assert "42 bytes" in result.stdout
    assert "manifest.json" in result.stdout
