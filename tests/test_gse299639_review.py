import csv
import gzip
import json
from pathlib import Path

from axis.analysis import Gse299639Reviewer


def _results(path: Path, ddx_effect: float, ada_effect: float) -> None:
    path.write_text(
        "gene_symbol\tmedian_mean_difference\tdirection\tsimes_p_value\t"
        "adjusted_p_value\n"
        f"DDX24\t{ddx_effect}\tlower_in_case\t0.1\t0.5\n"
        f"ADA\t{ada_effect}\tlower_in_case\t0.08\t0.4\n",
        encoding="utf-8",
    )


def test_gse299639_review_freezes_unique_participants_and_holds_use(
    tmp_path: Path,
) -> None:
    abundance = tmp_path / "abundance.tsv.gz"
    with gzip.open(abundance, "wt", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["Gene", *Gse299639Reviewer.EXPECTED_SAMPLES, "Symbol"]
        )
    full = tmp_path / "full.tsv"
    sensitivity = tmp_path / "sensitivity.tsv"
    qc = tmp_path / "qc.json"
    sensitivity_summary = tmp_path / "sensitivity.json"
    _results(full, -0.3, -0.2)
    _results(sensitivity, -0.4, -0.3)
    qc.write_text(
        json.dumps(
            {
                "outlier_samples": ["AS_M1"],
                "minimum_sample_correlation": 0.85,
            }
        ),
        encoding="utf-8",
    )
    sensitivity_summary.write_text(
        json.dumps({"decision": "retain_all"}),
        encoding="utf-8",
    )

    result = Gse299639Reviewer().review(
        abundance_path=abundance,
        full_results_path=full,
        sensitivity_results_path=sensitivity,
        qc_path=qc,
        sensitivity_summary_path=sensitivity_summary,
        output_root=tmp_path / "out",
    )

    with result.sample_sheet_path.open(
        encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    assert result.samples == 12
    assert len({row["participant_id"] for row in rows}) == 12
    assert result.decision.startswith("hold_")
    assert rows[3]["outlier_status"] == "candidate_retain_for_sensitivity"
