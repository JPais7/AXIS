"""Cross-repository discovery from BioStudies/ArrayExpress and NCBI SRA."""

from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from axis.ingestion.geo import EUTILS_BASE_URL, GeoApiError

BIOSTUDIES_SEARCH_URL = "https://www.ebi.ac.uk/biostudies/api/v1/search"
BIOSTUDIES_STUDY_URL = "https://www.ebi.ac.uk/biostudies/api/v1/studies"
SRA_RUNINFO_URL = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo"


@dataclass(frozen=True)
class RepositoryStudy:
    source: str
    accession: str
    title: str
    summary: str
    organism: str
    assay: str
    sample_or_run_count: int
    bioproject_id: str
    publication_ids: str
    source_uri: str


@dataclass(frozen=True)
class CrossRepositoryRun:
    records: int
    unique_records: int
    new_candidates: int
    priority_candidates: int
    output_path: Path
    new_path: Path
    priority_path: Path
    summary_path: Path


class BioStudiesClient:
    """Search the ArrayExpress collection now hosted by EMBL-EBI BioStudies."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (BioStudies discovery)"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> BioStudiesClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_study(self, accession: str) -> dict[str, Any]:
        return self._get_object(f"{BIOSTUDIES_STUDY_URL}/{accession}")

    def fetch_study_info(self, accession: str) -> dict[str, Any]:
        return self._get_object(f"{BIOSTUDIES_STUDY_URL}/{accession}/info")

    def fetch_text(self, url: str) -> str:
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeoApiError(f"BioStudies file download failed: {error}") from error
        return response.text

    def _get_object(self, url: str) -> dict[str, Any]:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GeoApiError(f"BioStudies request failed: {error}") from error
        if not isinstance(payload, dict):
            raise GeoApiError("BioStudies response must be an object")
        return cast(dict[str, Any], payload)

    def search(self, query: str, *, maximum: int = 200) -> tuple[RepositoryStudy, ...]:
        studies: list[RepositoryStudy] = []
        page = 1
        while len(studies) < maximum:
            page_size = min(100, maximum - len(studies))
            try:
                response = self._client.get(
                    BIOSTUDIES_SEARCH_URL,
                    params={
                        "query": f"accession:E-MTAB* AND ({query})",
                        "page": page,
                        "pageSize": page_size,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise GeoApiError(f"BioStudies search failed: {error}") from error
            if not isinstance(payload, dict):
                raise GeoApiError("BioStudies response must be an object")
            hits = payload.get("hits")
            if not isinstance(hits, list):
                raise GeoApiError("BioStudies response has no hits list")
            for raw in hits:
                if not isinstance(raw, dict):
                    continue
                accession = str(raw.get("accession", "")).strip()
                if not accession:
                    continue
                content = str(raw.get("content", ""))
                studies.append(
                    RepositoryStudy(
                        source="BioStudies-ArrayExpress",
                        accession=accession,
                        title=str(raw.get("title", "")).strip(),
                        summary=content,
                        organism=("Homo sapiens" if "Homo sapiens" in content else ""),
                        assay=self._assay(content),
                        sample_or_run_count=0,
                        bioproject_id="",
                        publication_ids="",
                        source_uri=(
                            "https://www.ebi.ac.uk/biostudies/arrayexpress/"
                            f"studies/{accession}"
                        ),
                    )
                )
            if not hits or len(studies) >= int(payload.get("totalHits", 0)):
                break
            page += 1
        return tuple(studies[:maximum])

    @staticmethod
    def _assay(content: str) -> str:
        lowered = content.lower()
        if "single cell" in lowered:
            return "single-cell RNA-seq"
        if "rna-seq" in lowered:
            return "RNA-seq"
        if "transcription profiling by array" in lowered:
            return "microarray"
        if "tcr repertoire" in lowered:
            return "TCR repertoire"
        return "unknown"


class SraClient:
    """Search SRA runs and aggregate them into study-level records."""

    def __init__(
        self,
        *,
        email: str | None = None,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._email = email
        self._api_key = api_key
        self._client = http_client or httpx.Client(
            timeout=60.0,
            headers={"User-Agent": "AXIS/0.1 (SRA discovery)"},
        )
        self._owns_client = http_client is None
        self._sleeper = sleeper or time.sleep

    def __enter__(self) -> SraClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_runinfo(self, accession: str) -> str:
        try:
            response = self._client.get(SRA_RUNINFO_URL, params={"acc": accession})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeoApiError(f"SRA runinfo request failed: {error}") from error
        return response.text

    def search(
        self, query: str, *, maximum_runs: int = 1000
    ) -> tuple[RepositoryStudy, ...]:
        search_query = (
            f'({query}) AND "Homo sapiens"[Organism] AND "biomol rna"[Properties]'
        )
        payload = self._get_json(
            "esearch.fcgi",
            {
                "db": "sra",
                "term": search_query,
                "retmode": "json",
                "retmax": str(maximum_runs),
            },
        )
        result = self._object(payload, "esearchresult")
        raw_ids = result.get("idlist")
        if not isinstance(raw_ids, list):
            raise GeoApiError("SRA search idlist must be a list")
        uids = [str(value) for value in raw_ids]
        aggregated: dict[str, dict[str, Any]] = {}
        for start in range(0, len(uids), 100):
            summary = self._get_json(
                "esummary.fcgi",
                {
                    "db": "sra",
                    "id": ",".join(uids[start : start + 100]),
                    "retmode": "json",
                },
            )
            records = self._object(summary, "result")
            for uid in uids[start : start + 100]:
                raw = records.get(uid)
                if not isinstance(raw, dict):
                    continue
                parsed = self._parse_experiment(str(raw.get("expxml", "")))
                key = parsed["study_accession"] or parsed["bioproject_id"]
                if not key:
                    continue
                record = aggregated.setdefault(
                    key,
                    {
                        **parsed,
                        "runs": 0,
                        "samples": set(),
                        "strategies": set(),
                    },
                )
                record["runs"] = int(record["runs"]) + 1
                cast(set[str], record["samples"]).add(parsed["sample_accession"])
                cast(set[str], record["strategies"]).add(parsed["strategy"])
        return tuple(
            RepositoryStudy(
                source="NCBI-SRA",
                accession=str(record["study_accession"]),
                title=str(record["title"]),
                summary=str(record["protocol"]),
                organism=str(record["organism"]),
                assay="|".join(sorted(cast(set[str], record["strategies"]))),
                sample_or_run_count=len(cast(set[str], record["samples"])),
                bioproject_id=str(record["bioproject_id"]),
                publication_ids="",
                source_uri=(
                    "https://www.ncbi.nlm.nih.gov/sra/?term="
                    f"{record['study_accession']}"
                ),
            )
            for record in aggregated.values()
        )

    @staticmethod
    def _parse_experiment(xml_fragment: str) -> dict[str, str]:
        try:
            root = ET.fromstring(f"<Root>{xml_fragment}</Root>")
        except ET.ParseError as error:
            raise GeoApiError(f"invalid SRA experiment XML: {error}") from error

        def attribute(path: str, name: str) -> str:
            element = root.find(path)
            return element.get(name, "") if element is not None else ""

        def text(path: str) -> str:
            element = root.find(path)
            return (element.text or "").strip() if element is not None else ""

        return {
            "study_accession": attribute("Study", "acc"),
            "title": attribute("Study", "name"),
            "sample_accession": attribute("Sample", "acc"),
            "organism": attribute("Organism", "ScientificName"),
            "bioproject_id": text("Bioproject"),
            "strategy": text("Library_descriptor/LIBRARY_STRATEGY"),
            "protocol": text("Library_descriptor/LIBRARY_CONSTRUCTION_PROTOCOL"),
        }

    def _get_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        request_params = {**params, "tool": "axis"}
        if self._email:
            request_params["email"] = self._email
        if self._api_key:
            request_params["api_key"] = self._api_key
        for attempt in range(5):
            try:
                response = self._client.get(
                    f"{EUTILS_BASE_URL}/{endpoint}", params=request_params
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise GeoApiError("SRA response must be an object")
                return cast(dict[str, Any], payload)
            except httpx.HTTPStatusError as error:
                retryable = error.response.status_code == 429 or (
                    500 <= error.response.status_code < 600
                )
                if not retryable or attempt == 4:
                    raise GeoApiError(f"SRA request failed: {error}") from error
                self._sleeper(float(2**attempt))
            except (httpx.HTTPError, ValueError) as error:
                raise GeoApiError(f"SRA request failed: {error}") from error
        raise GeoApiError("SRA request exhausted all attempts")

    @staticmethod
    def _object(parent: dict[str, Any], key: str) -> dict[str, Any]:
        value = parent.get(key)
        if not isinstance(value, dict):
            raise GeoApiError(f"SRA {key} must be an object")
        return cast(dict[str, Any], value)


class CrossRepositoryCatalogBuilder:
    """Merge repository discoveries and flag overlap with the GEO catalog."""

    QUERIES = (
        '"ankylosing spondylitis"',
        '"axial spondyloarthritis"',
        "spondyloarthritis",
    )

    def build(
        self,
        biostudies: BioStudiesClient,
        sra: SraClient,
        *,
        geo_catalog_path: str | Path = Path("data/catalog/study-catalog.tsv"),
        output_root: str | Path = Path("data/catalog/cross-repository"),
        maximum_per_query: int = 1000,
    ) -> CrossRepositoryRun:
        geo_rows = self._read(Path(geo_catalog_path))
        geo_accessions = {row["accession"] for row in geo_rows}
        geo_projects = {
            row["bioproject_id"] for row in geo_rows if row["bioproject_id"]
        }
        geo_publications = {
            item
            for row in geo_rows
            for item in row["publication_ids"].split("|")
            if item
        }
        discovered: list[RepositoryStudy] = []
        for query in self.QUERIES:
            discovered.extend(biostudies.search(query, maximum=maximum_per_query))
            discovered.extend(sra.search(query, maximum_runs=maximum_per_query))
        unique = {
            (record.source, record.accession, record.bioproject_id): record
            for record in discovered
        }
        rows = [
            self._row(
                record,
                geo_accessions=geo_accessions,
                geo_projects=geo_projects,
                geo_publications=geo_publications,
            )
            for record in unique.values()
        ]
        self._mark_cross_repository_duplicates(rows)
        rows.sort(
            key=lambda row: (
                row["overlap_status"] != "new_repository_candidate",
                str(row["source"]),
                str(row["accession"]),
            )
        )
        new_rows = [
            row for row in rows if row["overlap_status"] == "new_repository_candidate"
        ]
        priority_rows = [
            row
            for row in new_rows
            if row["triage_status"]
            in {
                "single_cell_replication_candidate",
                "bulk_or_spatial_review_candidate",
            }
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "cross-repository-catalog.tsv"
        new_path = destination / "new-repository-candidates.tsv"
        priority_path = destination / "cross-repository-priority.tsv"
        summary_path = destination / "cross-repository-catalog.json"
        self._write(output_path, rows)
        self._write(new_path, new_rows)
        self._write(priority_path, priority_rows)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "cross_repository_study_discovery",
                    "created_at": datetime.now(UTC).isoformat(),
                    "queries": self.QUERIES,
                    "records_across_queries": len(discovered),
                    "unique_repository_records": len(rows),
                    "new_repository_candidates": len(new_rows),
                    "priority_candidates": len(priority_rows),
                    "deduplication": (
                        "Exact accessions, GEO-linked accessions, BioProjects and "
                        "publication identifiers are checked. Candidate status still "
                        "requires sample-level scientific review."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CrossRepositoryRun(
            records=len(discovered),
            unique_records=len(rows),
            new_candidates=len(new_rows),
            priority_candidates=len(priority_rows),
            output_path=output_path,
            new_path=new_path,
            priority_path=priority_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _row(
        record: RepositoryStudy,
        *,
        geo_accessions: set[str],
        geo_projects: set[str],
        geo_publications: set[str],
    ) -> dict[str, object]:
        geo_match = ""
        if record.accession in geo_accessions:
            overlap = "existing_geo_accession"
            geo_match = record.accession
        elif record.bioproject_id and record.bioproject_id in geo_projects:
            overlap = "existing_geo_bioproject"
            geo_match = record.bioproject_id
        elif set(record.publication_ids.split("|")) & geo_publications:
            overlap = "existing_geo_publication"
            geo_match = record.publication_ids
        elif record.accession.startswith("E-GEOD-"):
            linked = f"GSE{record.accession.removeprefix('E-GEOD-')}"
            if linked in geo_accessions:
                overlap = "existing_geo_accession"
                geo_match = linked
            else:
                overlap = "new_repository_candidate"
        else:
            overlap = "new_repository_candidate"
        text = f"{record.title} {record.summary}".lower()
        disease_specific = bool(
            re.search(
                r"ankylosing spondylitis|axial spondyloarthritis|\baxspa\b",
                text,
            )
        )
        assay = record.assay.lower()
        if "single-cell" in assay and disease_specific:
            triage = "single_cell_replication_candidate"
        elif (
            ("rna-seq" in assay or "spatial transcript" in text)
            and disease_specific
            and not re.search(r"\btreated\b|treatment|stimulation", text)
            and record.sample_or_run_count >= 6
        ):
            triage = "bulk_or_spatial_review_candidate"
        elif re.search(r"\btreated\b|treatment|stimulation", text):
            triage = "treatment_mechanistic_context"
        elif any(
            token in assay
            for token in ("amplicon", "targeted-capture", "rip-seq", "tcr")
        ):
            triage = "targeted_or_nonexpression_context"
        elif not disease_specific:
            triage = "related_disease_context"
        else:
            triage = "manual_relevance_review"
        return {
            "source": record.source,
            "accession": record.accession,
            "title": record.title,
            "organism": record.organism,
            "assay": record.assay,
            "sample_or_run_count": record.sample_or_run_count,
            "bioproject_id": record.bioproject_id,
            "publication_ids": record.publication_ids,
            "disease_signal": (
                "axspa_specific" if disease_specific else "broad_spondyloarthritis"
            ),
            "triage_status": triage,
            "overlap_status": overlap,
            "overlap_identifier": geo_match,
            "source_uri": record.source_uri,
            "automatic_eligibility": False,
        }

    @staticmethod
    def _mark_cross_repository_duplicates(
        rows: list[dict[str, object]],
    ) -> None:
        by_title: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            normalized = re.sub(r"\W+", " ", str(row["title"]).lower()).strip()
            if normalized:
                by_title.setdefault(normalized, []).append(row)
        for duplicates in by_title.values():
            if len(duplicates) < 2:
                continue
            accessions = "|".join(sorted(str(row["accession"]) for row in duplicates))
            canonical = min(
                duplicates,
                key=lambda row: (
                    str(row["source"]) != "BioStudies-ArrayExpress",
                    str(row["accession"]),
                ),
            )
            for row in duplicates:
                row["cross_repository_group"] = accessions
                if row is not canonical:
                    row["overlap_status"] = "cross_repository_duplicate"
                    row["overlap_identifier"] = str(canonical["accession"])
                    row["triage_status"] = "duplicate_repository_record"
        for row in rows:
            row.setdefault("cross_repository_group", str(row["accession"]))

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
