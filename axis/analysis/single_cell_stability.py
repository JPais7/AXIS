"""Donor-level uncertainty and stability analysis for focused targets."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class TargetStabilityRun:
    comparisons: int
    stable_comparisons: int
    output_path: Path
    leave_one_out_path: Path
    summary_path: Path


class TargetStabilityAnalyzer:
    """Quantify whether a pseudobulk effect depends on individual donors."""

    def analyze(
        self,
        pseudobulk_path: str | Path,
        *,
        gene: str,
        case_status: str = "AXI",
        control_status: str = "Healthy",
        minimum_cells: int = 20,
        bootstrap_iterations: int = 5000,
        random_seed: int = 20260727,
        output_root: str | Path,
    ) -> TargetStabilityRun:
        if bootstrap_iterations < 100:
            raise ValueError("bootstrap_iterations must be at least 100")
        rows = self._read(Path(pseudobulk_path), gene.upper(), minimum_cells)
        cell_types = sorted({row["cell_type"] for row in rows})
        results: list[dict[str, object]] = []
        leave_one_out: list[dict[str, object]] = []
        generator = np.random.default_rng(random_seed)
        for cell_type in cell_types:
            typed = [row for row in rows if row["cell_type"] == cell_type]
            case = {
                row["subject"]: float(row["log2_cpm"])
                for row in typed
                if row["status"] == case_status
            }
            control = {
                row["subject"]: float(row["log2_cpm"])
                for row in typed
                if row["status"] == control_status
            }
            if len(case) < 3 or len(control) < 3:
                continue
            estimate, lower, upper, p_value = self._welch(
                np.asarray(tuple(case.values())),
                np.asarray(tuple(control.values())),
            )
            loo_rows = self._leave_one_out(
                gene.upper(), cell_type, case, control, full_effect=estimate
            )
            leave_one_out.extend(loo_rows)
            loo_effects = np.asarray(
                [float(cast(float, row["log2_cpm_difference"])) for row in loo_rows]
            )
            bootstrap = self._bootstrap(
                np.asarray(tuple(case.values())),
                np.asarray(tuple(control.values())),
                iterations=bootstrap_iterations,
                generator=generator,
            )
            bootstrap_lower, bootstrap_upper = np.quantile(bootstrap, (0.025, 0.975))
            full_direction = np.sign(estimate)
            loo_consistency = float(np.mean(np.sign(loo_effects) == full_direction))
            bootstrap_consistency = float(np.mean(np.sign(bootstrap) == full_direction))
            maximum_influence = float(np.max(np.abs(loo_effects - estimate)))
            stable = (
                loo_consistency == 1.0
                and bootstrap_consistency >= 0.95
                and bootstrap_lower * bootstrap_upper > 0
            )
            results.append(
                {
                    "gene_symbol": gene.upper(),
                    "cell_type": cell_type,
                    "case_subjects": len(case),
                    "control_subjects": len(control),
                    "log2_cpm_difference": estimate,
                    "welch_ci_95_lower": lower,
                    "welch_ci_95_upper": upper,
                    "welch_p_value": p_value,
                    "bootstrap_ci_95_lower": float(bootstrap_lower),
                    "bootstrap_ci_95_upper": float(bootstrap_upper),
                    "leave_one_donor_out_runs": len(loo_rows),
                    "leave_one_out_direction_consistency": loo_consistency,
                    "bootstrap_direction_probability": bootstrap_consistency,
                    "maximum_absolute_donor_influence": maximum_influence,
                    "stable": stable,
                }
            )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "target-stability.tsv"
        leave_one_out_path = destination / "leave-one-donor-out.tsv"
        summary_path = destination / "target-stability.json"
        self._write(output_path, results)
        self._write(leave_one_out_path, leave_one_out)
        stable_count = sum(bool(row["stable"]) for row in results)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "focused_donor_stability",
                    "created_at": datetime.now(UTC).isoformat(),
                    "gene_symbol": gene.upper(),
                    "comparisons": len(results),
                    "stable_comparisons": stable_count,
                    "statistical_unit": "independent_subject",
                    "model": "Welch difference of subject log2(CPM + 0.5)",
                    "uncertainty": (
                        "Welch-Satterthwaite 95% confidence interval plus "
                        "nonparametric group-stratified bootstrap"
                    ),
                    "bootstrap_iterations": bootstrap_iterations,
                    "random_seed": random_seed,
                    "stability_rule": (
                        "all leave-one-donor-out effects retain direction, "
                        "bootstrap direction probability >= 0.95 and bootstrap "
                        "95% interval excludes zero"
                    ),
                    "warning": (
                        "This tests donor influence but does not adjust age, sex, "
                        "treatment or batch because those covariates are not "
                        "available in the processed metadata."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return TargetStabilityRun(
            comparisons=len(results),
            stable_comparisons=stable_count,
            output_path=output_path,
            leave_one_out_path=leave_one_out_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _welch(
        case: np.ndarray, control: np.ndarray
    ) -> tuple[float, float, float, float]:
        estimate = float(np.mean(case) - np.mean(control))
        case_variance = float(np.var(case, ddof=1))
        control_variance = float(np.var(control, ddof=1))
        case_term = case_variance / len(case)
        control_term = control_variance / len(control)
        standard_error = math.sqrt(case_term + control_term)
        denominator = case_term**2 / (len(case) - 1) + control_term**2 / (
            len(control) - 1
        )
        degrees = (case_term + control_term) ** 2 / denominator
        critical = float(stats.t.ppf(0.975, degrees))
        _, p_value = stats.ttest_ind(case, control, equal_var=False)
        return (
            estimate,
            estimate - critical * standard_error,
            estimate + critical * standard_error,
            float(p_value),
        )

    @classmethod
    def _leave_one_out(
        cls,
        gene: str,
        cell_type: str,
        case: dict[str, float],
        control: dict[str, float],
        *,
        full_effect: float,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for status, collection in (("AXI", case), ("Healthy", control)):
            for omitted in collection:
                case_values = np.asarray(
                    [value for subject, value in case.items() if subject != omitted]
                )
                control_values = np.asarray(
                    [value for subject, value in control.items() if subject != omitted]
                )
                effect, lower, upper, p_value = cls._welch(case_values, control_values)
                rows.append(
                    {
                        "gene_symbol": gene,
                        "cell_type": cell_type,
                        "omitted_subject": omitted,
                        "omitted_status": status,
                        "log2_cpm_difference": effect,
                        "change_from_full_effect": effect - full_effect,
                        "ci_95_lower": lower,
                        "ci_95_upper": upper,
                        "p_value": p_value,
                        "direction_retained": np.sign(effect) == np.sign(full_effect),
                    }
                )
        return rows

    @staticmethod
    def _bootstrap(
        case: np.ndarray,
        control: np.ndarray,
        *,
        iterations: int,
        generator: np.random.Generator,
    ) -> np.ndarray:
        case_indices = generator.integers(0, len(case), size=(iterations, len(case)))
        control_indices = generator.integers(
            0, len(control), size=(iterations, len(control))
        )
        return np.mean(case[case_indices], axis=1) - np.mean(
            control[control_indices], axis=1
        )

    @staticmethod
    def _read(path: Path, gene: str, minimum_cells: int) -> list[dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return [
                    row
                    for row in csv.DictReader(source, delimiter="\t")
                    if row["gene_symbol"].strip().upper() == gene
                    and int(row["cells"]) >= minimum_cells
                ]
        except (OSError, UnicodeError, csv.Error, KeyError, ValueError) as error:
            raise GeoApiError(
                f"cannot read pseudobulk table {path}: {error}"
            ) from error

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
