import csv
import json
from pathlib import Path

from axis.analysis import CohortSelectionBuilder


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_selection_applies_disease_independence_and_prior_use_gates(
    tmp_path: Path,
) -> None:
    validation = tmp_path / "validation.tsv"
    samples = tmp_path / "samples.tsv"
    catalog = tmp_path / "catalog.tsv"
    geo = tmp_path / "geo"
    validations = [
        {
            "accession": accession,
            "validation_status": "axspa_design_review_candidate",
            "evidence_cluster": cluster,
            "cluster_members": accession,
            "independence_status": independence,
        }
        for accession, cluster, independence in (
            ("GSE1", "cluster:new", "shared_source_cluster"),
            ("GSE2", "cluster:new", "shared_source_cluster"),
            ("GSE3", "accession:GSE3", "no_catalog_overlap_detected"),
            ("GSE4", "accession:GSE4", "no_catalog_overlap_detected"),
        )
    ]
    _write(validation, validations)
    sample_rows: list[dict[str, str]] = []
    for accession in ("GSE1", "GSE2", "GSE3", "GSE4"):
        disease = "rheumatoid arthritis" if accession == "GSE3" else "axSpA"
        for index in range(3):
            sample_rows.append(
                {
                    "study_accession": accession,
                    "suggested_group": "case",
                    "title": f"{disease} patient {index}",
                    "characteristics": f"disease: {disease}",
                    "treatment_signal": "unknown",
                }
            )
            sample_rows.append(
                {
                    "study_accession": accession,
                    "suggested_group": "control",
                    "title": f"healthy control {index}",
                    "characteristics": "disease: healthy",
                    "treatment_signal": "unknown",
                }
            )
    _write(samples, sample_rows)
    catalog_rows = [
        {
            "accession": accession,
            "title": "Peripheral blood RNA-seq",
            "summary": "Whole blood case control expression.",
            "experiment_type": "Expression profiling by high throughput sequencing",
        }
        for accession in ("GSE1", "GSE2", "GSE3", "GSE4")
    ]
    _write(catalog, catalog_rows)
    analyzed = geo / "GSE4" / "prepared"
    analyzed.mkdir(parents=True)
    (analyzed / "gene-level-results.tsv").write_text("gene\n", encoding="utf-8")

    result = CohortSelectionBuilder().build(
        validation_path=validation,
        sample_metadata_path=samples,
        catalog_path=catalog,
        geo_root=geo,
        output_root=tmp_path / "out",
        maximum=5,
    )

    assert result.selected == 1
    with result.selection_path.open(encoding="utf-8", newline="") as source:
        selected = list(csv.DictReader(source, delimiter="\t"))
    assert selected[0]["accession"] in {"GSE1", "GSE2"}
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["automatic_eligibility"] is False
