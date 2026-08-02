import csv
from pathlib import Path

from axis.analysis import TargetStabilityAnalyzer


def test_target_stability_uses_donors_and_retains_direction(tmp_path: Path) -> None:
    pseudobulk = tmp_path / "pseudobulk.tsv"
    with pseudobulk.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "subject",
                "status",
                "cell_type",
                "gene_symbol",
                "cells",
                "log2_cpm",
            ),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for index, value in enumerate((2.0, 2.1, 2.2, 2.3), start=1):
            writer.writerow(
                {
                    "subject": f"A{index}",
                    "status": "AXI",
                    "cell_type": "CD4 TCM",
                    "gene_symbol": "EWSR1",
                    "cells": 100,
                    "log2_cpm": value,
                }
            )
        for index, value in enumerate((4.0, 4.1, 4.2, 4.3), start=1):
            writer.writerow(
                {
                    "subject": f"H{index}",
                    "status": "Healthy",
                    "cell_type": "CD4 TCM",
                    "gene_symbol": "EWSR1",
                    "cells": 100,
                    "log2_cpm": value,
                }
            )

    result = TargetStabilityAnalyzer().analyze(
        pseudobulk,
        gene="EWSR1",
        bootstrap_iterations=500,
        output_root=tmp_path / "out",
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert float(row["log2_cpm_difference"]) < 0
    assert row["leave_one_out_direction_consistency"] == "1.0"
    assert row["stable"] == "True"
    assert result.stable_comparisons == 1
