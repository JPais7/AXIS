import csv
import gzip
from pathlib import Path
from types import SimpleNamespace

import axis.analysis.mirna as mirna_module
from axis.analysis import MirnaDifferentialAnalyzer


def test_mirna_analysis_writes_three_adjusted_comparisons(
    tmp_path: Path, monkeypatch: object
) -> None:
    root = tmp_path / "GSE1"
    supplementary = root / "supplementary"
    validation_root = root / "mirna-validation"
    supplementary.mkdir(parents=True)
    validation_root.mkdir()
    diagnoses = ["r-axspa"] * 4 + ["nr-axspa"] * 4 + ["hc"] * 4
    samples = [f"B{index:03d}" for index in range(1, 13)]
    sample_sheet = validation_root / "sample-sheet.tsv"
    with sample_sheet.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t")
        writer.writerow(("participant_id", "diagnosis", "group", "sex", "age", "crp"))
        for index, (sample, diagnosis) in enumerate(
            zip(samples, diagnoses, strict=True)
        ):
            writer.writerow(
                (
                    sample,
                    diagnosis,
                    "control" if diagnosis == "hc" else "case",
                    "male" if index % 2 else "female",
                    20 + index,
                    1 + (index % 3),
                )
            )
    counts = supplementary / "GSE1_seq_raw.txt.gz"
    with gzip.open(counts, "wt", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t")
        writer.writerow(("miRNA", *samples))
        for feature in range(20):
            writer.writerow(
                (
                    f"hsa-mir-{feature}",
                    *[
                        100
                        + feature
                        + index
                        + (500 if feature == 0 and index < 8 else 0)
                        for index in range(12)
                    ],
                )
            )

    class FakeValidator:
        def validate(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(
                eligible_for_analysis=True,
                sample_sheet_path=sample_sheet,
            )

    monkeypatch.setattr(  # type: ignore[attr-defined]
        mirna_module, "MirnaCohortValidator", FakeValidator
    )
    result = MirnaDifferentialAnalyzer().analyze(
        "GSE1", data_root=tmp_path, min_base_mean=0
    )

    assert result.participants == 12
    assert len(result.comparisons) == 9
    assert all(comparison.results_path.exists() for comparison in result.comparisons)
    assert result.sensitivity_path.exists()
    assert result.summary_path.exists()
