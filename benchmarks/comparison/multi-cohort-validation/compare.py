"""Summarize AXIS versus native limma across frozen bulk cohorts."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import TextIO

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / ".comparison-work"
STUDIES = {
    "GSE18781": ("GPL570", "GSE18781_series_matrix"),
    "GSE25101": ("GPL6947", "GSE25101_series_matrix"),
    "GSE73754": ("GPL10558", "GSE73754_series_matrix"),
    "GSE11886": ("GPL570", "GSE11886_series_matrix"),
}


def read_results(path: Path) -> dict[str, tuple[float, float]]:
    def parse(handle: TextIO) -> dict[str, tuple[float, float]]:
        rows = csv.DictReader(handle, delimiter="\t")
        return {
            row["probe_id"]: (
                float(row["mean_difference"]),
                float(row["adjusted_p_value"]),
            )
            for row in rows
        }

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            return parse(handle)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return parse(handle)


def top_set(values: dict[str, tuple[float, float]], size: int) -> set[str]:
    ordered = sorted(values.items(), key=lambda item: (item[1][1], item[0]))
    return {probe for probe, _ in ordered[:size]}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


rows: list[dict[str, object]] = []
for accession, (platform, _matrix) in STUDIES.items():
    if accession == "GSE18781":
        prior = (
            ROOT
            / "benchmarks/comparison/v2-run-ai-2026-08-02"
        )
        axis_path = prior / "axis/differential-expression.tsv"
        limma_path = prior / "limma-local/differential-expression.tsv"
    else:
        axis_path = WORK / accession / "axis-results.tsv.gz"
        limma_path = WORK / accession / "limma-results.tsv.gz"
    axis = read_results(axis_path)
    limma = read_results(limma_path)
    shared = sorted(set(axis) & set(limma))
    axis_effect = np.array([axis[probe][0] for probe in shared])
    limma_effect = np.array([limma[probe][0] for probe in shared])
    axis_adjusted = np.array([axis[probe][1] for probe in shared])
    limma_adjusted = np.array([limma[probe][1] for probe in shared])
    rows.append(
        {
            "accession": accession,
            "platform": platform,
            "shared_probes": len(shared),
            "effect_spearman": float(
                spearmanr(axis_effect, limma_effect).statistic
            ),
            "adjusted_p_spearman": float(
                spearmanr(axis_adjusted, limma_adjusted).statistic
            ),
            "maximum_absolute_effect_difference": float(
                np.max(np.abs(axis_effect - limma_effect))
            ),
            "direction_agreement_fraction": float(
                np.mean(np.sign(axis_effect) == np.sign(limma_effect))
            ),
            "top_100_overlap": len(top_set(axis, 100) & top_set(limma, 100)),
            "top_500_overlap": len(top_set(axis, 500) & top_set(limma, 500)),
            "axis_sha256": sha256(axis_path),
            "limma_sha256": sha256(limma_path),
        }
    )

adjusted_axis_path = (
    ROOT
    / "data/geo/GSE73754/prepared/GSE73754_series_matrix"
    / "differential-expression.tsv"
)
adjusted_limma_path = (
    WORK / "GSE73754-adjusted/limma-adjusted-results.tsv.gz"
)
adjusted_axis = read_results(adjusted_axis_path)
adjusted_limma = read_results(adjusted_limma_path)
adjusted_shared = sorted(set(adjusted_axis) & set(adjusted_limma))
adjusted_axis_effect = np.array(
    [adjusted_axis[probe][0] for probe in adjusted_shared]
)
adjusted_limma_effect = np.array(
    [adjusted_limma[probe][0] for probe in adjusted_shared]
)
adjusted_axis_p = np.array(
    [adjusted_axis[probe][1] for probe in adjusted_shared]
)
adjusted_limma_p = np.array(
    [adjusted_limma[probe][1] for probe in adjusted_shared]
)
adjusted_row: dict[str, object] = {
    "accession": "GSE73754",
    "platform": "GPL10558",
    "model": "group + sex + age + numeric batch",
    "shared_probes": len(adjusted_shared),
    "effect_spearman": float(
        spearmanr(adjusted_axis_effect, adjusted_limma_effect).statistic
    ),
    "adjusted_p_spearman": float(
        spearmanr(adjusted_axis_p, adjusted_limma_p).statistic
    ),
    "maximum_absolute_effect_difference": float(
        np.max(np.abs(adjusted_axis_effect - adjusted_limma_effect))
    ),
    "direction_agreement_fraction": float(
        np.mean(np.sign(adjusted_axis_effect) == np.sign(adjusted_limma_effect))
    ),
    "top_100_overlap": len(
        top_set(adjusted_axis, 100) & top_set(adjusted_limma, 100)
    ),
    "top_500_overlap": len(
        top_set(adjusted_axis, 500) & top_set(adjusted_limma, 500)
    ),
    "axis_sha256": sha256(adjusted_axis_path),
    "limma_sha256": sha256(adjusted_limma_path),
}

output = Path(__file__).resolve().parent
with (output / "validation-summary.tsv").open(
    "w", encoding="utf-8", newline=""
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=tuple(rows[0]),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
with (output / "adjusted-validation.tsv").open(
    "w", encoding="utf-8", newline=""
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=tuple(adjusted_row),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(adjusted_row)
(output / "validation-report.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "complete",
            "comparison": "AXIS moderated model versus native limma",
            "primary_model": "unadjusted case-control",
            "studies": rows,
            "adjusted_model": adjusted_row,
            "claim_limit": (
                "Technical agreement only; no workflow is biological truth."
            ),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
