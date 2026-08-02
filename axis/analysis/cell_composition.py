"""Marker-score diagnostics for blood-cell composition confounding."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.differential import DifferentialAnalyzer


@dataclass(frozen=True)
class CellCompositionRun:
    studies: int
    targets: int
    scores_path: Path
    adjustment_path: Path
    method_path: Path


class CellCompositionDiagnostic:
    """Estimate marker scores and test target robustness to composition proxies."""

    MARKERS = {
        "monocyte": ("LILRB1", "CTSD", "FCGR1A", "S100A8", "S100A9", "CTSS"),
        "neutrophil": ("FCGR3B", "CSF3R", "FPR1", "CEACAM8", "MNDA"),
        "T_cell": ("CD3D", "CD3E", "TRAC", "IL7R", "LTB"),
        "NK_cell": ("NKG7", "KLRD1", "GNLY", "PRF1", "KLRB1"),
        "B_cell": ("CD79A", "MS4A1", "CD37", "CD74", "HLA-DRA"),
        "platelet": ("PPBP", "PF4", "NRGN", "GNG11", "RGS18"),
    }

    def analyze(
        self,
        *,
        studies: Mapping[str, str | Path],
        platform_annotations: Mapping[str, str | Path],
        targets: tuple[str, ...] = ("DDX24", "ADA"),
        output_root: str | Path = Path(
            "data/analysis/cell-composition-diagnostic"
        ),
    ) -> CellCompositionRun:
        score_rows: list[dict[str, object]] = []
        adjustment_rows: list[dict[str, object]] = []
        coverage: dict[str, dict[str, list[str]]] = {}
        for accession, directory_value in studies.items():
            directory = Path(directory_value)
            annotation_path = Path(platform_annotations[accession])
            annotations = DifferentialAnalyzer._read_annotations(annotation_path)
            case_ids, case_samples, case_values = DifferentialAnalyzer._read_matrix(
                directory / "case-matrix.tsv.gz"
            )
            control_ids, control_samples, control_values = (
                DifferentialAnalyzer._read_matrix(
                    directory / "control-matrix.tsv.gz"
                )
            )
            if case_ids != control_ids:
                raise ValueError(f"{accession} case/control feature mismatch")
            samples = case_samples + control_samples
            groups = np.asarray(
                [1.0] * len(case_samples) + [0.0] * len(control_samples)
            )
            expression = np.column_stack((case_values, control_values))
            by_gene = self._gene_indices(case_ids, annotations)
            signatures, study_coverage = self._signature_scores(
                expression, by_gene
            )
            coverage[accession] = study_coverage
            for sample_index, sample in enumerate(samples):
                row: dict[str, object] = {
                    "study": accession,
                    "sample_id": sample,
                    "group": "case" if groups[sample_index] else "control",
                }
                row.update(
                    {
                        lineage: float(values[sample_index])
                        for lineage, values in signatures.items()
                    }
                )
                score_rows.append(row)
            design_scores = np.column_stack(tuple(signatures.values()))
            for target in targets:
                indices = by_gene.get(target, ())
                if not indices:
                    adjustment_rows.append(
                        {
                            "study": accession,
                            "gene_symbol": target,
                            "status": "target_not_mapped",
                        }
                    )
                    continue
                target_expression = np.median(expression[list(indices), :], axis=0)
                unadjusted = self._fit(target_expression, groups, None)
                adjusted = self._fit(target_expression, groups, design_scores)
                adjustment_rows.append(
                    {
                        "study": accession,
                        "gene_symbol": target,
                        "status": "diagnostic_only",
                        "unadjusted_group_effect": unadjusted["effect"],
                        "unadjusted_p_value": unadjusted["p_value"],
                        "adjusted_group_effect": adjusted["effect"],
                        "adjusted_p_value": adjusted["p_value"],
                        "effect_retained_percent": (
                            abs(float(adjusted["effect"]))
                            / abs(float(unadjusted["effect"]))
                            * 100.0
                            if float(unadjusted["effect"]) != 0
                            else ""
                        ),
                        "direction_retained": (
                            np.sign(float(unadjusted["effect"]))
                            == np.sign(float(adjusted["effect"]))
                        ),
                        "composition_covariates": "|".join(signatures),
                        "residual_degrees_of_freedom": adjusted["degrees"],
                    }
                )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        scores_path = destination / "sample-marker-scores.tsv"
        adjustment_path = destination / "target-composition-adjustment.tsv"
        method_path = destination / "composition-method.json"
        self._write(scores_path, score_rows)
        self._write(adjustment_path, adjustment_rows)
        method_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "cell_composition_confounding_diagnostic",
                    "method": (
                        "within-study standardized marker-expression scores, "
                        "followed by target ~ group + lineage marker scores"
                    ),
                    "marker_sets": self.MARKERS,
                    "marker_coverage": coverage,
                    "guardrails": [
                        "Marker scores are not measured cell proportions.",
                        "This is a sensitivity analysis, not reference deconvolution.",
                        "Correlated lineage scores can reduce precision.",
                        "A validated reference-based method remains required.",
                        "Medication and clinical covariates are not replaced.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CellCompositionRun(
            studies=len(studies),
            targets=len(targets),
            scores_path=scores_path,
            adjustment_path=adjustment_path,
            method_path=method_path,
        )

    @staticmethod
    def _gene_indices(
        feature_ids: tuple[str, ...],
        annotations: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[int, ...]]:
        collected: dict[str, list[int]] = {}
        for index, feature in enumerate(feature_ids):
            for gene in annotations.get(feature, ()):
                collected.setdefault(gene.upper(), []).append(index)
        return {gene: tuple(indices) for gene, indices in collected.items()}

    def _signature_scores(
        self,
        expression: np.ndarray,
        by_gene: dict[str, tuple[int, ...]],
    ) -> tuple[dict[str, np.ndarray], dict[str, list[str]]]:
        scores: dict[str, np.ndarray] = {}
        coverage: dict[str, list[str]] = {}
        for lineage, markers in self.MARKERS.items():
            available = [marker for marker in markers if marker in by_gene]
            coverage[lineage] = available
            if len(available) < 2:
                continue
            gene_values = np.vstack(
                [
                    np.median(expression[list(by_gene[marker]), :], axis=0)
                    for marker in available
                ]
            )
            deviations = np.std(gene_values, axis=1, ddof=1)
            valid = deviations > 0
            standardized = (
                gene_values[valid] - np.mean(gene_values[valid], axis=1)[:, None]
            ) / deviations[valid, None]
            scores[lineage] = np.median(standardized, axis=0)
        if len(scores) < 3:
            raise ValueError("fewer than three cell-lineage signatures are mapped")
        return scores, coverage

    @staticmethod
    def _fit(
        outcome: np.ndarray,
        group: np.ndarray,
        covariates: np.ndarray | None,
    ) -> dict[str, float | int]:
        columns = [np.ones(len(outcome)), group]
        if covariates is not None:
            columns.extend(covariates[:, index] for index in range(covariates.shape[1]))
        design = np.column_stack(columns)
        rank = int(np.linalg.matrix_rank(design))
        degrees = len(outcome) - rank
        if rank != design.shape[1] or degrees < 2:
            raise ValueError("composition-adjusted design is not estimable")
        coefficients, _, _, _ = np.linalg.lstsq(design, outcome, rcond=None)
        residuals = outcome - design @ coefficients
        residual_variance = float(np.sum(residuals**2) / degrees)
        covariance = residual_variance * np.linalg.inv(design.T @ design)
        standard_error = float(math.sqrt(covariance[1, 1]))
        effect = float(coefficients[1])
        statistic = effect / standard_error
        p_value = float(2.0 * stats.t.sf(abs(statistic), degrees))
        return {
            "effect": effect,
            "standard_error": standard_error,
            "p_value": p_value,
            "degrees": degrees,
        }

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(dict.fromkeys(key for row in rows for key in row))
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
