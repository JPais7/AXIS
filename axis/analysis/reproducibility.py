"""Frozen, offline reproduction of named AXIS computational studies."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.cd8_cross_cohort import Cd8CrossCohortAnalyzer


@dataclass(frozen=True)
class ReproductionCheck:
    name: str
    status: str
    observed: str
    expected: str


@dataclass(frozen=True)
class StudyReproductionRun:
    study: str
    checks: int
    passed: int
    report_path: Path
    checks_path: Path
    rebuilt_root: Path


class StudyReproducer:
    """Rebuild a frozen study and enforce its scientific invariants."""

    SUPPORTED = ("ddx24-study",)

    def reproduce(
        self,
        study: str,
        *,
        workspace: str | Path = Path("."),
        manifest_path: str | Path | None = None,
        output_root: str | Path = Path("data/reproducibility"),
    ) -> StudyReproductionRun:
        if study not in self.SUPPORTED:
            raise ValueError(
                f"unsupported study {study!r}; choose one of {self.SUPPORTED}"
            )
        root = Path(workspace).resolve()
        manifest = Path(manifest_path) if manifest_path else (
            root / "reproducibility" / study / "manifest.json"
        )
        if not manifest.is_absolute():
            manifest = root / manifest
        definition = self._load_manifest(manifest)
        self._validate_manifest(definition, study)

        destination = Path(output_root)
        if not destination.is_absolute():
            destination = root / destination
        destination = destination / study
        destination.mkdir(parents=True, exist_ok=True)
        rebuilt = destination / "rebuilt"
        rebuilt.mkdir(parents=True, exist_ok=True)

        checks = self._verify_inputs(root, definition)
        if any(check.status != "pass" for check in checks):
            self._write_checks(destination / "checks.tsv", checks)
            raise ValueError("input integrity verification failed")

        inputs = cast(dict[str, dict[str, Any]], definition["inputs"])
        primary = Cd8CrossCohortAnalyzer().analyze(
            gse194315_path=root / str(inputs["gse194315"]["path"]),
            gse288581_path=root / str(inputs["gse288581"]["path"]),
            output_root=rebuilt / "primary-cd8",
        )
        checks.extend(
            self._verify_primary(
                primary.summary_path,
                primary.effects_path,
                definition,
            )
        )
        broad_path = self._build_broad_sensitivity(
            primary.effects_path,
            root / str(inputs["gse163314"]["path"]),
            rebuilt / "broad-cd8-sensitivity.json",
        )
        checks.extend(self._verify_broad(broad_path, definition))
        checks.extend(self._scientific_guardrails(primary.effects_path, broad_path))

        checks_path = destination / "checks.tsv"
        self._write_checks(checks_path, checks)
        failed = [check for check in checks if check.status != "pass"]
        report_path = destination / "reproduction-report.json"
        report = {
            "schema_version": 1,
            "study": study,
            "status": "failed" if failed else "reproduced",
            "created_at": datetime.now(UTC).isoformat(),
            "offline": True,
            "manifest": str(manifest),
            "manifest_sha256": self._sha256(manifest),
            "runtime": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "numpy": np.__version__,
            },
            "checks": {
                "total": len(checks),
                "passed": len(checks) - len(failed),
                "failed": len(failed),
            },
            "rebuilt_artifacts": {
                "primary_summary": str(primary.summary_path),
                "primary_effects": str(primary.effects_path),
                "broad_cd8_sensitivity": str(broad_path),
            },
            "valid_claim": (
                "DDX24 is lower in the two compatible primary CD8 cohorts and "
                "directionally consistent in the independent broad-CD8 "
                "GSE163314 sensitivity cohort; this is associative evidence."
            ),
        }
        report_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        if failed:
            names = ", ".join(check.name for check in failed)
            raise ValueError(f"scientific reproduction checks failed: {names}")
        return StudyReproductionRun(
            study=study,
            checks=len(checks),
            passed=len(checks),
            report_path=report_path,
            checks_path=checks_path,
            rebuilt_root=rebuilt,
        )

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"reproduction manifest not found: {path}")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("reproduction manifest must be a JSON object")
        return cast(dict[str, Any], loaded)

    @staticmethod
    def _validate_manifest(definition: dict[str, Any], study: str) -> None:
        if definition.get("schema_version") != 1:
            raise ValueError("unsupported reproduction manifest schema")
        if definition.get("study") != study:
            raise ValueError("manifest study does not match requested study")
        inputs = definition.get("inputs")
        expected = definition.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError("manifest requires inputs and expected objects")
        if set(inputs) != {"gse194315", "gse288581", "gse163314"}:
            raise ValueError("manifest must declare exactly three frozen inputs")

    def _verify_inputs(
        self, root: Path, definition: dict[str, Any]
    ) -> list[ReproductionCheck]:
        checks: list[ReproductionCheck] = []
        inputs = cast(dict[str, dict[str, Any]], definition["inputs"])
        for name, item in inputs.items():
            path = root / str(item["path"])
            exists = path.is_file()
            checks.append(
                ReproductionCheck(
                    f"input_exists_{name}",
                    "pass" if exists else "fail",
                    str(exists),
                    "True",
                )
            )
            if not exists:
                continue
            observed = self._sha256(path)
            expected = str(item["sha256"])
            checks.append(
                ReproductionCheck(
                    f"input_sha256_{name}",
                    "pass" if observed == expected else "fail",
                    observed,
                    expected,
                )
            )
        lock = root / str(definition["environment"]["poetry_lock"])
        observed_lock = self._sha256(lock) if lock.is_file() else "missing"
        expected_lock = str(definition["environment"]["poetry_lock_sha256"])
        checks.append(
            ReproductionCheck(
                "poetry_lock_sha256",
                "pass" if observed_lock == expected_lock else "fail",
                observed_lock,
                expected_lock,
            )
        )
        return checks

    def _verify_primary(
        self,
        summary_path: Path,
        effects_path: Path,
        definition: dict[str, Any],
    ) -> list[ReproductionCheck]:
        summary = self._tsv(summary_path)
        effects = self._tsv(effects_path)
        ddx24 = next(row for row in summary if row["gene_symbol"] == "DDX24")
        expected = cast(dict[str, Any], definition["expected"]["primary"])
        ddx_effects = [row for row in effects if row["gene_symbol"] == "DDX24"]
        values = [
            (
                "primary_random_effect",
                float(ddx24["random_effect"]),
                float(expected["random_effect"]),
            ),
            ("primary_ci_low", float(ddx24["ci_low"]), float(expected["ci_low"])),
            (
                "primary_ci_high",
                float(ddx24["ci_high"]),
                float(expected["ci_high"]),
            ),
            (
                "primary_p_value",
                float(ddx24["p_value"]),
                float(expected["p_value"]),
            ),
        ]
        checks = [
            self._close_check(name, observed, wanted)
            for name, observed, wanted in values
        ]
        checks.extend(
            [
                self._equal_check(
                    "primary_case_donors",
                    int(ddx24["case_donors"]),
                    int(expected["case_donors"]),
                ),
                self._equal_check(
                    "primary_control_donors",
                    int(ddx24["control_donors"]),
                    int(expected["control_donors"]),
                ),
                self._equal_check(
                    "primary_independent_cohorts",
                    len({row["cohort"] for row in ddx_effects}),
                    2,
                ),
                self._equal_check(
                    "primary_all_cohort_directions_lower",
                    all(float(row["effect"]) < 0 for row in ddx_effects),
                    True,
                ),
            ]
        )
        return checks

    def _build_broad_sensitivity(
        self, effects_path: Path, donor_path: Path, output: Path
    ) -> Path:
        effects = [
            row
            for row in self._tsv(effects_path)
            if row["gene_symbol"] == "DDX24"
        ]
        donors = self._tsv(donor_path)
        cases = np.asarray(
            [
                float(row["ddx24_log2_cpm"])
                for row in donors
                if row["group"] == "axSpA"
            ]
        )
        controls = np.asarray(
            [
                float(row["ddx24_log2_cpm"])
                for row in donors
                if row["group"] == "healthy_control"
            ]
        )
        if len(cases) != 2 or len(controls) != 2:
            raise ValueError("GSE163314 sensitivity requires two donors per group")
        gse_effect = float(cases.mean() - controls.mean())
        gse_se = float(
            math.sqrt(
                cases.var(ddof=1) / len(cases)
                + controls.var(ddof=1) / len(controls)
            )
        )
        cohort_effects = np.asarray(
            [float(row["effect"]) for row in effects] + [gse_effect]
        )
        ses = np.asarray(
            [float(row["standard_error"]) for row in effects] + [gse_se]
        )
        variances = ses**2
        fixed_weights = 1.0 / variances
        fixed = float(
            np.sum(fixed_weights * cohort_effects) / fixed_weights.sum()
        )
        q_value = float(
            np.sum(fixed_weights * (cohort_effects - fixed) ** 2)
        )
        df = len(cohort_effects) - 1
        c_value = float(
            fixed_weights.sum()
            - np.sum(fixed_weights**2) / fixed_weights.sum()
        )
        tau_squared = max(0.0, (q_value - df) / c_value)
        weights = 1.0 / (variances + tau_squared)
        pooled = float(np.sum(weights * cohort_effects) / weights.sum())
        se = float(math.sqrt(1.0 / weights.sum()))
        payload = {
            "role": "broad_CD8_cell_state_sensitivity",
            "cohorts": ["GSE194315", "GSE288581", "GSE163314"],
            "participants": 51,
            "gse163314": {
                "cases": len(cases),
                "controls": len(controls),
                "effect": gse_effect,
                "standard_error": gse_se,
            },
            "pooled_effect": pooled,
            "standard_error": se,
            "ci_low": pooled - 1.96 * se,
            "ci_high": pooled + 1.96 * se,
            "p_value": float(2.0 * stats.norm.sf(abs(pooled / se))),
            "tau_squared": tau_squared,
            "all_cohorts_lower_in_case": bool(np.all(cohort_effects < 0)),
            "guardrail": (
                "GSE163314 is sensitivity-only because its author annotation "
                "is broad CD8_T rather than memory/effector CD8."
            ),
        }
        output.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return output

    def _verify_broad(
        self, path: Path, definition: dict[str, Any]
    ) -> list[ReproductionCheck]:
        observed = json.loads(path.read_text(encoding="utf-8"))
        expected = cast(
            dict[str, Any], definition["expected"]["broad_sensitivity"]
        )
        return [
            self._close_check(
                "broad_random_effect",
                float(observed["pooled_effect"]),
                float(expected["random_effect"]),
            ),
            self._close_check(
                "broad_ci_low",
                float(observed["ci_low"]),
                float(expected["ci_low"]),
            ),
            self._close_check(
                "broad_ci_high",
                float(observed["ci_high"]),
                float(expected["ci_high"]),
            ),
            self._close_check(
                "broad_p_value",
                float(observed["p_value"]),
                float(expected["p_value"]),
            ),
            self._equal_check(
                "broad_participants",
                int(observed["participants"]),
                int(expected["participants"]),
            ),
        ]

    def _scientific_guardrails(
        self, effects_path: Path, broad_path: Path
    ) -> list[ReproductionCheck]:
        effects = [
            row
            for row in self._tsv(effects_path)
            if row["gene_symbol"] == "DDX24"
        ]
        broad = json.loads(broad_path.read_text(encoding="utf-8"))
        participants = sum(
            int(row["case_donors"]) + int(row["control_donors"])
            for row in effects
        )
        return [
            self._equal_check(
                "participant_is_statistical_unit", participants, 47
            ),
            self._equal_check(
                "no_duplicate_primary_cohort",
                len({row["cohort"] for row in effects}),
                len(effects),
            ),
            self._equal_check(
                "primary_excludes_pooled_hra001027",
                "HRA001027" not in {row["cohort"] for row in effects},
                True,
            ),
            self._equal_check(
                "gse163314_is_sensitivity_only",
                broad["role"],
                "broad_CD8_cell_state_sensitivity",
            ),
            self._equal_check(
                "three_cohort_directional_concordance",
                broad["all_cohorts_lower_in_case"],
                True,
            ),
        ]

    @staticmethod
    def _tsv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _close_check(
        name: str, observed: float, expected: float
    ) -> ReproductionCheck:
        passed = math.isclose(
            observed, expected, rel_tol=1e-9, abs_tol=1e-12
        )
        return ReproductionCheck(
            name,
            "pass" if passed else "fail",
            f"{observed:.15g}",
            f"{expected:.15g}",
        )

    @staticmethod
    def _equal_check(
        name: str, observed: object, expected: object
    ) -> ReproductionCheck:
        return ReproductionCheck(
            name,
            "pass" if observed == expected else "fail",
            str(observed),
            str(expected),
        )

    @staticmethod
    def _write_checks(path: Path, checks: list[ReproductionCheck]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("name", "status", "observed", "expected"),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(asdict(check) for check in checks)
