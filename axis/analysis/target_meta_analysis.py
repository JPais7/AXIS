"""Targeted random-effects meta-analysis over compatible microarray contrasts."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class TargetMetaAnalysisRun:
    targets: int
    studies: int
    effects_path: Path
    summary_path: Path
    leave_one_out_path: Path
    method_path: Path
    figure_paths: tuple[Path, ...]


class TargetMetaAnalyzer:
    """Estimate target effects without treating Simes p-values as standard errors."""

    def analyze(
        self,
        *,
        studies: Mapping[str, str | Path],
        targets: tuple[str, ...] = ("DDX24", "ADA"),
        output_root: str | Path = Path("data/analysis/target-meta-analysis"),
    ) -> TargetMetaAnalysisRun:
        if len(studies) < 3:
            raise ValueError("random-effects analysis requires at least 3 studies")
        effects = [
            self._study_effect(accession, Path(directory), gene)
            for gene in targets
            for accession, directory in studies.items()
        ]
        summaries = [
            self._pool(gene, [row for row in effects if row["gene_symbol"] == gene])
            for gene in targets
        ]
        leave_one_out = [
            {
                "gene_symbol": gene,
                "omitted_study": str(omitted["study"]),
                **self._pool_values(
                    [row for row in effects if row["gene_symbol"] == gene]
                    and [
                        row
                        for row in effects
                        if row["gene_symbol"] == gene
                        and row["study"] != omitted["study"]
                    ]
                ),
            }
            for gene in targets
            for omitted in effects
            if omitted["gene_symbol"] == gene
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        effects_path = destination / "study-effects.tsv"
        summary_path = destination / "target-meta-analysis.tsv"
        leave_one_out_path = destination / "leave-one-study-out.tsv"
        self._write(effects_path, effects)
        self._write(summary_path, summaries)
        self._write(leave_one_out_path, leave_one_out)
        figure_paths = tuple(
            self._forest(
                gene,
                [row for row in effects if row["gene_symbol"] == gene],
                next(row for row in summaries if row["gene_symbol"] == gene),
                destination / f"{gene.lower()}-forest-plot.png",
            )
            for gene in targets
        )
        method_path = destination / "meta-analysis-method.json"
        method_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "targeted_random_effects_meta_analysis",
                    "targets": list(targets),
                    "studies": list(studies),
                    "effect": (
                        "case minus control mean on each study's normalized "
                        "log-expression scale"
                    ),
                    "probe_selection": (
                        "probe annotated to the target whose effect is closest "
                        "to the gene-level median effect"
                    ),
                    "standard_error": (
                        "reconstructed from that probe's two-sided p-value, "
                        "effect and residual degrees of freedom"
                    ),
                    "pooling": "DerSimonian-Laird random effects",
                    "heterogeneity": ["Cochran_Q", "I_squared", "tau_squared"],
                    "sensitivity": "leave_one_study_out",
                    "guardrails": [
                        "Simes gene-level p-values are not used as standard errors.",
                        "Only normalized log-expression contrasts are combined.",
                        "Three studies provide imprecise heterogeneity estimates.",
                        "This analysis is association, not causal evidence.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return TargetMetaAnalysisRun(
            targets=len(targets),
            studies=len(studies),
            effects_path=effects_path,
            summary_path=summary_path,
            leave_one_out_path=leave_one_out_path,
            method_path=method_path,
            figure_paths=figure_paths,
        )

    @staticmethod
    def _study_effect(
        accession: str, directory: Path, gene: str
    ) -> dict[str, object]:
        analysis = json.loads(
            (directory / "differential-analysis.json").read_text(encoding="utf-8")
        )
        method = analysis.get("method", {})
        if not isinstance(method, dict):
            raise ValueError(f"{accession} has no valid method metadata")
        degrees = int(method.get("residual_degrees_of_freedom") or 0)
        if degrees < 1:
            raise ValueError(f"{accession} has no residual degrees of freedom")
        with (directory / "gene-level-results.tsv").open(
            encoding="utf-8", newline=""
        ) as source:
            gene_row = next(
                (
                    row
                    for row in csv.DictReader(source, delimiter="\t")
                    if row["gene_symbol"].strip().upper() == gene
                ),
                None,
            )
        if gene_row is None:
            raise ValueError(f"{gene} is missing from {accession}")
        median_effect = float(gene_row["median_mean_difference"])
        with (directory / "differential-expression.tsv").open(
            encoding="utf-8", newline=""
        ) as source:
            probes = [
                row
                for row in csv.DictReader(source, delimiter="\t")
                if gene
                in {
                    symbol.strip().upper()
                    for symbol in row["gene_symbols"].split("|")
                }
            ]
        if not probes:
            raise ValueError(f"{gene} has no annotated probes in {accession}")
        representative = min(
            probes,
            key=lambda row: abs(float(row["mean_difference"]) - median_effect),
        )
        effect = float(representative["mean_difference"])
        p_value = min(max(float(representative["p_value"]), 1e-300), 1.0)
        t_statistic = float(stats.t.isf(p_value / 2.0, degrees))
        if not math.isfinite(t_statistic) or t_statistic <= 0 or effect == 0:
            raise ValueError(f"cannot reconstruct {gene} SE in {accession}")
        standard_error = abs(effect) / t_statistic
        return {
            "gene_symbol": gene,
            "study": accession,
            "probe_id": representative["probe_id"],
            "effect": effect,
            "standard_error": standard_error,
            "ci_low": effect - 1.96 * standard_error,
            "ci_high": effect + 1.96 * standard_error,
            "p_value": p_value,
            "residual_degrees_of_freedom": degrees,
            "case_samples": int(analysis["case_samples"]),
            "control_samples": int(analysis["control_samples"]),
        }

    @classmethod
    def _pool(
        cls, gene: str, rows: list[dict[str, object]]
    ) -> dict[str, object]:
        return {"gene_symbol": gene, **cls._pool_values(rows)}

    @staticmethod
    def _pool_values(rows: list[dict[str, object]]) -> dict[str, object]:
        if len(rows) < 2:
            raise ValueError("pooling requires at least two study effects")
        effects = np.asarray(
            [float(cast(Any, row["effect"])) for row in rows]
        )
        variances = np.asarray(
            [float(cast(Any, row["standard_error"])) ** 2 for row in rows]
        )
        fixed_weights = 1.0 / variances
        fixed_effect = float(np.sum(fixed_weights * effects) / fixed_weights.sum())
        q_value = float(np.sum(fixed_weights * (effects - fixed_effect) ** 2))
        degrees = len(rows) - 1
        c_value = float(
            fixed_weights.sum()
            - np.sum(fixed_weights**2) / fixed_weights.sum()
        )
        tau_squared = max(0.0, (q_value - degrees) / c_value)
        random_weights = 1.0 / (variances + tau_squared)
        pooled = float(np.sum(random_weights * effects) / random_weights.sum())
        pooled_se = float(math.sqrt(1.0 / random_weights.sum()))
        z_value = pooled / pooled_se
        p_value = float(2.0 * stats.norm.sf(abs(z_value)))
        i_squared = (
            max(0.0, (q_value - degrees) / q_value) * 100.0
            if q_value > 0
            else 0.0
        )
        q_p_value = float(stats.chi2.sf(q_value, degrees))
        return {
            "studies": len(rows),
            "pooled_effect": pooled,
            "standard_error": pooled_se,
            "ci_low": pooled - 1.96 * pooled_se,
            "ci_high": pooled + 1.96 * pooled_se,
            "p_value": p_value,
            "direction": (
                "higher_in_case"
                if pooled > 0
                else "lower_in_case"
                if pooled < 0
                else "unchanged"
            ),
            "cochran_q": q_value,
            "q_p_value": q_p_value,
            "i_squared_percent": i_squared,
            "tau_squared": tau_squared,
        }

    @staticmethod
    def _forest(
        gene: str,
        effects: list[dict[str, object]],
        summary: dict[str, object],
        path: Path,
    ) -> Path:
        labels = [str(row["study"]) for row in effects] + ["Random effects"]
        values = [float(cast(Any, row["effect"])) for row in effects] + [
            float(cast(Any, summary["pooled_effect"]))
        ]
        lows = [float(cast(Any, row["ci_low"])) for row in effects] + [
            float(cast(Any, summary["ci_low"]))
        ]
        highs = [float(cast(Any, row["ci_high"])) for row in effects] + [
            float(cast(Any, summary["ci_high"]))
        ]
        positions = np.arange(len(labels), 0, -1)
        figure, axis = plt.subplots(figsize=(7.2, 3.8))
        axis.errorbar(
            values[:-1],
            positions[:-1],
            xerr=[
                np.asarray(values[:-1]) - np.asarray(lows[:-1]),
                np.asarray(highs[:-1]) - np.asarray(values[:-1]),
            ],
            fmt="o",
            color="#2b6cb0",
            capsize=3,
        )
        axis.errorbar(
            values[-1],
            positions[-1],
            xerr=[[values[-1] - lows[-1]], [highs[-1] - values[-1]]],
            fmt="D",
            color="#c53030",
            capsize=4,
        )
        axis.axvline(0, color="#666666", linewidth=1, linestyle="--")
        axis.set_yticks(positions, labels)
        axis.set_xlabel("Case - control normalized log-expression")
        axis.set_title(
            f"{gene} random-effects synthesis (I²={summary['i_squared_percent']:.1f}%)"
        )
        figure.tight_layout()
        figure.savefig(path, dpi=180)
        plt.close(figure)
        return path

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
