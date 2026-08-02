import csv
import json
from pathlib import Path

from axis.ingestion import CatalogTriageBuilder

FIELDS = [
    "accession",
    "primary_role",
    "title",
    "summary",
    "organisms",
    "experiment_type",
    "sample_count",
    "shared_publication_flag",
    "shared_bioproject_flag",
    "eligibility_status",
    "estimated_download_class",
]


def _write_catalog(path: Path) -> None:
    rows = [
        {
            "accession": "GSE1",
            "primary_role": "direct_disease_candidate",
            "title": "RNA-seq of untreated ankylosing spondylitis patients",
            "summary": "PBMC from patients and healthy controls.",
            "organisms": "Homo sapiens",
            "experiment_type": "Expression profiling by high throughput sequencing",
            "sample_count": "24",
            "shared_publication_flag": "False",
            "shared_bioproject_flag": "False",
            "eligibility_status": "metadata_review_candidate",
            "estimated_download_class": "large",
        },
        {
            "accession": "GSE2",
            "primary_role": "direct_disease_candidate",
            "title": "HLA-B27 cell line experiment",
            "summary": "In vitro stimulation of a cell line.",
            "organisms": "Homo sapiens",
            "experiment_type": "Expression profiling by array",
            "sample_count": "8",
            "shared_publication_flag": "False",
            "shared_bioproject_flag": "True",
            "eligibility_status": "metadata_review_candidate",
            "estimated_download_class": "small",
        },
        {
            "accession": "GSE3",
            "primary_role": "related_disease_context",
            "title": "Rheumatoid arthritis",
            "summary": "Patients and healthy controls.",
            "organisms": "Homo sapiens",
            "experiment_type": "Expression profiling by array",
            "sample_count": "50",
            "shared_publication_flag": "False",
            "shared_bioproject_flag": "False",
            "eligibility_status": "metadata_review_candidate",
            "estimated_download_class": "small",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_triage_prioritizes_case_control_and_never_approves(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.tsv"
    _write_catalog(catalog)

    result = CatalogTriageBuilder().build(catalog, output_root=tmp_path)

    assert result.candidates == 2
    assert result.high_priority == 1
    with result.output_path.open(encoding="utf-8", newline="") as handle:
        rows = {row["accession"]: row for row in csv.DictReader(handle, delimiter="\t")}
    assert rows["GSE1"]["priority_tier"] == "high"
    assert rows["GSE1"]["tissue_signal"] == "pbmc"
    assert rows["GSE1"]["automatic_eligibility"] == "False"
    assert rows["GSE2"]["priority_tier"] == "manual_review"

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["candidates"] == 2
    assert "verify case and control sample labels" in summary["mandatory_manual_checks"]
