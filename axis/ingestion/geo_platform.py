"""Download official GEO platform annotation tables."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from axis.ingestion.geo import GeoApiError

GEO_PLATFORM_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/geo/platforms"


@dataclass(frozen=True)
class GeoPlatformAnnotation:
    platform: str
    path: Path
    source_uri: str
    size_bytes: int
    checksum: str


class GeoPlatformDownloader:
    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (GEO platform annotation)"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> GeoPlatformDownloader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def download(
        self,
        platform: str,
        *,
        data_root: str | Path = Path("data/geo"),
    ) -> GeoPlatformAnnotation:
        platform = platform.strip().upper()
        if not platform.startswith("GPL") or not platform[3:].isdigit():
            raise ValueError(f"invalid GEO platform accession: {platform!r}")
        bucket = f"{platform[:-3]}nnn"
        source_uri = (
            f"{GEO_PLATFORM_BASE_URL}/{bucket}/{platform}/annot/{platform}.annot.gz"
        )
        directory = Path(data_root) / "platforms" / platform
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{platform}.annot.gz"
        temporary = destination.with_suffix(".gz.part")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with (
                self._client.stream("GET", source_uri) as response,
                temporary.open("wb") as output,
            ):
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
            temporary.replace(destination)
        except (httpx.HTTPError, OSError) as error:
            temporary.unlink(missing_ok=True)
            raise GeoApiError(
                f"failed to download annotation for {platform}: {error}"
            ) from error
        checksum = f"sha256:{digest.hexdigest()}"
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "platform": platform,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "source_uri": source_uri,
                    "size_bytes": size_bytes,
                    "checksum": checksum,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return GeoPlatformAnnotation(
            platform=platform,
            path=destination,
            source_uri=source_uri,
            size_bytes=size_bytes,
            checksum=checksum,
        )
