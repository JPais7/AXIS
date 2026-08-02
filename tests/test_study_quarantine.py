import csv
from pathlib import Path

from axis.analysis import StudyQuarantineBuilder


def test_quarantine_never_reintroduces_frozen_discovery(tmp_path: Path) -> None:
    geo = tmp_path / "geo.tsv"
    cross = tmp_path / "cross.tsv"
    geo.write_text(
        "accession\tprimary_role\tquery_families\ttitle\texperiment_type\t"
        "sample_count\tbioproject_id\tpublication_ids\t"
        "shared_publication_flag\tshared_bioproject_flag\tsource_uri\n"
        "GSE25101\tdirect_disease_candidate\taxspa_direct\told\t"
        "Expression profiling by array\t10\t\t\tFalse\tFalse\tu1\n"
        "GSE99999\tdirect_disease_candidate\taxspa_direct\tnew\t"
        "Expression profiling by array\t20\t\t\tFalse\tFalse\tu2\n",
        encoding="utf-8",
    )
    cross.write_text(
        "source\taccession\ttitle\tdisease_signal\tassay\t"
        "sample_or_run_count\tbioproject_id\tpublication_ids\t"
        "overlap_status\tsource_uri\n",
        encoding="utf-8",
    )

    result = StudyQuarantineBuilder().build(
        geo_catalog_path=geo,
        cross_repository_path=cross,
        output_root=tmp_path / "out",
    )

    with result.queue_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    assert [row["accession"] for row in rows] == ["GSE99999"]
    assert rows[0]["quarantine_status"] == "manual_review_required"
