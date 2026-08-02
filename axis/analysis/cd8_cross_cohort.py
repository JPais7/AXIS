"""Cross-cohort synthesis of predeclared targets in independent CD8 cohorts."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy import stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class Cd8CrossCohortRun:
    targets: int
    cohorts: int
    effects_path: Path
    summary_path: Path
    sensitivity_path: Path
    method_path: Path


class Cd8CrossCohortAnalyzer:
    """Combine donor-level CD8 effects without counting cell types as cohorts."""

    TARGETS = ("DDX24", "ADA")

    def analyze(
        self,
        *,
        gse194315_path: str | Path,
        gse288581_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/CD8-cross-cohort"
        ),
    ) -> Cd8CrossCohortRun:
        effects = self._gse194315(Path(gse194315_path), "CD8 TEM")
        effects.extend(self._gse288581(Path(gse288581_path)))
        summaries = [
            self._summary(gene, [row for row in effects if row["gene_symbol"] == gene])
            for gene in self.TARGETS
        ]
        sensitivity = self._cell_state_sensitivity(Path(gse194315_path), effects)
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        effects_path = destination / "cohort-effects.tsv"
        summary_path = destination / "cross-cohort-summary.tsv"
        sensitivity_path = destination / "cd8-state-sensitivity.tsv"
        method_path = destination / "analysis-method.json"
        self._write(effects_path, effects)
        self._write(summary_path, summaries)
        self._write(sensitivity_path, sensitivity)
        method_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "role": "independent_CD8_cross_cohort_synthesis",
                    "primary_cell_states": {
                        "GSE194315": "CD8 TEM",
                        "GSE288581": "CD45RO+ CD8 memory",
                    },
                    "statistical_unit": "human donor",
                    "pooling": "inverse-variance fixed and DerSimonian-Laird random",
                    "sensitivity": "replace GSE194315 CD8 TEM with CD8 Naive",
                    "guardrails": [
                        "Only two independent cohorts are available.",
                        "CD8 subsets are similar but not identical.",
                        "CD8 Naive and CD8 TEM from GSE194315 are not independent.",
                        "The synthesis is targeted validation, not causal evidence.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Cd8CrossCohortRun(
            targets=2,
            cohorts=2,
            effects_path=effects_path,
            summary_path=summary_path,
            sensitivity_path=sensitivity_path,
            method_path=method_path,
        )

    def _gse194315(self, path: Path, cell_type: str) -> list[dict[str, object]]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        selected = [
            row
            for row in rows
            if row["gene_symbol"] in self.TARGETS and row["cell_type"] == cell_type
        ]
        if len(selected) != 2:
            raise ValueError(f"missing target rows for GSE194315 {cell_type}")
        return [
            {
                "gene_symbol": row["gene_symbol"],
                "cohort": "GSE194315",
                "cell_state": cell_type,
                "case_donors": int(float(row["case_subjects"])),
                "control_donors": int(float(row["control_subjects"])),
                "effect": float(row["adjusted_log2_cpm_difference"]),
                "standard_error": float(row["standard_error"]),
                "p_value": float(row["p_value"]),
            }
            for row in selected
        ]

    def _gse288581(self, path: Path) -> list[dict[str, object]]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        selected = [row for row in rows if row["gene_symbol"] in self.TARGETS]
        if len(selected) != 2:
            raise ValueError("missing target rows for GSE288581")
        output: list[dict[str, object]] = []
        for row in selected:
            effect = float(row["log2_cpm_difference"])
            statistic = float(row["welch_statistic"])
            if statistic == 0:
                raise ValueError(f"cannot derive SE for {row['gene_symbol']}")
            output.append(
                {
                    "gene_symbol": row["gene_symbol"],
                    "cohort": "GSE288581",
                    "cell_state": "CD45RO+ CD8 memory",
                    "case_donors": int(row["case_donors"]),
                    "control_donors": int(row["control_donors"]),
                    "effect": effect,
                    "standard_error": abs(effect / statistic),
                    "p_value": float(row["p_value"]),
                }
            )
        return output

    @staticmethod
    def _summary(gene: str, rows: list[dict[str, object]]) -> dict[str, object]:
        effects = np.asarray(
            [float(cast(Any, row["effect"])) for row in rows]
        )
        variances = np.asarray(
            [float(cast(Any, row["standard_error"])) ** 2 for row in rows]
        )
        weights = 1.0 / variances
        fixed = float(np.sum(weights * effects) / weights.sum())
        q_value = float(np.sum(weights * (effects - fixed) ** 2))
        c_value = float(weights.sum() - np.sum(weights**2) / weights.sum())
        tau_squared = max(0.0, (q_value - 1.0) / c_value)
        random_weights = 1.0 / (variances + tau_squared)
        random = float(np.sum(random_weights * effects) / random_weights.sum())
        random_se = float(math.sqrt(1.0 / random_weights.sum()))
        p_value = float(2.0 * stats.norm.sf(abs(random / random_se)))
        return {
            "gene_symbol": gene,
            "cohorts": 2,
            "case_donors": sum(
                int(cast(Any, row["case_donors"])) for row in rows
            ),
            "control_donors": sum(
                int(cast(Any, row["control_donors"])) for row in rows
            ),
            "fixed_effect": fixed,
            "random_effect": random,
            "standard_error": random_se,
            "ci_low": random - 1.96 * random_se,
            "ci_high": random + 1.96 * random_se,
            "p_value": p_value,
            "direction": "lower_in_case" if random < 0 else "higher_in_case",
            "cochran_q": q_value,
            "q_p_value": float(stats.chi2.sf(q_value, 1)),
            "i_squared_percent": (
                max(0.0, (q_value - 1.0) / q_value) * 100.0
                if q_value > 0
                else 0.0
            ),
            "tau_squared": tau_squared,
            "directionally_concordant": len({effect > 0 for effect in effects}) == 1,
        }

    def _cell_state_sensitivity(
        self, gse194315_path: Path, primary: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        naive = self._gse194315(gse194315_path, "CD8 Naive")
        external = [row for row in primary if row["cohort"] == "GSE288581"]
        return [
            {
                "gene_symbol": gene,
                "gse194315_cell_state": "CD8 Naive",
                **self._summary(
                    gene,
                    [
                        row
                        for row in naive + external
                        if row["gene_symbol"] == gene
                    ],
                ),
            }
            for gene in self.TARGETS
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
