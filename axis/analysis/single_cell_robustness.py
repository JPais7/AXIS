"""Covariate, leave-one-subject-out and lineage robustness for GSE194315."""

from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.single_cell_pseudobulk import SingleCellPseudobulkAnalyzer


@dataclass(frozen=True)
class SingleCellRobustnessRun:
    adjusted_tests: int
    leave_one_out_tests: int
    adjusted_path: Path
    leave_one_out_path: Path
    lineage_path: Path
    availability_path: Path
    summary_path: Path


class SingleCellRobustnessAnalyzer:
    """Use only deposited covariates and preserve subjects as replicates."""

    LINEAGES = {
        "CD14 Mono": "myeloid",
        "CD16 Mono": "myeloid",
        "cDC2": "myeloid",
        "CD4 TCM": "T_cell",
        "CD4 Naive": "T_cell",
        "CD8 TEM": "T_cell",
        "CD8 Naive": "T_cell",
        "gdT": "T_cell",
        "CD4 TEM": "T_cell",
        "B naive": "B_cell",
        "B intermediate": "B_cell",
        "B memory": "B_cell",
        "NK": "NK_cell",
        "Eryth": "erythroid",
    }

    def analyze(
        self,
        *,
        pseudobulk_path: str | Path,
        metadata_path: str | Path,
        reference_results_path: str | Path,
        output_root: str | Path = Path(
            "data/single-cell/GSE194315/robustness"
        ),
    ) -> SingleCellRobustnessRun:
        pseudobulk = self._rows(Path(pseudobulk_path))
        reference = self._rows(Path(reference_results_path))
        batch = self._batch_proportions(Path(metadata_path))
        adjusted = self._adjusted(pseudobulk, batch)
        leave_one_out, stability = self._leave_one_out(pseudobulk)
        lineages = self._lineages(reference)
        availability = self._availability()
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        adjusted_path = destination / "batch-adjusted-targets.tsv"
        leave_one_out_path = destination / "leave-one-subject-out.tsv"
        stability_path = destination / "leave-one-out-stability.tsv"
        lineage_path = destination / "lineage-consistency.tsv"
        availability_path = destination / "covariate-availability.tsv"
        summary_path = destination / "robustness-analysis.json"
        self._write(adjusted_path, adjusted)
        self._write(leave_one_out_path, leave_one_out)
        self._write(stability_path, stability)
        self._write(lineage_path, lineages)
        self._write(availability_path, availability)
        ddx_stable = [
            row
            for row in stability
            if row["gene_symbol"] == "DDX24"
            and row["direction_stability_fraction"] == 1.0
        ]
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE194315",
                    "analysis_role": "single_cell_target_robustness",
                    "statistical_unit": "subject",
                    "available_adjustment": (
                        "processing-batch proportions represented by up to "
                        "three principal components"
                    ),
                    "unavailable_adjustments": [
                        "age",
                        "sex",
                        "medication",
                        "disease_activity",
                    ],
                    "sex_stratification_status": (
                        "not_run_sex_absent_from_deposited_subject_metadata"
                    ),
                    "adjusted_tests": len(adjusted),
                    "leave_one_out_tests": len(leave_one_out),
                    "DDX24_cell_types_direction_stable_for_every_omission": len(
                        ddx_stable
                    ),
                    "warning": (
                        "Batch adjustment is a sensitivity analysis because "
                        "case status and processing pools are not fully balanced."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SingleCellRobustnessRun(
            adjusted_tests=len(adjusted),
            leave_one_out_tests=len(leave_one_out),
            adjusted_path=adjusted_path,
            leave_one_out_path=leave_one_out_path,
            lineage_path=lineage_path,
            availability_path=availability_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _batch_proportions(
        path: Path,
    ) -> dict[tuple[str, str], dict[str, float]]:
        counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                if row["IncludedInStudy"] != "TRUE":
                    continue
                counts[(row["Subject"], row["CellType"])][row["Run"]] += 1
        result: dict[tuple[str, str], dict[str, float]] = {}
        for key, values in counts.items():
            total = sum(values.values())
            result[key] = {
                batch: count / total for batch, count in values.items()
            }
        return result

    @classmethod
    def _adjusted(
        cls,
        rows: list[dict[str, str]],
        batch: dict[tuple[str, str], dict[str, float]],
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        groups = sorted(
            {(row["cell_type"], row["gene_symbol"]) for row in rows}
        )
        for cell_type, gene in groups:
            selected = [
                row
                for row in rows
                if row["cell_type"] == cell_type
                and row["gene_symbol"] == gene
                and int(row["cells"]) >= 20
            ]
            batches = sorted(
                {
                    candidate
                    for row in selected
                    for candidate in batch.get(
                        (row["subject"], cell_type), {}
                    )
                }
            )
            batch_matrix = np.asarray(
                [
                    [
                        batch.get((row["subject"], cell_type), {}).get(
                            candidate, 0.0
                        )
                        for candidate in batches
                    ]
                    for row in selected
                ],
                dtype=float,
            )
            centred = batch_matrix - np.mean(batch_matrix, axis=0)
            _, singular, vectors = np.linalg.svd(
                centred, full_matrices=False
            )
            rank = int(np.sum(singular > 1e-10))
            pcs = min(3, rank, max(0, len(selected) - 4))
            scores = centred @ vectors[:pcs].T if pcs else np.empty(
                (len(selected), 0)
            )
            status = np.asarray(
                [1.0 if row["status"] == "AXI" else 0.0 for row in selected]
            )
            response = np.asarray(
                [float(row["log2_cpm"]) for row in selected]
            )
            design = np.column_stack(
                [np.ones(len(selected)), status, scores]
            )
            coefficients, _, _, _ = np.linalg.lstsq(
                design, response, rcond=None
            )
            residual = response - design @ coefficients
            dof = len(response) - np.linalg.matrix_rank(design)
            covariance = (
                np.linalg.pinv(design.T @ design)
                * float(residual @ residual)
                / dof
            )
            standard_error = math.sqrt(max(0.0, covariance[1, 1]))
            statistic = (
                float(coefficients[1]) / standard_error
                if standard_error
                else float("nan")
            )
            p_value = float(
                2 * stats.t.sf(abs(statistic), dof)
                if math.isfinite(statistic)
                else 1.0
            )
            results.append(
                {
                    "gene_symbol": gene,
                    "cell_type": cell_type,
                    "subjects": len(selected),
                    "case_subjects": sum(status),
                    "control_subjects": len(status) - sum(status),
                    "batch_levels": len(batches),
                    "batch_principal_components": pcs,
                    "adjusted_log2_cpm_difference": float(coefficients[1]),
                    "direction": (
                        "lower_in_case"
                        if coefficients[1] < 0
                        else "higher_in_case"
                    ),
                    "standard_error": standard_error,
                    "t_statistic": statistic,
                    "p_value": p_value,
                    "adjusted_p_value": 1.0,
                }
            )
        for cell_type in sorted({str(row["cell_type"]) for row in results}):
            indices = [
                index
                for index, row in enumerate(results)
                if row["cell_type"] == cell_type
            ]
            adjusted = SingleCellPseudobulkAnalyzer._bh(
                [float(str(results[index]["p_value"])) for index in indices]
            )
            for index, value in zip(indices, adjusted, strict=True):
                results[index]["adjusted_p_value"] = value
        return results

    @staticmethod
    def _leave_one_out(
        rows: list[dict[str, str]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        output: list[dict[str, object]] = []
        summary: list[dict[str, object]] = []
        groups = sorted(
            {(row["cell_type"], row["gene_symbol"]) for row in rows}
        )
        for cell_type, gene in groups:
            selected = [
                row
                for row in rows
                if row["cell_type"] == cell_type
                and row["gene_symbol"] == gene
                and int(row["cells"]) >= 20
            ]
            case = [
                float(row["log2_cpm"])
                for row in selected
                if row["status"] == "AXI"
            ]
            control = [
                float(row["log2_cpm"])
                for row in selected
                if row["status"] == "Healthy"
            ]
            full = float(np.mean(case) - np.mean(control))
            effects: list[float] = []
            for excluded in selected:
                retained = [
                    row
                    for row in selected
                    if row["subject"] != excluded["subject"]
                ]
                case_values = [
                    float(row["log2_cpm"])
                    for row in retained
                    if row["status"] == "AXI"
                ]
                control_values = [
                    float(row["log2_cpm"])
                    for row in retained
                    if row["status"] == "Healthy"
                ]
                effect = float(
                    np.mean(case_values) - np.mean(control_values)
                )
                effects.append(effect)
                output.append(
                    {
                        "gene_symbol": gene,
                        "cell_type": cell_type,
                        "excluded_subject": excluded["subject"],
                        "excluded_group": excluded["status"],
                        "full_effect": full,
                        "leave_one_out_effect": effect,
                        "direction_preserved": effect * full > 0,
                    }
                )
            most_influential = max(
                output[-len(selected) :],
                key=lambda row: abs(
                    float(str(row["leave_one_out_effect"])) - full
                ),
            )
            summary.append(
                {
                    "gene_symbol": gene,
                    "cell_type": cell_type,
                    "subjects": len(selected),
                    "full_effect": full,
                    "minimum_leave_one_out_effect": min(effects),
                    "maximum_leave_one_out_effect": max(effects),
                    "direction_stability_fraction": sum(
                        effect * full > 0 for effect in effects
                    )
                    / len(effects),
                    "most_influential_subject": most_influential[
                        "excluded_subject"
                    ],
                    "largest_absolute_effect_change": abs(
                        float(
                            str(most_influential["leave_one_out_effect"])
                        )
                        - full
                    ),
                }
            )
        return output, summary

    @classmethod
    def _lineages(
        cls, rows: list[dict[str, str]]
    ) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for gene in ("DDX24", "ADA"):
            target = [row for row in rows if row["gene_symbol"] == gene]
            for lineage in sorted(set(cls.LINEAGES.values())):
                selected = [
                    row
                    for row in target
                    if cls.LINEAGES.get(row["cell_type"]) == lineage
                ]
                if not selected:
                    continue
                output.append(
                    {
                        "gene_symbol": gene,
                        "lineage": lineage,
                        "cell_types_tested": len(selected),
                        "lower_in_case": sum(
                            row["direction"] == "lower_in_case"
                            for row in selected
                        ),
                        "significant_lower_in_case": sum(
                            row["direction"] == "lower_in_case"
                            and float(row["adjusted_p_value"]) < 0.05
                            for row in selected
                        ),
                        "mean_log2_cpm_difference": float(
                            np.mean(
                                [
                                    float(row["log2_cpm_difference"])
                                    for row in selected
                                ]
                            )
                        ),
                    }
                )
        return output

    @staticmethod
    def _availability() -> list[dict[str, object]]:
        return [
            {
                "covariate": covariate,
                "availability": availability,
                "action": action,
            }
            for covariate, availability, action in (
                ("diagnosis", "available", "included_as_primary_exposure"),
                ("processing_batch", "available", "adjusted_with_batch_PCs"),
                ("cell_type", "available", "analysed_separately"),
                ("age", "absent", "request_from_authors"),
                ("sex", "absent", "sex_stratification_not_performed"),
                ("medication", "absent", "request_from_authors"),
                ("disease_activity", "absent", "request_from_authors"),
            )
        ]

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
