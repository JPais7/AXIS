"""Measure the small packaged AXIS demonstration without network access."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

from axis.analysis.demo import AxisDemoRunner


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/results/local-demo.json")
    )
    arguments = parser.parse_args()
    if arguments.repetitions < 1:
        raise ValueError("repetitions must be at least one")

    root = arguments.workspace.resolve()
    run_root = root / ".benchmark-run"
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    timings: list[float] = []
    peaks: list[int] = []
    check_counts: list[int] = []
    output_sizes: list[int] = []
    try:
        for index in range(arguments.repetitions):
            destination = run_root / f"run-{index + 1}"
            tracemalloc.start()
            start = time.perf_counter()
            result = AxisDemoRunner().run(
                workspace=root,
                output_root=destination,
            )
            elapsed = time.perf_counter() - start
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            timings.append(elapsed)
            peaks.append(peak)
            check_counts.append(result.passed)
            output_sizes.append(directory_bytes(destination))
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

    payload = {
        "schema_version": 1,
        "benchmark": "axis_synthetic_demo",
        "created_at": datetime.now(UTC).isoformat(),
        "offline": True,
        "synthetic": True,
        "repetitions": arguments.repetitions,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "wall_seconds": {
            "median": statistics.median(timings),
            "minimum": min(timings),
            "maximum": max(timings),
            "all": timings,
        },
        "python_allocation_peak_bytes": {
            "measurement": "tracemalloc; excludes non-Python native allocations",
            "median": statistics.median(peaks),
            "maximum": max(peaks),
            "all": peaks,
        },
        "output_bytes": {
            "median": statistics.median(output_sizes),
            "all": output_sizes,
        },
        "checks": {
            "expected_per_run": 9,
            "passed_per_run": check_counts,
            "all_runs_passed": all(value == 9 for value in check_counts),
        },
        "interpretation": (
            "Installation-scale performance only; no biological claim and no "
            "cross-tool superiority claim."
        ),
    }
    output = arguments.output
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
