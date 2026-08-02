import csv
from pathlib import Path

from axis.ingestion import ParticipantExpansionBuilder


def test_participant_expansion_collapses_cell_subtypes(tmp_path: Path) -> None:
    samples = tmp_path / "samples.tsv"
    fields = (
        "study_accession",
        "sample_accession",
        "suggested_group",
        "treatment_signal",
        "subject_identifier",
        "title",
        "characteristics",
    )
    with samples.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for suffix in ("Mk", "Mn", "Mp"):
            writer.writerow(
                {
                    "study_accession": "GSE1",
                    "sample_accession": f"GSM1{suffix}",
                    "suggested_group": "case",
                    "treatment_signal": "unknown",
                    "subject_identifier": "",
                    "title": f"OS001_{suffix}",
                    "characteristics": (
                        "disease state: Axial SpA Patient | "
                        f"cell type: {suffix} Monocytes"
                    ),
                }
            )
        writer.writerow(
            {
                "study_accession": "GSE1",
                "sample_accession": "GSM2",
                "suggested_group": "control",
                "treatment_signal": "unknown",
                "subject_identifier": "",
                "title": "GK001_Mk",
                "characteristics": "disease state: Healthy Control",
            }
        )
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "accession\texperiment_type\n"
        "GSE1\tExpression profiling by RT-PCR\n",
        encoding="utf-8",
    )

    result = ParticipantExpansionBuilder().build(
        samples, catalog, output_root=tmp_path / "out"
    )

    with result.cohort_path.open(encoding="utf-8", newline="") as source:
        cohort = next(csv.DictReader(source, delimiter="\t"))
    assert cohort["participants"] == "2"
    assert cohort["axial_spa_participants"] == "1"
    assert cohort["healthy_control_participants"] == "1"
    assert cohort["repeated_sample_rows"] == "2"


def test_participant_expansion_resolves_pooled_title_ids(tmp_path: Path) -> None:
    samples = tmp_path / "samples.tsv"
    samples.write_text(
        "study_accession\tsample_accession\tsuggested_group\t"
        "treatment_signal\tsubject_identifier\ttitle\tcharacteristics\n"
        "GSE2\tGSM1\tunassigned\tunknown\t\t"
        "PBMC KAS01_KAS02_KAS03\t"
        "tissue: PBMC | disease: ankylosing spondylitis\n",
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "accession\texperiment_type\n"
        "GSE2\tExpression profiling by high throughput sequencing\n",
        encoding="utf-8",
    )

    result = ParticipantExpansionBuilder().build(
        samples, catalog, output_root=tmp_path / "out"
    )

    with result.cohort_path.open(encoding="utf-8", newline="") as source:
        cohort = next(csv.DictReader(source, delimiter="\t"))
    assert cohort["participants"] == "3"
    assert cohort["ankylosing_spondylitis_participants"] == "3"


def test_participant_expansion_recognizes_hc_and_b_ids(
    tmp_path: Path,
) -> None:
    samples = tmp_path / "samples.tsv"
    samples.write_text(
        "study_accession\tsample_accession\tsuggested_group\t"
        "treatment_signal\tsubject_identifier\ttitle\tcharacteristics\n"
        "GSE252708\tGSM1\tunassigned\tunknown\t\tB001\t"
        "diagnosis: hc\n"
        "GSE252708\tGSM2\tcase\tunknown\t\tB002\t"
        "diagnosis: r-axspa\n",
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "accession\texperiment_type\n"
        "GSE252708\t"
        "Non-coding RNA profiling by high throughput sequencing\n",
        encoding="utf-8",
    )

    result = ParticipantExpansionBuilder().build(
        samples, catalog, output_root=tmp_path / "out"
    )

    with result.cohort_path.open(encoding="utf-8", newline="") as source:
        cohort = next(csv.DictReader(source, delimiter="\t"))
    assert cohort["participants"] == "2"
    assert cohort["axial_spa_participants"] == "1"
    assert cohort["healthy_control_participants"] == "1"
