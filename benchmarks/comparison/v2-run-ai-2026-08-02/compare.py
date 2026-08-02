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
shared = sorted(set(axis) & set(manual))
axis_effects = np.array([axis[probe][0] for probe in shared])
manual_effects = np.array([manual[probe][0] for probe in shared])


def top_set(values: dict[str, tuple[float, float]], size: int) -> set[str]:
    return {
        probe
        for probe, _ in sorted(
            values.items(),
            key=lambda item: (item[1][1], item[0]),
        )[:size]
    }


report = {
    "schema_version": 1,
    "status": "partial",
    "accession": "GSE18781",
    "platform": "GPL570",
    "completed_workflows": ["axis", "manual_statistics"],
    "incomplete_workflows": ["geo2r", "expressanalyst"],
    "shared_probes": len(shared),
    "effect_spearman": float(spearmanr(axis_effects, manual_effects).statistic),
    "direction_agreement_fraction": float(
        np.mean(np.sign(axis_effects) == np.sign(manual_effects))
    ),
    "top_100_overlap": len(top_set(axis, 100) & top_set(manual, 100)),
    "top_500_overlap": len(top_set(axis, 500) & top_set(manual, 500)),
    "interpretation": (
        "Method agreement for one public contrast; neither workflow is truth and "
        "the four-workflow comparison is incomplete."
    ),
}
(ROOT / "comparison-report.json").write_text(
    json.dumps(report, indent=2) + "\n",
    encoding="utf-8",
)
