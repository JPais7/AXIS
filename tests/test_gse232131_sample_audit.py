import csv
import gzip
import json
from pathlib import Path

from axis.analysis import Gse232131SampleAuditor


def test_audit_detects_absent_controls_and_pooled_donors(
    tmp_path: Path,
) -> None:
    matrix = tmp_path / "matrix.txt.gz"
    with gzip.open(matrix, "wt", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(["!Sample_geo_accession", "GSM1", "GSM2"])
        writer.writerow(
            [
                "!Sample_title",
                "PBMCs_Unsti_AS1802",
                "PBMCs_LPS_AS2311_AS1830",
            ]
        )
        writer.writerow(
            [
                "!Sample_relation",
                "BioSample: https://example/SAMN1",
                "BioSample: https://example/SAMN2",
            ]
        )
        writer.writerow(
            [
                "!Sample_relation",
                "SRA: https://example/SRX1",
                "SRA: https://example/SRX2",
            ]
        )
        writer.writerow(
            [
                "!Sample_supplementary_file_1",
                "ftp://example/GSM1_matrix.tar.gz",
                "ftp://example/GSM2_matrix.tar.gz",
            ]
        )

    result = Gse232131SampleAuditor().audit(
        matrix_path=matrix,
        output_root=tmp_path / "out",
    )
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    with result.sample_sheet_path.open(
        encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source, delimiter="\t"))

    assert result.donors == 3
    assert audit["diagnostic_groups"]["healthy_control"] == 0
    assert rows[1]["pooled_donors"] == "True"
    assert rows[1]["donor_level_pseudobulk_eligible"] == "False"
    assert result.decision.startswith("mechanistic_only_")
