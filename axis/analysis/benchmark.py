"""Reproducible performance benchmark for the synthetic AXIS demonstration."""

from __future__ import annotations

import csv
import json
import platform
import statistics
import sys
import tempfile
import time
import tomllib
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from axis.analysis.demo import AxisDemoRunner


@dataclass(frozen=True)
class BenchmarkObservation:
    run: int
    elapsed_seconds: float
    peak_traced_memory_bytes: int
    output_bytes: int
    checks: int
    passed: int


@dataclass(frozen=True)
class DemoBenchmarkRun:
    repetitions: int
    warmups: int
    report_path: Path
    runs_path: Path


class DemoBenchmarker:
    """Measure deterministic demo execution without biomedical data."""

    def run(
        self,
        *,
        repetitions: int = 10,
        warmups: int = 1,
        workspace: str | Path = Path("."),
        manifest_path: str | Path = Path("examples/demo/manifest.json"),
        output_root: str | Path = Path("benchmark-output"),
    ) -> DemoBenchmarkRun:
        if repetitions < 1:
            raise ValueError("benchmark repetitions must be at least one")
        if warmups < 0:
            raise ValueError("benchmark warmups cannot be negative")

        root = Path(workspace).resolve()
        output = Path(output_root)
        if not output.is_absolute():
            output = root / output
        output.mkdir(parents=True, exist_ok=True)

        runner = AxisDemoRunner()
        with tempfile.TemporaryDirectory(prefix="axis-benchmark-warmup-") as temporary:
            temporary_root = Path(temporary)
            for index in range(warmups):
                runner.run(
                    workspace=root,
                    manifest_path=manifest_path,
                    output_root=temporary_root / f"run-{index + 1:03d}",
                )

        observations: list[BenchmarkObservation] = []
        runs_root = output / "runs"
        for index in range(1, repetitions + 1):
            run_output = runs_root / f"run-{index:03d}"
            tracemalloc.start()
            started = time.perf_counter()
            try:
                result = runner.run(
                    workspace=root,
                    manifest_path=manifest_path,
                    output_root=run_output,
                )
                elapsed = time.perf_counter() - started
                _, peak_memory = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            observations.append(
                BenchmarkObservation(
                    run=index,
                    elapsed_seconds=elapsed,
                    peak_traced_memory_bytes=peak_memory,
                    output_bytes=sum(
                        path.stat().st_size
                        for path in run_output.rglob("*")
                        if path.is_file()
                    ),
                    checks=result.checks,
                    passed=result.passed,
                )
            )

        runs_path = output / "benchmark-runs.tsv"
        with runs_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=tuple(asdict(observations[0]).keys()),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(asdict(item) for item in observations)

        elapsed_values = [item.elapsed_seconds for item in observations]
        memory_values = [item.peak_traced_memory_bytes for item in observations]
        output_values = [item.output_bytes for item in observations]
        report_path = output / "benchmark-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "benchmark": "synthetic-demo",
                    "status": "passed",
                    "synthetic": True,
                    "offline_during_timed_runs": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "axis_version": self._axis_version(root),
                    "runtime": {
                        "python": sys.version.split()[0],
                        "platform": platform.platform(),
                        "processor": platform.processor() or "not_reported",
                    },
                    "method": {
                        "repetitions": repetitions,
                        "warmups": warmups,
                        "timer": "time.perf_counter",
                        "memory": "tracemalloc peak Python-traced allocations",
                        "scope": (
                            "in-process demo execution after interpreter and "
                            "dependencies are loaded; excludes installation"
                        ),
                    },
                    "elapsed_seconds": self._summary(elapsed_values),
                    "peak_traced_memory_bytes": self._summary(memory_values),
                    "output_bytes": self._summary(output_values),
                    "checks": {
                        "expected_per_run": 9,
                        "all_runs_passed": all(
                            item.checks == item.passed == 9
                            for item in observations
                        ),
                    },
                    "runs": runs_path.name,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return DemoBenchmarkRun(
            repetitions=repetitions,
            warmups=warmups,
            report_path=report_path,
            runs_path=runs_path,
        )

    @staticmethod
    def _summary(values: list[float] | list[int]) -> dict[str, float]:
        numeric = [float(value) for value in values]
        return {
            "minimum": min(numeric),
            "median": statistics.median(numeric),
            "mean": statistics.fmean(numeric),
            "maximum": max(numeric),
            "population_standard_deviation": statistics.pstdev(numeric),
        }

    @staticmethod
    def _axis_version(workspace: Path) -> str:
        project = workspace / "pyproject.toml"
        if project.is_file():
            payload = tomllib.loads(project.read_text(encoding="utf-8"))
            poetry = payload.get("tool", {}).get("poetry", {})
            if poetry.get("name") in {"axis", "axis-bio"} and poetry.get("version"):
                return str(poetry["version"])
        try:
            return version("axis-bio")
        except PackageNotFoundError:
            return "source-tree"
