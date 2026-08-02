import io
import tarfile
from pathlib import Path

import httpx

from axis.ingestion import PmcSupplementDownloader


def _archive() -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w:gz") as archive:
        content = b"fake workbook"
        info = tarfile.TarInfo("article/supplement.xlsx")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
        ignored = b"image"
        image = tarfile.TarInfo("article/figure.jpg")
        image.size = len(ignored)
        archive.addfile(image, io.BytesIO(ignored))
    return target.getvalue()


def test_pmc_downloader_extracts_only_selected_safe_files(
    tmp_path: Path,
) -> None:
    archive = _archive()

    def handler(request: httpx.Request) -> httpx.Response:
        if "oa.fcgi" in str(request.url):
            return httpx.Response(
                200,
                text=(
                    "<OA><records><record><link format='tgz' "
                    "href='ftp://example.test/article.tar.gz'/>"
                    "</record></records></OA>"
                ),
            )
        return httpx.Response(200, content=archive)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = PmcSupplementDownloader(http_client=client).download(
        "PMC123", output_root=tmp_path
    )

    assert result.files == 1
    assert result.supplements[0].local_path.read_bytes() == b"fake workbook"
    assert not (result.output_root / "figure.jpg").exists()


def test_pmc_downloader_translates_ncbi_ftp_path(tmp_path: Path) -> None:
    archive = _archive()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if "oa.fcgi" in str(request.url):
            return httpx.Response(
                200,
                text=(
                    "<OA><link format='tgz' "
                    "href='ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/a.tar.gz'/>"
                    "</OA>"
                ),
            )
        return httpx.Response(200, content=archive)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    PmcSupplementDownloader(http_client=client).download(
        "PMC123", output_root=tmp_path
    )

    assert requested[-1] == "https://ftp.ncbi.nlm.nih.gov/pmc/a.tar.gz"
