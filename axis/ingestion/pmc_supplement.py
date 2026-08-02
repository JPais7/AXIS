"""Download selected supplementary files from PubMed Central OA packages."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

import httpx

from axis.ingestion.geo import GeoApiError

PMC_OA_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
EUROPE_PMC_SUPPLEMENTS = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/"
    "{pmcid}/supplementaryFiles"
)


@dataclass(frozen=True)
class PmcSupplement:
    pmcid: str
    archive_uri: str
    member_name: str
    local_path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True)
class PmcSupplementRun:
    pmcid: str
    files: int
    output_root: Path
    manifest_path: Path
    supplements: tuple[PmcSupplement, ...]


class PmcSupplementDownloader:
    """Fetch an OA archive and extract only explicitly selected small files."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=120.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (PMC supplement acquisition)"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> PmcSupplementDownloader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def download(
        self,
        pmcid: str,
        *,
        suffixes: tuple[str, ...] = (".xlsx", ".csv", ".tsv"),
        output_root: str | Path = Path("data/publications"),
        maximum_file_bytes: int = 25_000_000,
    ) -> PmcSupplementRun:
        normalized = pmcid.strip().upper()
        if not normalized.startswith("PMC") or not normalized[3:].isdigit():
            raise ValueError(f"invalid PMCID: {pmcid}")
        archive_uri = self._archive_uri(normalized)
        archive_format = "tgz"
        try:
            archive = self._get(archive_uri).content
        except GeoApiError:
            archive_uri = EUROPE_PMC_SUPPLEMENTS.format(pmcid=normalized)
            archive = self._get(archive_uri).content
            archive_format = "zip"
        destination = Path(output_root) / normalized / "supplements"
        destination.mkdir(parents=True, exist_ok=True)
        selected: list[PmcSupplement] = []
        if archive_format == "tgz":
            try:
                with tarfile.open(
                    fileobj=io.BytesIO(archive), mode="r:gz"
                ) as package:
                    selected.extend(
                        self._extract_selected(
                            package,
                            destination,
                            normalized,
                            archive_uri,
                            suffixes,
                            maximum_file_bytes,
                        )
                    )
            except tarfile.TarError as error:
                raise GeoApiError(f"invalid PMC OA archive: {error}") from error
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(archive)) as package:
                    selected.extend(
                        self._extract_zip_selected(
                            package,
                            destination,
                            normalized,
                            archive_uri,
                            suffixes,
                            maximum_file_bytes,
                        )
                    )
            except zipfile.BadZipFile as error:
                raise GeoApiError(
                    f"invalid Europe PMC supplement archive: {error}"
                ) from error
        manifest_path = destination / "supplement-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "pmcid": normalized,
                    "archive_uri": archive_uri,
                    "selected_suffixes": list(suffixes),
                    "files": [
                        {**asdict(item), "local_path": str(item.local_path)}
                        for item in selected
                    ],
                    "warning": (
                        "Supplementary tables are publication-level evidence; "
                        "inspect their contents before treating them as expression "
                        "matrices."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return PmcSupplementRun(
            normalized,
            len(selected),
            destination,
            manifest_path,
            tuple(selected),
        )

    @staticmethod
    def _extract_selected(
        package: tarfile.TarFile,
        destination: Path,
        pmcid: str,
        archive_uri: str,
        suffixes: tuple[str, ...],
        maximum_file_bytes: int,
    ) -> list[PmcSupplement]:
        selected: list[PmcSupplement] = []
        accepted = tuple(suffix.lower() for suffix in suffixes)
        for member in package.getmembers():
            if not member.isfile():
                continue
            filename = PurePosixPath(member.name).name
            if not filename.lower().endswith(accepted):
                continue
            if member.size > maximum_file_bytes:
                raise ValueError(
                    f"selected PMC file exceeds size limit: {member.name}"
                )
            source = package.extractfile(member)
            if source is None:
                continue
            content = source.read()
            local_path = destination / filename
            local_path.write_bytes(content)
            selected.append(
                PmcSupplement(
                    pmcid=pmcid,
                    archive_uri=archive_uri,
                    member_name=member.name,
                    local_path=local_path,
                    bytes=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            )
        return selected

    def _archive_uri(self, pmcid: str) -> str:
        response = self._get(PMC_OA_API, params={"id": pmcid})
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise GeoApiError(f"invalid PMC OA response: {error}") from error
        link = root.find(".//link[@format='tgz']")
        if link is None or not link.get("href"):
            raise GeoApiError(f"PMC OA package unavailable for {pmcid}")
        uri = str(link.get("href")).replace("ftp://", "https://", 1)
        return uri.replace(
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/",
            "https://ftp.ncbi.nlm.nih.gov/pmc/",
            1,
        )

    @staticmethod
    def _extract_zip_selected(
        package: zipfile.ZipFile,
        destination: Path,
        pmcid: str,
        archive_uri: str,
        suffixes: tuple[str, ...],
        maximum_file_bytes: int,
    ) -> list[PmcSupplement]:
        selected: list[PmcSupplement] = []
        accepted = tuple(suffix.lower() for suffix in suffixes)
        for member in package.infolist():
            filename = PurePosixPath(member.filename).name
            if not filename.lower().endswith(accepted):
                continue
            if member.file_size > maximum_file_bytes:
                raise ValueError(
                    f"selected PMC file exceeds size limit: {member.filename}"
                )
            content = package.read(member)
            local_path = destination / filename
            local_path.write_bytes(content)
            selected.append(
                PmcSupplement(
                    pmcid=pmcid,
                    archive_uri=archive_uri,
                    member_name=member.filename,
                    local_path=local_path,
                    bytes=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            )
        return selected

    def _get(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeoApiError(f"PMC supplement request failed: {error}") from error
        return response
