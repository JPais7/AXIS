"""Large-scale metadata catalog with role-aware study triage."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.domain import Study
from axis.ingestion.geo import GeoClient


@dataclass(frozen=True)
class CatalogQuery:
    family: str
    role: str
    query: str


DEFAULT_QUERIES: tuple[CatalogQuery, ...] = (
    CatalogQuery(
        "axspa_direct",
        "direct_disease_candidate",
        '"ankylosing spondylitis" OR "axial spondyloarthritis" OR axSpA',
    ),
    CatalogQuery(
        "spondyloarthritis_related",
        "direct_disease_candidate",
        'spondyloarthritis OR "HLA-B27"',
    ),
    CatalogQuery(
        "psoriatic_disease",
        "related_disease_context",
        '"psoriatic arthritis" OR psoriasis',
    ),
    CatalogQuery(
        "intestinal_inflammation",
        "related_disease_context",
        '"Crohn disease" OR "inflammatory bowel disease" OR colitis',
    ),
    CatalogQuery(
        "uveitis",
        "related_disease_context",
        'uveitis OR "anterior uveitis"',
    ),
    CatalogQuery(
        "inflammatory_arthritis",
        "related_disease_context",
        '"rheumatoid arthritis" OR "reactive arthritis"',
    ),
    CatalogQuery(
        "immune_cell_perturbation",
        "mechanistic_context",
        '(PBMC OR "T cell" OR monocyte OR macrophage) AND '
        "(CRISPR OR knockdown OR perturbation OR inhibitor)",
    ),
    CatalogQuery(
        "immune_drug_response",
        "treatment_response_context",
        '(PBMC OR "T cell" OR monocyte) AND '
        '("drug response" OR "treatment response" OR anti-TNF)',
    ),
)

ROLE_PRIORITY = {
    "direct_disease_candidate": 0,
    "related_disease_context": 1,
    "treatment_response_context": 2,
    "mechanistic_context": 3,
}


@dataclass(frozen=True)
class StudyCatalogRun:
    queries: int
    discovered_records: int
    unique_studies: int
    direct_candidates: int
    download_candidates: int
    output_path: Path
    queue_path: Path
    summary_path: Path


class StudyCatalogBuilder:
    """Discover broadly, but download only scientifically reviewable studies."""

    def build(
        self,
        client: GeoClient,
        *,
        queries: tuple[CatalogQuery, ...] = DEFAULT_QUERIES,
        maximum_per_query: int = 500,
        page_size: int = 200,
        output_root: str | Path = Path("data/catalog"),
    ) -> StudyCatalogRun:
        if maximum_per_query < 1:
            raise ValueError("maximum_per_query must be positive")
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        matches: dict[str, dict[str, object]] = {}
        discovered = 0
        query_totals: dict[str, int] = {}
        for specification in queries:
            offset = 0
            total = 0
            while offset < maximum_per_query:
                limit = min(page_size, maximum_per_query - offset)
                page = client.search(specification.query, limit=limit, offset=offset)
                total = page.total
                discovered += len(page.studies)
                for study in page.studies:
                    record = matches.setdefault(
                        study.identifier,
                        {
                            "study": study,
                            "families": set(),
                            "roles": set(),
                        },
                    )
                    cast_set(record["families"]).add(specification.family)
                    cast_set(record["roles"]).add(specification.role)
                offset += len(page.studies)
                if not page.studies or offset >= page.total:
                    break
            query_totals[specification.family] = total
        publication_counts: dict[str, int] = {}
        bioproject_counts: dict[str, int] = {}
        for record in matches.values():
            study = cast_study(record["study"])
            for publication in study.publication_ids:
                publication_counts[publication] = (
                    publication_counts.get(publication, 0) + 1
                )
            if study.bioproject_id:
                bioproject_counts[study.bioproject_id] = (
                    bioproject_counts.get(study.bioproject_id, 0) + 1
                )
        rows = [
            self._row(
                record,
                publication_counts=publication_counts,
                bioproject_counts=bioproject_counts,
            )
            for record in matches.values()
        ]
        rows.sort(
            key=lambda row: (
                ROLE_PRIORITY.get(str(row["primary_role"]), 99),
                row["eligibility_status"] != "metadata_review_candidate",
                -cast_sample_count(row["sample_count"]),
                str(row["accession"]),
            )
        )
        queue = [
            row
            for row in rows
            if row["eligibility_status"] == "metadata_review_candidate"
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "study-catalog.tsv"
        queue_path = destination / "download-review-queue.tsv"
        summary_path = destination / "study-catalog.json"
        self._write(output_path, rows)
        self._write(queue_path, queue)
        direct = sum(row["primary_role"] == "direct_disease_candidate" for row in rows)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "large_scale_study_metadata_catalog",
                    "created_at": datetime.now(UTC).isoformat(),
                    "source": "NCBI GEO",
                    "queries": [
                        {
                            "family": item.family,
                            "role": item.role,
                            "query": item.query,
                            "repository_total": query_totals[item.family],
                        }
                        for item in queries
                    ],
                    "records_returned_across_queries": discovered,
                    "unique_accessions": len(rows),
                    "direct_disease_candidates": direct,
                    "download_review_candidates": len(queue),
                    "deduplication": (
                        "exact GEO accessions are merged; shared BioProject and "
                        "publication identifiers are flagged but not automatically "
                        "collapsed because one project can contain distinct cohorts"
                    ),
                    "download_policy": (
                        "cataloguing never downloads expression matrices; only "
                        "human expression studies with at least four samples enter "
                        "manual metadata review"
                    ),
                    "warning": (
                        "Keyword classification is a triage step, not scientific "
                        "eligibility. Case/control design, tissue, treatment and "
                        "sample independence must be verified before analysis."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return StudyCatalogRun(
            queries=len(queries),
            discovered_records=discovered,
            unique_studies=len(rows),
            direct_candidates=direct,
            download_candidates=len(queue),
            output_path=output_path,
            queue_path=queue_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _row(
        record: dict[str, object],
        *,
        publication_counts: dict[str, int],
        bioproject_counts: dict[str, int],
    ) -> dict[str, object]:
        study = record["study"]
        if not isinstance(study, Study):
            raise TypeError("catalog record study must be a Study")
        roles = sorted(
            cast_set(record["roles"]),
            key=lambda role: ROLE_PRIORITY.get(role, 99),
        )
        families = sorted(cast_set(record["families"]))
        organism = "|".join(study.organisms)
        experiment = study.experiment_type or ""
        human = any("homo sapiens" in value.lower() for value in study.organisms)
        expression = bool(
            re.search(
                r"expression profiling|rna.?seq|single.?cell|transcript",
                f"{experiment} {study.title} {study.summary}",
                re.IGNORECASE,
            )
        )
        enough_samples = (study.sample_count or 0) >= 4
        if human and expression and enough_samples:
            eligibility = "metadata_review_candidate"
        elif not human:
            eligibility = "context_only_non_human"
        elif not expression:
            eligibility = "context_only_non_expression"
        else:
            eligibility = "insufficient_sample_count_or_metadata"
        shared_publication = any(
            publication_counts.get(identifier, 0) > 1
            for identifier in study.publication_ids
        )
        shared_bioproject = bool(
            study.bioproject_id and bioproject_counts.get(study.bioproject_id, 0) > 1
        )
        return {
            "accession": study.identifier,
            "primary_role": roles[0],
            "matched_roles": "|".join(roles),
            "query_families": "|".join(families),
            "title": study.title,
            "summary": study.summary,
            "organisms": organism,
            "experiment_type": experiment,
            "sample_count": study.sample_count or "",
            "platform_ids": "|".join(study.platform_ids),
            "publication_ids": "|".join(study.publication_ids),
            "bioproject_id": study.bioproject_id or "",
            "released_on": study.released_on.isoformat() if study.released_on else "",
            "shared_publication_flag": shared_publication,
            "shared_bioproject_flag": shared_bioproject,
            "eligibility_status": eligibility,
            "estimated_download_class": StudyCatalogBuilder._download_class(study),
            "source_uri": study.provenance.source_uri or "",
            "metadata_checksum": study.provenance.checksum or "",
        }

    @staticmethod
    def _download_class(study: Study) -> str:
        samples = study.sample_count or 0
        text = f"{study.experiment_type or ''} {study.title}".lower()
        if "single" in text and samples >= 20:
            return "very_large"
        if "high throughput sequencing" in text or "rna-seq" in text:
            return "large" if samples >= 20 else "medium"
        if samples >= 100:
            return "medium"
        return "small"

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)


def cast_set(value: object) -> set[str]:
    if not isinstance(value, set) or any(not isinstance(item, str) for item in value):
        raise TypeError("catalog roles and families must be sets of strings")
    return value


def cast_study(value: object) -> Study:
    if not isinstance(value, Study):
        raise TypeError("catalog record study must be a Study")
    return value


def cast_sample_count(value: object) -> int:
    if value == "":
        return 0
    if not isinstance(value, int):
        raise TypeError("catalog sample count must be an integer")
    return value
