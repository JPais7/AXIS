"""Download supplementary files declared by a local GEO Series Matrix."""

from __future__ import annotations

import csv
import gzip
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class GeoSupplement:
    source_uri: str
    path: Path
    size_bytes: int
    checksum: str


class GeoSupplementDownloader:
    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=120.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (GEO supplementary download)"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> GeoSupplementDownloader:
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
        filename_pattern: str,
        data_root: str | Path = Path("data/geo"),
    ) -> tuple[GeoSupplement, ...]:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        try:
            pattern = re.compile(filename_pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"invalid filename pattern: {error}") from error
        study_root = Path(data_root) / accession
        matrices = tuple(study_root.glob(f"{accession}*_series_matrix.txt.gz"))
        if not matrices:
            raise GeoApiError(
                f"Series Matrix metadata is missing for {accession}; "
                f"run 'axis download {accession}' first"
            )
        source_uris = self._supplementary_uris(matrices[0])
        selected = tuple(
            uri for uri in source_uris if pattern.search(Path(urlparse(uri).path).name)
        )
        if not selected:
            raise GeoApiError(
                f"no supplementary filename for {accession} matches "
                f"{filename_pattern!r}"
            )
        destination = study_root / "supplementary"
        destination.mkdir(parents=True, exist_ok=True)
        return tuple(self._download(uri, destination) for uri in selected)

    @staticmethod
    def _supplementary_uris(matrix_path: Path) -> tuple[str, ...]:
        uris: list[str] = []
        try:
            with gzip.open(matrix_path, "rt", encoding="utf-8") as source:
                for line in source:
                    if not line.startswith("!Series_supplementary_file"):
                        continue
                    values = next(csv.reader([line], delimiter="\t"))
                    uris.extend(value.strip().strip('"') for value in values[1:])
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(
                f"cannot read supplementary metadata in {matrix_path}: {error}"
            ) from error
        return tuple(dict.fromkeys(uri for uri in uris if uri and uri != "NONE"))

    def _download(self, source_uri: str, destination: Path) -> GeoSupplement:
        https_uri = source_uri.replace(
            "ftp://ftp.ncbi.nlm.nih.gov/", "https://ftp.ncbi.nlm.nih.gov/"
        )
        filename = Path(urlparse(https_uri).path).name
        path = destination / filename
        temporary = path.with_suffix(path.suffix + ".part")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with (
                self._client.stream("GET", https_uri) as response,
                temporary.open("wb") as output,
            ):
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
            temporary.replace(path)
        except (httpx.HTTPError, OSError) as error:
            temporary.unlink(missing_ok=True)
            raise GeoApiError(
                f"failed to download supplementary file {https_uri}: {error}"
            ) from error
        return GeoSupplement(
            source_uri=https_uri,
            path=path,
            size_bytes=size_bytes,
            checksum=f"sha256:{digest.hexdigest()}",
        )
