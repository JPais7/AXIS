import csv
import json
from pathlib import Path

from axis.analysis import TargetMetaAnalyzer


def _study(path: Path, effect: float, p_value: float) -> None:
    path.mkdir()
    (path / "differential-analysis.json").write_text(
        json.dumps(
            {
                "method": {"residual_degrees_of_freedom": 20},
                "case_samples": 12,
                "control_samples": 10,
            }
        ),
        encoding="utf-8",
    )
    (path / "gene-level-results.tsv").write_text(
        "gene_symbol\tmedian_mean_difference\n"
        f"DDX24\t{effect}\nADA\t{effect / 2}\n",
        encoding="utf-8",
    )
    with (path / "differential-expression.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ("probe_id", "gene_symbols", "mean_difference", "p_value")
        )
        writer.writerow(("p1", "DDX24", effect, p_value))
        writer.writerow(("p2", "ADA", effect / 2, p_value))


def test_target_meta_analysis_pools_and_leaves_each_study_out(
    tmp_path: Path,
) -> None:
    studies = {}
    for number, effect in enumerate((-0.5, -0.4, -0.3), 1):
        path = tmp_path / f"S{number}"
        _study(path, effect, 0.01)
        studies[f"S{number}"] = path

    result = TargetMetaAnalyzer().analyze(
        studies=studies,
        output_root=tmp_path / "out",
    )

    with result.summary_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    with result.leave_one_out_path.open(
        encoding="utf-8", newline=""
    ) as source:
        sensitivity = list(csv.DictReader(source, delimiter="\t"))
    assert len(rows) == 2
    assert float(rows[0]["pooled_effect"]) < 0
    assert len(sensitivity) == 6
    assert len(result.figure_paths) == 2
    assert all(path.exists() for path in result.figure_paths)
