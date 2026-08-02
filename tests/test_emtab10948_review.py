import csv
import json
from pathlib import Path

from axis.analysis import Emtab10948Reviewer


def test_emtab10948_is_paired_tissue_not_case_control(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({"accession": "E-MTAB-10948"}),
        encoding="utf-8",
    )
    header = [
        "Source Name",
        "Comment[ENA_SAMPLE]",
        "Comment[BioSD_SAMPLE]",
        "Characteristics[organism]",
        "Characteristics[individual]",
        "Characteristics[sex]",
        "Characteristics[age]",
        "Unit[time unit]",
        "Characteristics[developmental stage]",
        "Characteristics[disease]",
        "Characteristics[organism part]",
        "Characteristics[cell type]",
        "Characteristics[immunophenotype]",
        "Characteristics[clinical information]",
    ]
    sdrf = tmp_path / "study.sdrf.txt"
    with sdrf.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        for donor in ("AS01", "AS02"):
            for source, tissue in (
                (f"{donor}_PB", "blood"),
                (f"{donor}_SF", "synoval fluid"),
            ):
                writer.writerow(
                    [
                        source,
                        "ERS1",
                        "SAMEA1",
                        "Homo sapiens",
                        donor,
                        "female",
                        "41",
                        "year",
                        "adult",
                        "ankylosing spondylitis",
                        tissue,
                        "mononuclear cell",
                        "CD3-positive; CD25-positive",
                        "active knee arthritis",
                        "E-MTAB-10948.processed.1.zip",
                        "E-MTAB-10948.processed.2.zip",
                        "E-MTAB-10948.processed.3.zip",
                    ]
                )

    result = Emtab10948Reviewer().review(
        study_audit_path=audit,
        sdrf_path=sdrf,
        output_root=tmp_path / "out",
    )
    review = json.loads(result.review_path.read_text(encoding="utf-8"))

    assert result.participants == 2
    assert result.biological_samples == 4
    assert review["participants"]["healthy_controls"] == 0
    assert review["automatic_eligibility"] is False
    assert result.decision == "mechanistic_paired_tissue_only"
