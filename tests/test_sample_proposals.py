import csv
import json
from pathlib import Path

from axis.analysis import ProposedSampleSheetBuilder


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_proposals_exclude_related_disease_and_non_expression(tmp_path: Path) -> None:
    queue = tmp_path / "queue.tsv"
    samples = tmp_path / "samples.tsv"
    catalog = tmp_path / "catalog.tsv"
    _write(
        queue,
        ["accession"],
        [{"accession": "GSE1"}, {"accession": "GSE2"}],
    )
    sample_rows = [
        {
            "study_accession": accession,
            "sample_accession": f"GSM{index}",
            "suggested_group": "case" if index == 1 else "control",
            "treatment_signal": "unknown",
            "subject_identifier": "",
            "title": ("PsA patient 1" if index == 1 else "Healthy 1"),
            "source": "CD4 T cell",
            "characteristics": "disease: psoriatic arthritis",
        }
        for accession in ("GSE1", "GSE2")
        for index in (1, 2)
    ]
    _write(samples, list(sample_rows[0]), sample_rows)
    catalog_rows = [
        {
            "accession": "GSE1",
            "title": "Primary T cells [RNA-seq]",
            "summary": "Psoriatic arthritis and healthy controls.",
            "publication_ids": "PMID:1",
            "bioproject_id": "PRJNA1",
            "shared_publication_flag": "True",
            "shared_bioproject_flag": "True",
        },
        {
            "accession": "GSE2",
            "title": "Primary T cells [Hi-C]",
            "summary": "Psoriatic arthritis and healthy controls.",
            "publication_ids": "PMID:1",
            "bioproject_id": "PRJNA1",
            "shared_publication_flag": "True",
            "shared_bioproject_flag": "True",
        },
    ]
    _write(catalog, list(catalog_rows[0]), catalog_rows)

    result = ProposedSampleSheetBuilder().build(
        design_queue_path=queue,
        sample_metadata_path=samples,
        catalog_path=catalog,
        output_root=tmp_path / "out",
    )

    assert result.related_disease_exclusions == 1
    assert result.non_expression_exclusions == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        validations = {
            row["accession"]: row for row in csv.DictReader(source, delimiter="\t")
        }
    assert validations["GSE1"]["validation_status"] == "related_disease_context_only"
    assert validations["GSE2"]["validation_status"] == "non_expression_context_only"
    assert (
        validations["GSE1"]["evidence_cluster"]
        == validations["GSE2"]["evidence_cluster"]
    )
    assert validations["GSE1"]["independence_status"] == "shared_source_cluster"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["automatic_eligibility"] is False
