"""Download traceable GEO Series Matrix files from the NCBI FTP service."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx

from axis.ingestion.geo import GSE_PATTERN, GeoApiError

GEO_FTP_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/geo/series"


@dataclass(frozen=True)
class GeoMatrixFile:
    filename: str
    path: Path
    source_uri: str
    size_bytes: int
    checksum: str


@dataclass(frozen=True)
class GeoMatrixDownload:
    accession: str
    retrieved_at: datetime
    files: tuple[GeoMatrixFile, ...]
    manifest_path: Path


class GeoMatrixDownloader:
    """Discovers and downloads processed Series Matrix files for one GSE."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (GEO Series Matrix download)"},
        )
        self._owns_client = http_client is None
        self._clock = clock or (lambda: datetime.now(UTC))

    def __enter__(self) -> GeoMatrixDownloader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def download(
        self,
        accession: str,
        *,
        output_root: str | Path = Path("data/geo"),
    ) -> GeoMatrixDownload:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")

        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")

        matrix_url = self._matrix_directory_url(accession)
        filenames = self._discover_filenames(accession, matrix_url)
        destination = Path(output_root) / accession
        destination.mkdir(parents=True, exist_ok=True)
        files = tuple(
            self._download_file(
                urljoin(matrix_url, filename),
                destination / filename,
            )
            for filename in filenames
        )
        manifest_path = destination / "manifest.json"
        self._write_manifest(
            manifest_path,
            accession=accession,
            retrieved_at=retrieved_at,
            files=files,
        )
        return GeoMatrixDownload(
            accession=accession,
            retrieved_at=retrieved_at,
            files=files,
            manifest_path=manifest_path,
        )

    @staticmethod
    def _matrix_directory_url(accession: str) -> str:
        bucket = f"{accession[:-3]}nnn"
        return f"{GEO_FTP_BASE_URL}/{bucket}/{accession}/matrix/"

    def _discover_filenames(self, accession: str, matrix_url: str) -> tuple[str, ...]:
        try:
            response = self._client.get(matrix_url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeoApiError(
                f"failed to list GEO matrix files for {accession}: {error}"
            ) from error

        pattern = re.compile(
            rf'href=["\']({re.escape(accession)}'
            rf'(?:-[^"\'/]+)?_series_matrix\.txt\.gz)["\']',
            re.IGNORECASE,
        )
        filenames = tuple(
            dict.fromkeys(match.group(1) for match in pattern.finditer(response.text))
        )
        if not filenames:
            raise GeoApiError(
                f"GEO has no Series Matrix files available for {accession}"
            )
        return filenames

    def _download_file(self, source_uri: str, destination: Path) -> GeoMatrixFile:
        temporary = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with (
                self._stream(source_uri) as response,
                temporary.open("wb") as output,
            ):
                for chunk in response.iter_bytes():
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
            temporary.replace(destination)
        except (httpx.HTTPError, OSError) as error:
            temporary.unlink(missing_ok=True)
            raise GeoApiError(f"failed to download {source_uri}: {error}") from error
        return GeoMatrixFile(
            filename=destination.name,
            path=destination,
            source_uri=source_uri,
            size_bytes=size_bytes,
            checksum=f"sha256:{digest.hexdigest()}",
        )

    @contextmanager
    def _stream(self, source_uri: str) -> Iterator[httpx.Response]:
        with self._client.stream("GET", source_uri) as response:
            response.raise_for_status()
            yield response

    @staticmethod
    def _write_manifest(
        path: Path,
        *,
        accession: str,
        retrieved_at: datetime,
        files: tuple[GeoMatrixFile, ...],
    ) -> None:
        payload = {
            "accession": accession,
            "retrieved_at": retrieved_at.isoformat(),
            "files": [
                {
                    **asdict(file),
                    "path": str(file.path),
                }
                for file in files
            ],
        }
        temporary = path.with_suffix(".json.part")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
