import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from axis.ingestion import GeoApiError, GeoMatrixDownloader

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
MATRIX_CONTENT = b"!Series_title\tExample\n!series_matrix_table_begin\n"


def matrix_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/matrix/"):
        return httpx.Response(
            200,
            text=(
                '<a href="GSE234339_series_matrix.txt.gz">'
                "GSE234339_series_matrix.txt.gz</a>"
            ),
        )
    if request.url.path.endswith("/GSE234339_series_matrix.txt.gz"):
        return httpx.Response(200, content=MATRIX_CONTENT)
    raise AssertionError(f"unexpected request: {request.url}")


def make_downloader(handler: object = matrix_handler) -> GeoMatrixDownloader:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return GeoMatrixDownloader(
        http_client=httpx.Client(transport=transport),
        clock=lambda: NOW,
    )


def test_download_writes_matrix_and_traceable_manifest(tmp_path: Path) -> None:
    downloader = make_downloader()

    result = downloader.download("gse234339", output_root=tmp_path)

    assert result.accession == "GSE234339"
    assert len(result.files) == 1
    downloaded = result.files[0]
    assert downloaded.path.read_bytes() == MATRIX_CONTENT
    assert downloaded.source_uri.endswith("GSE234339_series_matrix.txt.gz")
    assert downloaded.size_bytes == len(MATRIX_CONTENT)
    assert downloaded.checksum.startswith("sha256:")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["accession"] == "GSE234339"
    assert manifest["retrieved_at"] == NOW.isoformat()
    assert manifest["files"][0]["checksum"] == downloaded.checksum


def test_download_supports_multiple_platform_matrices(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matrix/"):
            return httpx.Response(
                200,
                text=(
                    '<a href="GSE1-GPL10_series_matrix.txt.gz">first</a>'
                    '<a href="GSE1-GPL20_series_matrix.txt.gz">second</a>'
                ),
            )
        return httpx.Response(200, content=b"matrix")

    result = make_downloader(handler).download("GSE1", output_root=tmp_path)

    assert tuple(file.filename for file in result.files) == (
        "GSE1-GPL10_series_matrix.txt.gz",
        "GSE1-GPL20_series_matrix.txt.gz",
    )


def test_download_rejects_invalid_accession_without_network(tmp_path: Path) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be called")

    with pytest.raises(ValueError, match="invalid GEO Series"):
        make_downloader(fail).download("GDS123", output_root=tmp_path)


def test_download_reports_when_series_has_no_matrix(tmp_path: Path) -> None:
    downloader = make_downloader(
        lambda _: httpx.Response(200, text="<html>No matrix files</html>")
    )

    with pytest.raises(GeoApiError, match="no Series Matrix"):
        downloader.download("GSE234339", output_root=tmp_path)
