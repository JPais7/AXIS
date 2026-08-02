"""Minimal NCBI GEO metadata connector using Entrez E-utilities."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

import httpx

from axis.domain import Provenance, SourceKind, Study
from axis.storage import StudyRepository

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GEO_ACCESSION_URL = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
GSE_PATTERN = re.compile(r"^GSE\d+$", re.IGNORECASE)

JsonObject = dict[str, Any]


class GeoApiError(RuntimeError):
    """Raised when NCBI returns malformed or incomplete metadata."""


@dataclass(frozen=True)
class GeoSearchPage:
    query: str
    total: int
    offset: int
    studies: tuple[Study, ...]


class GeoClient:
    """Searches GEO Series metadata without downloading expression matrices."""

    def __init__(
        self,
        *,
        email: str | None = None,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        maximum_attempts: int = 5,
    ) -> None:
        if maximum_attempts < 1:
            raise ValueError("maximum_attempts must be positive")
        self._email = email
        self._api_key = api_key
        self._client = http_client or httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "AXIS/0.1 (GEO metadata discovery)"},
        )
        self._owns_client = http_client is None
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper or time.sleep
        self._maximum_attempts = maximum_attempts

    def __enter__(self) -> GeoClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search(self, query: str, *, limit: int = 20, offset: int = 0) -> GeoSearchPage:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if offset < 0:
            raise ValueError("offset must not be negative")

        geo_query = f"({query}) AND gse[Entry Type]"
        payload = self._get_json(
            "esearch.fcgi",
            {
                "db": "gds",
                "term": geo_query,
                "retmode": "json",
                "retmax": str(limit),
                "retstart": str(offset),
            },
        )
        result = self._object(payload, "esearchresult")
        total = self._integer(result.get("count"), "esearchresult.count")
        uids = self._string_list(result.get("idlist"), "esearchresult.idlist")
        studies = self._summaries(uids)
        return GeoSearchPage(
            query=query,
            total=total,
            offset=offset,
            studies=studies,
        )

    def metadata(self, accessions: Iterable[str]) -> tuple[Study, ...]:
        normalized = tuple(dict.fromkeys(value.upper() for value in accessions))
        if not normalized:
            return ()
        if len(normalized) > 200:
            raise ValueError("at most 200 accessions can be requested at once")
        invalid = tuple(
            value for value in normalized if not GSE_PATTERN.fullmatch(value)
        )
        if invalid:
            raise ValueError(f"invalid GEO Series accession: {invalid[0]!r}")

        accession_query = " OR ".join(f"{value}[Accession]" for value in normalized)
        payload = self._get_json(
            "esearch.fcgi",
            {
                "db": "gds",
                "term": f"({accession_query}) AND gse[Entry Type]",
                "retmode": "json",
                "retmax": str(len(normalized)),
            },
        )
        result = self._object(payload, "esearchresult")
        uids = self._string_list(result.get("idlist"), "esearchresult.idlist")
        studies_by_accession = {
            study.identifier: study for study in self._summaries(uids)
        }
        return tuple(
            studies_by_accession[accession]
            for accession in normalized
            if accession in studies_by_accession
        )

    def _summaries(self, uids: tuple[str, ...]) -> tuple[Study, ...]:
        if not uids:
            return ()
        payload = self._get_json(
            "esummary.fcgi",
            {
                "db": "gds",
                "id": ",".join(uids),
                "retmode": "json",
            },
        )
        result = self._object(payload, "result")
        returned_uids = self._string_list(result.get("uids"), "result.uids")
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return tuple(
            self._parse_study(
                self._object(result, uid),
                retrieved_at=retrieved_at,
            )
            for uid in returned_uids
        )

    def _parse_study(self, record: JsonObject, *, retrieved_at: datetime) -> Study:
        accession = self._string(record.get("accession"), "accession").upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise GeoApiError(f"ESummary returned non-Series accession {accession!r}")
        title = self._string(record.get("title"), f"{accession}.title")
        summary = self._optional_string(record.get("summary")) or ""
        taxon = self._optional_string(record.get("taxon"))
        experiment_type = self._optional_string(record.get("gdstype"))
        sample_count = self._optional_integer(record.get("n_samples"))
        platforms = tuple(
            f"GPL{platform}"
            for platform in re.findall(
                r"\d+", self._optional_string(record.get("gpl")) or ""
            )
        )
        pubmed_ids = tuple(
            f"PMID:{value}"
            for value in self._string_list(
                record.get("pubmedids", []), f"{accession}.pubmedids"
            )
        )
        released_on = self._parse_date(self._optional_string(record.get("pdat")))
        canonical_record = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        checksum = hashlib.sha256(canonical_record.encode()).hexdigest()
        return Study(
            identifier=accession,
            title=title,
            summary=summary,
            source=SourceKind.GEO,
            organisms=(taxon,) if taxon else (),
            experiment_type=experiment_type,
            sample_count=sample_count,
            platform_ids=platforms,
            publication_ids=pubmed_ids,
            bioproject_id=self._optional_string(record.get("bioproject")),
            released_on=released_on,
            provenance=Provenance(
                source_kind=SourceKind.GEO,
                source_identifier=accession,
                retrieved_at=retrieved_at,
                source_uri=GEO_ACCESSION_URL.format(accession=accession),
                checksum=f"sha256:{checksum}",
            ),
        )

    def _get_json(self, endpoint: str, params: dict[str, str]) -> JsonObject:
        request_params = {
            **params,
            "tool": "axis",
        }
        if self._email:
            request_params["email"] = self._email
        if self._api_key:
            request_params["api_key"] = self._api_key
        for attempt in range(self._maximum_attempts):
            try:
                response = self._client.get(
                    f"{EUTILS_BASE_URL}/{endpoint}",
                    params=request_params,
                )
                response.raise_for_status()
                payload = response.json()
                break
            except httpx.HTTPStatusError as error:
                retryable = error.response.status_code == 429 or (
                    500 <= error.response.status_code < 600
                )
                if not retryable or attempt + 1 == self._maximum_attempts:
                    raise GeoApiError(f"NCBI GEO request failed: {error}") from error
                retry_after = error.response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = float(2**attempt)
                self._sleeper(max(delay, 0.0))
            except (httpx.HTTPError, ValueError) as error:
                raise GeoApiError(f"NCBI GEO request failed: {error}") from error
        else:  # pragma: no cover - the loop either succeeds or raises
            raise GeoApiError("NCBI GEO request exhausted all attempts")
        if not isinstance(payload, dict):
            raise GeoApiError("NCBI GEO response must be a JSON object")
        return cast(JsonObject, payload)

    @staticmethod
    def _object(parent: JsonObject, key: str) -> JsonObject:
        value = parent.get(key)
        if not isinstance(value, dict):
            raise GeoApiError(f"{key} must be a JSON object")
        return cast(JsonObject, value)

    @staticmethod
    def _string(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise GeoApiError(f"{field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise GeoApiError("expected a string value")
        return value.strip() or None

    @staticmethod
    def _string_list(value: object, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise GeoApiError(f"{field} must be a list of strings")
        return tuple(cast(list[str], value))

    @staticmethod
    def _integer(value: object, field: str) -> int:
        try:
            return int(cast(str | int, value))
        except (TypeError, ValueError) as error:
            raise GeoApiError(f"{field} must be an integer") from error

    @classmethod
    def _optional_integer(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return cls._integer(value, "integer value")

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if value is None:
            return None
        try:
            return datetime.strptime(value, "%Y/%m/%d").date()
        except ValueError as error:
            raise GeoApiError(f"invalid GEO publication date {value!r}") from error


class GeoIngestionService:
    """Persists newly discovered GEO studies through the storage boundary."""

    def __init__(self, client: GeoClient, studies: StudyRepository) -> None:
        self._client = client
        self._studies = studies

    def discover(
        self, query: str, *, limit: int = 20, offset: int = 0
    ) -> GeoSearchPage:
        page = self._client.search(query, limit=limit, offset=offset)
        for study in page.studies:
            if self._studies.get_optional(study.identifier) is None:
                self._studies.add(study)
        return page
