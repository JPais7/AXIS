"""Compare completed probe-level outputs without treating either as truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent


def read_results(path: Path) -> dict[str, tuple[float, float]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        return {
            row["probe_id"]: (
                float(row["mean_difference"]),
                float(row["adjusted_p_value"]),
            )
            for row in rows
        }


axis = read_results(ROOT / "axis/differential-expression.tsv")
manual = read_results(ROOT / "manual/differential-expression.tsv")
limma = read_results(ROOT / "limma-local/differential-expression.tsv")


def top_set(values: dict[str, tuple[float, float]], size: int) -> set[str]:
    return {
        probe
        for probe, _ in sorted(
            values.items(),
            key=lambda item: (item[1][1], item[0]),
        )[:size]
    }


def pairwise(
    left_name: str,
    left: dict[str, tuple[float, float]],
    right_name: str,
    right: dict[str, tuple[float, float]],
) -> dict[str, object]:
    shared = sorted(set(left) & set(right))
    left_effects = np.array([left[probe][0] for probe in shared])
    right_effects = np.array([right[probe][0] for probe in shared])
    left_adjusted = np.array([left[probe][1] for probe in shared])
    right_adjusted = np.array([right[probe][1] for probe in shared])
    return {
        "left": left_name,
        "right": right_name,
        "shared_probes": len(shared),
        "effect_spearman": float(
            spearmanr(left_effects, right_effects).statistic
        ),
        "adjusted_p_spearman": float(
            spearmanr(left_adjusted, right_adjusted).statistic
        ),
        "maximum_absolute_effect_difference": float(
            np.max(np.abs(left_effects - right_effects))
        ),
        "direction_agreement_fraction": float(
            np.mean(np.sign(left_effects) == np.sign(right_effects))
        ),
        "top_100_overlap": len(top_set(left, 100) & top_set(right, 100)),
        "top_500_overlap": len(top_set(left, 500) & top_set(right, 500)),
    }


report = {
    "schema_version": 1,
    "status": "partial",
    "accession": "GSE18781",
    "platform": "GPL570",
    "completed_workflows": ["axis", "manual_statistics", "limma_local"],
    "incomplete_workflows": ["geo2r_server", "expressanalyst"],
    "pairwise": [
        pairwise("axis", axis, "manual_statistics", manual),
        pairwise("axis", axis, "limma_local", limma),
        pairwise("manual_statistics", manual, "limma_local", limma),
    ],
    "interpretation": (
        "Method agreement for one public contrast; neither workflow is truth and "
        "the four-workflow comparison is incomplete."
    ),
}
(ROOT / "comparison-report.json").write_text(
    json.dumps(report, indent=2) + "\n",
    encoding="utf-8",
)
