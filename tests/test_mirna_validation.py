import csv
import gzip
import json
from pathlib import Path

from axis.ingestion import MirnaCohortValidator


def test_mirna_validator_cross_checks_metadata_and_matrices(tmp_path: Path) -> None:
    root = tmp_path / "GSE1"
    supplementary = root / "supplementary"
    supplementary.mkdir(parents=True)
    matrix = root / "GSE1_series_matrix.txt.gz"
    with gzip.open(matrix, "wt", encoding="utf-8") as target:
        target.write(
            '!Sample_title\t"B001"\t"B002"\t"B003"\n'
            '!Sample_characteristics_ch1\t"gender: male"\t'
            '"gender: female"\t"gender: male"\n'
            '!Sample_characteristics_ch1\t"age: 30"\t"age: 31"\t"age: 32"\n'
            '!Sample_characteristics_ch1\t"crp: 1"\t"crp: 2"\t"crp: 3"\n'
            '!Sample_characteristics_ch1\t"diagnosis: r-axspa"\t'
            '"diagnosis: nr-axspa"\t"diagnosis: hc"\n'
            "!series_matrix_table_begin\n"
        )
    for suffix, values in (
        ("raw", ("1", "2", "3")),
        ("norm", ("1.1", "2.2", "3.3")),
    ):
        with gzip.open(
            supplementary / f"GSE1_seq_{suffix}.txt.gz",
            "wt",
            encoding="utf-8",
            newline="",
        ) as target:
            writer = csv.writer(target, delimiter="\t")
            writer.writerow(("miRNA", "B001", "B002", "B003"))
            writer.writerow(("hsa-mir-1", *values))

    result = MirnaCohortValidator().validate("GSE1", data_root=tmp_path)

    assert result.participants == 3
    assert result.raw_counts_are_integers
    assert result.empty_raw_libraries == ()
    assert result.normalized_missing_values == 0
    assert result.sample_order_matches
    assert not result.eligible_for_analysis
    sample_rows = list(
        csv.DictReader(result.sample_sheet_path.open(), delimiter="\t")
    )
    assert len(sample_rows) == 3
    assert json.loads(result.report_path.read_text())["mirnas"] == 1
