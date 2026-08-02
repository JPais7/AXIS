"""Frozen manual-statistics comparator for GSE18781."""

from __future__ import annotations

import csv
import gzip
import json
import platform
import time
import tracemalloc
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import ttest_ind

ROOT = Path(__file__).resolve().parents[4]
PREPARED = ROOT / "data/geo/GSE18781/prepared/GSE18781_series_matrix"
OUTPUT = Path(__file__).resolve().parent


def benjamini_hochberg(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.minimum(adjusted, 1.0)
    return result


started = time.perf_counter()
tracemalloc.start()


def read_matrix(path: Path) -> tuple[list[str], list[str], np.ndarray]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        samples = next(reader)[1:]
        rows = list(reader)
    return samples, [row[0] for row in rows], np.array(
        [[float(value) for value in row[1:]] for row in rows],
        dtype=float,
    )


case_samples, probes, case_values = read_matrix(PREPARED / "case-matrix.tsv.gz")
control_samples, control_probes, control_values = read_matrix(
    PREPARED / "control-matrix.tsv.gz"
)
if probes != control_probes:
    raise ValueError("case and control features are not aligned")

test = ttest_ind(case_values, control_values, axis=1, equal_var=False)
p_values = np.nan_to_num(test.pvalue, nan=1.0)
effects = case_values.mean(axis=1) - control_values.mean(axis=1)
directions = np.where(
    effects > 0,
    "higher_in_case",
    np.where(effects < 0, "lower_in_case", "no_difference"),
)
adjusted = benjamini_hochberg(p_values)
with (OUTPUT / "differential-expression.tsv").open(
    "w", encoding="utf-8", newline=""
) as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "probe_id",
            "case_mean",
            "control_mean",
            "mean_difference",
            "direction",
            "p_value",
            "adjusted_p_value",
        )
    )
    writer.writerows(
        zip(
            probes,
            case_values.mean(axis=1),
            control_values.mean(axis=1),
            effects,
            directions,
            p_values,
            adjusted,
            strict=True,
        )
    )
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
elapsed = time.perf_counter() - started
(OUTPUT / "methods.json").write_text(
    json.dumps(
        {
            "accession": "GSE18781",
            "platform": "GPL570",
            "contrast": "case minus control",
            "case_samples": len(case_samples),
            "control_samples": len(control_samples),
            "test": "two-sided Welch t-test per probe",
            "multiple_testing": "Benjamini-Hochberg across all probes",
            "elapsed_seconds": elapsed,
            "peak_python_traced_bytes": peak,
            "python": platform.python_version(),
            "scipy": scipy.__version__,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
