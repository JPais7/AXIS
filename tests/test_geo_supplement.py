import gzip
from pathlib import Path

import httpx
import pytest

from axis.ingestion import GeoApiError, GeoSupplementDownloader


def write_series_matrix(root: Path) -> None:
    path = root / "GSE1" / "GSE1_series_matrix.txt.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as output:
        output.write(
            "!Series_supplementary_file\t"
            '"ftp://ftp.ncbi.nlm.nih.gov/geo/file.all.mRNA.xls.gz"\n'
        )
        output.write(
            "!Series_supplementary_file\t"
            '"ftp://ftp.ncbi.nlm.nih.gov/geo/file.other.xls.gz"\n'
        )


def test_supplement_downloader_selects_declared_filename(
    tmp_path: Path,
) -> None:
    write_series_matrix(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.url.path.endswith("file.all.mRNA.xls.gz")
        return httpx.Response(200, content=b"supplement")

    downloader = GeoSupplementDownloader(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = downloader.download(
        "GSE1",
        filename_pattern=r"all\.mRNA",
        data_root=tmp_path,
    )[0]

    assert result.path.read_bytes() == b"supplement"
    assert result.size_bytes == 10
    assert result.checksum.startswith("sha256:")


def test_supplement_downloader_reports_missing_match(tmp_path: Path) -> None:
    write_series_matrix(tmp_path)
    downloader = GeoSupplementDownloader(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: pytest.fail("network should not be called")
            )
        )
    )

    with pytest.raises(GeoApiError, match="no supplementary filename"):
        downloader.download(
            "GSE1",
            filename_pattern="counts",
            data_root=tmp_path,
        )
