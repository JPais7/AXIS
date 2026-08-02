import csv
from pathlib import Path

from axis.ingestion import CrossRepositoryCatalogBuilder, RepositoryStudy


class FakeRepositoryClient:
    def __init__(self, records: tuple[RepositoryStudy, ...]) -> None:
        self.records = records

    def search(self, query: str, **_: object) -> tuple[RepositoryStudy, ...]:
        return self.records


def test_cross_repository_catalog_flags_bioproject_overlap(tmp_path: Path) -> None:
    geo = tmp_path / "geo.tsv"
    geo.write_text(
        "accession\tbioproject_id\tpublication_ids\nGSE1\tPRJNA1\tPMID:1\n",
        encoding="utf-8",
    )
    existing = RepositoryStudy(
        "NCBI-SRA",
        "SRP1",
        "Ankylosing spondylitis RNA-seq",
        "case control",
        "Homo sapiens",
        "RNA-Seq",
        12,
        "PRJNA1",
        "",
        "https://example/SRP1",
    )
    novel = RepositoryStudy(
        "BioStudies-ArrayExpress",
        "E-MTAB-1",
        "Axial spondyloarthritis single-cell RNA-seq",
        "patients and controls",
        "Homo sapiens",
        "single-cell RNA-seq",
        8,
        "",
        "",
        "https://example/E-MTAB-1",
    )

    result = CrossRepositoryCatalogBuilder().build(
        FakeRepositoryClient((novel,)),  # type: ignore[arg-type]
        FakeRepositoryClient((existing,)),  # type: ignore[arg-type]
        geo_catalog_path=geo,
        output_root=tmp_path,
        maximum_per_query=10,
    )

    assert result.unique_records == 2
    assert result.new_candidates == 1
    assert result.priority_candidates == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = {row["accession"]: row for row in csv.DictReader(source, delimiter="\t")}
    assert rows["SRP1"]["overlap_status"] == "existing_geo_bioproject"
    assert rows["E-MTAB-1"]["overlap_status"] == "new_repository_candidate"
