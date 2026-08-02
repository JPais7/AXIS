import csv
import gzip
import json
from pathlib import Path

from axis.analysis import ExpressionQualityControl


def write_matrix(path: Path, sample_prefix: str, offset: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "ID_REF",
                f"{sample_prefix}1",
                f"{sample_prefix}2",
                f"{sample_prefix}3",
            )
        )
        for feature in range(20):
            base = feature * 0.2 + offset
            writer.writerow(
                (
                    f"probe{feature}",
                    base,
                    base + 0.1 + feature * 0.001,
                    base - 0.1 - feature * 0.002,
                )
            )


def test_qc_writes_metrics_and_three_nonempty_plots(tmp_path: Path) -> None:
    directory = tmp_path / "GSE1" / "prepared" / "matrix"
    write_matrix(directory / "case-matrix.tsv.gz", "case", 0.3)
    write_matrix(directory / "control-matrix.tsv.gz", "control", 0.0)

    result = ExpressionQualityControl().run(
        "GSE1",
        data_root=tmp_path,
        max_features=10,
    )[0]

    assert result.samples == 6
    assert result.features == 20
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["case_samples"] == 3
    assert report["control_samples"] == 3
    assert report["pca_features"] == 10
    assert len(report["explained_variance_ratio"]) >= 2
    assert len(report["group_associations"]) == 5
    for path in (
        result.distribution_plot,
        result.pca_plot,
        result.correlation_plot,
    ):
        assert path.read_bytes().startswith(b"\x89PNG")
        assert path.stat().st_size > 1000
