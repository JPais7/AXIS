from datetime import UTC, datetime
from pathlib import Path

from axis.domain import Provenance, SourceKind, Study
from axis.ingestion import GeoSearchPage
from axis.ingestion.study_catalog import StudyCatalogBuilder


def _study(identifier: str, title: str) -> Study:
    return Study(
        identifier=identifier,
        title=title,
        summary="Ankylosing spondylitis case control transcriptome study.",
        source=SourceKind.GEO,
        provenance=Provenance(
            source_kind=SourceKind.GEO,
            source_identifier=identifier,
            retrieved_at=datetime(2026, 7, 27, tzinfo=UTC),
        ),
        organisms=("Homo sapiens",),
        platform_ids=("GPL1",),
        sample_count=20,
        experiment_type="Expression profiling by array",
        publication_ids=("PMID:1",),
        bioproject_id="PRJNA1",
    )


class FakeGeoClient:
    def search(self, query: str, *, limit: int = 20, offset: int = 0) -> GeoSearchPage:
        studies = [
            _study("GSE1", "Axial spondyloarthritis blood"),
            _study("GSE2", "Ankylosing spondylitis immune cells"),
        ]
        return GeoSearchPage(
            query, len(studies), offset, tuple(studies[offset : offset + limit])
        )


def test_catalog_deduplicates_and_preserves_provenance(tmp_path: Path) -> None:
    result = StudyCatalogBuilder().build(
        FakeGeoClient(),  # type: ignore[arg-type]
        maximum_per_query=10,
        page_size=1,
        output_root=tmp_path,
    )

    assert result.discovered_records == 16
    assert result.unique_studies == 2
    assert result.download_candidates == 2

    catalog = result.output_path.read_text(encoding="utf-8")
    assert catalog.count("\n") == 3
    assert "axspa_direct" in catalog
    assert "spondyloarthritis_related" in catalog
    assert "\tTrue\tTrue\tmetadata_review_candidate\t" in catalog

    queue = result.queue_path.read_text(encoding="utf-8")
    assert "GSE1" in queue
    assert "GSE2" in queue
