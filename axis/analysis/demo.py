"""Small, offline and synthetic demonstration of AXIS evidence synthesis."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy import stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class DemoRun:
    checks: int
    passed: int
    report_path: Path
    summary_path: Path
    checks_path: Path


class AxisDemoRunner:
    """Verify and synthesize a tiny dataset containing no participant data."""

    def run(
        self,
        *,
        workspace: str | Path = Path("."),
        manifest_path: str | Path = Path("examples/demo/manifest.json"),
        output_root: str | Path = Path("demo-output"),
    ) -> DemoRun:
        root = Path(workspace).resolve()
        manifest = Path(manifest_path)
        if not manifest.is_absolute():
            manifest = root / manifest
        if not manifest.is_file() and manifest_path == Path(
            "examples/demo/manifest.json"
        ):
            manifest = (
                Path(__file__).resolve().parents[1]
                / "resources/demo/manifest.json"
            )
        definition = cast(
            dict[str, Any], json.loads(manifest.read_text(encoding="utf-8"))
        )
        if definition.get("schema_version") != 1:
            raise ValueError("unsupported demo manifest schema")
        if definition.get("synthetic") is not True:
            raise ValueError("the public demo must be explicitly synthetic")

        input_definition = cast(dict[str, Any], definition["input"])
        source = (
            manifest.parent / str(input_definition["path"])
            if input_definition.get("relative_to") == "manifest"
            else root / str(input_definition["path"])
        )
        expected_hash = str(input_definition["sha256"])
        observed_hash = self._sha256(source)
        checks: list[dict[str, str]] = [
            self._check("synthetic_input", True, True),
            self._check("input_sha256", observed_hash, expected_hash),
        ]
        if observed_hash != expected_hash:
            raise ValueError("demo input integrity verification failed")

        rows = self._read(source)
        primary = [row for row in rows if row["role"] == "primary"]
        sensitivity = [row for row in rows if row["role"] == "sensitivity"]
        if len(primary) != 2 or len(sensitivity) != 1:
            raise ValueError("demo requires two primary and one sensitivity cohort")

        primary_result = self._pool(primary)
        broad_result = self._pool(rows)
        expected = cast(dict[str, Any], definition["expected"])
        primary_people = self._participants(primary)
        broad_people = self._participants(rows)
        checks.extend(
            [
                self._check("primary_cohorts", len(primary), 2),
                self._check(
                    "unique_cohort_names",
                    len({row["cohort"] for row in rows}),
                    len(rows),
                ),
                self._check("primary_participants", primary_people, 30),
                self._check("broad_participants", broad_people, 42),
                self._check(
                    "all_effects_same_direction",
                    all(float(row["effect"]) < 0 for row in rows),
                    True,
                ),
                self._close_check(
                    "primary_effect",
                    primary_result["effect"],
                    float(expected["primary_effect"]),
                ),
                self._close_check(
                    "broad_effect",
                    broad_result["effect"],
                    float(expected["broad_effect"]),
                ),
            ]
        )
        failed = [item for item in checks if item["status"] != "pass"]

        output = Path(output_root)
        if not output.is_absolute():
            output = root / output
        output.mkdir(parents=True, exist_ok=True)
        summary_path = output / "synthesis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "primary": {
                        **primary_result,
                        "cohorts": 2,
                        "participants": primary_people,
                    },
                    "sensitivity": {
                        **broad_result,
                        "cohorts": 3,
                        "participants": broad_people,
                    },
                    "interpretation": (
                        "Demonstration only: no biological or clinical claim."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        checks_path = output / "checks.tsv"
        with checks_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("name", "status", "observed", "expected"),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(checks)
        report_path = output / "demo-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "failed" if failed else "passed",
                    "synthetic": True,
                    "offline": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "runtime": {
                        "python": sys.version.split()[0],
                        "platform": platform.platform(),
                    },
                    "checks": {
                        "total": len(checks),
                        "passed": len(checks) - len(failed),
                        "failed": len(failed),
                    },
                    "summary": str(summary_path),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if failed:
            raise ValueError("demo verification failed")
        return DemoRun(
            checks=len(checks),
            passed=len(checks),
            report_path=report_path,
            summary_path=summary_path,
            checks_path=checks_path,
        )

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    @staticmethod
    def _participants(rows: list[dict[str, str]]) -> int:
        return sum(int(row["cases"]) + int(row["controls"]) for row in rows)

    @staticmethod
    def _pool(rows: list[dict[str, str]]) -> dict[str, float]:
        effects = np.asarray([float(row["effect"]) for row in rows])
        variances = np.asarray([float(row["standard_error"]) ** 2 for row in rows])
        fixed_weights = 1.0 / variances
        fixed = float(np.sum(fixed_weights * effects) / fixed_weights.sum())
        q_value = float(np.sum(fixed_weights * (effects - fixed) ** 2))
        degrees = len(effects) - 1
        c_value = float(
            fixed_weights.sum()
            - np.sum(fixed_weights**2) / fixed_weights.sum()
        )
        tau_squared = max(0.0, (q_value - degrees) / c_value)
        weights = 1.0 / (variances + tau_squared)
        effect = float(np.sum(weights * effects) / weights.sum())
        standard_error = float(math.sqrt(1.0 / weights.sum()))
        return {
            "effect": effect,
            "standard_error": standard_error,
            "ci_low": effect - 1.96 * standard_error,
            "ci_high": effect + 1.96 * standard_error,
            "p_value": float(
                2.0 * stats.norm.sf(abs(effect / standard_error))
            ),
            "tau_squared": tau_squared,
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _check(name: str, observed: object, expected: object) -> dict[str, str]:
        return {
            "name": name,
            "status": "pass" if observed == expected else "fail",
            "observed": str(observed),
            "expected": str(expected),
        }

    @classmethod
    def _close_check(
        cls, name: str, observed: float, expected: float
    ) -> dict[str, str]:
        result = cls._check(name, f"{observed:.15g}", f"{expected:.15g}")
        result["status"] = (
            "pass"
            if math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-12)
            else "fail"
        )
        return result
