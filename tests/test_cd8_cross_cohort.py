import csv
from pathlib import Path

from axis.analysis import Cd8CrossCohortAnalyzer


def _write(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def test_cd8_cross_cohort_preserves_direction_and_donor_unit(tmp_path: Path) -> None:
    gse194315 = tmp_path / "adjusted.tsv"
    gse288581 = tmp_path / "external.tsv"
    _write(
        gse194315,
        (
            "gene_symbol",
            "cell_type",
            "case_subjects",
            "control_subjects",
            "adjusted_log2_cpm_difference",
            "standard_error",
            "p_value",
        ),
        [
            ("DDX24", "CD8 TEM", 10, 29, -0.3, 0.1, 0.01),
            ("ADA", "CD8 TEM", 10, 29, 0.2, 0.2, 0.3),
            ("DDX24", "CD8 Naive", 10, 24, -0.4, 0.1, 0.001),
            ("ADA", "CD8 Naive", 10, 24, 0.1, 0.2, 0.6),
        ],
    )
    _write(
        gse288581,
        (
            "gene_symbol",
            "case_donors",
            "control_donors",
            "log2_cpm_difference",
            "welch_statistic",
            "p_value",
        ),
        [
            ("DDX24", 4, 4, -0.1, -1.5, 0.2),
            ("ADA", 4, 4, 0.3, 1.0, 0.4),
        ],
    )

    result = Cd8CrossCohortAnalyzer().analyze(
        gse194315_path=gse194315,
        gse288581_path=gse288581,
        output_root=tmp_path / "out",
    )

    rows = list(
        csv.DictReader(result.summary_path.open(encoding="utf-8"), delimiter="\t")
    )
    ddx24 = next(row for row in rows if row["gene_symbol"] == "DDX24")
    assert ddx24["direction"] == "lower_in_case"
    assert ddx24["directionally_concordant"] == "True"
    assert ddx24["case_donors"] == "14"
