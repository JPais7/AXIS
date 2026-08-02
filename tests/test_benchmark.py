from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from axis.analysis.benchmark import DemoBenchmarker


def test_demo_benchmark_writes_auditable_runs(tmp_path: Path) -> None:
    result = DemoBenchmarker().run(
        repetitions=3,
        warmups=1,
        workspace=tmp_path,
    )

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    with result.runs_path.open(encoding="utf-8", newline="") as handle:
        runs = list(csv.DictReader(handle, delimiter="\t"))

    assert result.repetitions == 3
    assert result.warmups == 1
    assert report["status"] == "passed"
    assert report["synthetic"] is True
    assert report["offline_during_timed_runs"] is True
    assert report["method"]["repetitions"] == 3
    assert report["checks"]["all_runs_passed"] is True
    assert report["elapsed_seconds"]["minimum"] > 0
    assert report["peak_traced_memory_bytes"]["maximum"] > 0
    assert len(runs) == 3
    assert {row["passed"] for row in runs} == {"9"}
    assert all(int(row["output_bytes"]) > 0 for row in runs)


@pytest.mark.parametrize(
    ("repetitions", "warmups", "message"),
    [
        (0, 1, "repetitions"),
        (1, -1, "warmups"),
    ],
)
def test_demo_benchmark_rejects_invalid_run_counts(
    tmp_path: Path,
    repetitions: int,
    warmups: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DemoBenchmarker().run(
            repetitions=repetitions,
            warmups=warmups,
            workspace=tmp_path,
        )
