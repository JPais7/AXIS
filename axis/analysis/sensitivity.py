"""Threshold sensitivity analysis kept separate from primary inference."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from axis.analysis.recurrence import RecurrenceRanker


@dataclass(frozen=True)
class SensitivityAnalysis:
    studies: tuple[str, ...]
    scenarios: int
    genes_seen: int
    stable_genes: int
    scenario_path: Path
    gene_path: Path
    summary_path: Path


class SensitivityAnalyzer:
    """Run a declared threshold grid without changing the primary ranking."""

    def run(
        self,
        studies: list[str] | tuple[str, ...],
        *,
        data_root: str | Path = Path("data/geo"),
        output_root: str | Path = Path("data/analysis/sensitivity"),
        alphas: tuple[float, ...] = (0.01, 0.05, 0.1),
        min_differences: tuple[float, ...] = (0.0, 0.25, 0.5),
        min_recurrences: tuple[int, ...] = (2,),
    ) -> SensitivityAnalysis:
        alphas = tuple(sorted(set(alphas)))
        min_differences = tuple(sorted(set(min_differences)))
        min_recurrences = tuple(sorted(set(min_recurrences)))
        if not alphas or not min_differences or not min_recurrences:
            raise ValueError("sensitivity threshold lists must not be empty")
        if len(alphas) * len(min_differences) * len(min_recurrences) > 100:
            raise ValueError("sensitivity analysis is limited to 100 scenarios")

        destination = Path(output_root)
        scenario_root = destination / "scenarios"
        scenario_root.mkdir(parents=True, exist_ok=True)
        scenario_rows: list[dict[str, object]] = []
        gene_scenarios: dict[str, list[str]] = {}
        normalized_studies: tuple[str, ...] | None = None
        genes_seen = 0
        for alpha in alphas:
            for difference in min_differences:
                for recurrence in min_recurrences:
                    scenario_id = (
                        f"alpha-{alpha:g}_effect-{difference:g}_recurrence-{recurrence}"
                    )
                    result = RecurrenceRanker().rank(
                        studies,
                        data_root=data_root,
                        output_root=scenario_root / scenario_id,
                        alpha=alpha,
                        min_abs_difference=difference,
                        min_recurrence=recurrence,
                        analysis_role="sensitivity",
                    )
                    normalized_studies = result.studies
                    genes_seen = max(genes_seen, result.genes)
                    recurrent = self._recurrent_genes(result.output_path)
                    for gene in recurrent:
                        gene_scenarios.setdefault(gene, []).append(scenario_id)
                    scenario_rows.append(
                        {
                            "scenario_id": scenario_id,
                            "alpha": alpha,
                            "minimum_absolute_mean_difference": difference,
                            "minimum_recurrent_studies": recurrence,
                            "recurrent_genes": len(recurrent),
                            "ranking_path": str(result.output_path),
                        }
                    )

        destination.mkdir(parents=True, exist_ok=True)
        scenario_path = destination / "sensitivity-scenarios.tsv"
        self._write_rows(
            scenario_path,
            scenario_rows,
            (
                "scenario_id",
                "alpha",
                "minimum_absolute_mean_difference",
                "minimum_recurrent_studies",
                "recurrent_genes",
                "ranking_path",
            ),
        )
        scenario_count = len(scenario_rows)
        gene_rows = [
            {
                "gene_symbol": gene,
                "recurrent_scenarios": len(scenarios),
                "scenario_fraction": len(scenarios) / scenario_count,
                "stable_across_all_scenarios": len(scenarios) == scenario_count,
                "scenario_ids": "|".join(scenarios),
            }
            for gene, scenarios in gene_scenarios.items()
        ]
        gene_rows.sort(
            key=lambda row: (
                -cast(int, row["recurrent_scenarios"]),
                str(row["gene_symbol"]),
            )
        )
        gene_path = destination / "sensitivity-genes.tsv"
        self._write_rows(
            gene_path,
            gene_rows,
            (
                "gene_symbol",
                "recurrent_scenarios",
                "scenario_fraction",
                "stable_across_all_scenarios",
                "scenario_ids",
            ),
        )
        stable_genes = sum(
            bool(row["stable_across_all_scenarios"]) for row in gene_rows
        )
        summary_path = destination / "sensitivity-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "sensitivity",
                    "studies": normalized_studies or (),
                    "alphas": alphas,
                    "minimum_absolute_mean_differences": min_differences,
                    "minimum_recurrent_studies": min_recurrences,
                    "scenarios": scenario_count,
                    "genes_seen": genes_seen,
                    "genes_recurrent_in_any_scenario": len(gene_rows),
                    "genes_stable_across_all_scenarios": stable_genes,
                    "publication_eligible": False,
                    "warning": (
                        "Exploratory threshold sensitivity analysis; these "
                        "results cannot be published as primary AXIS claims."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SensitivityAnalysis(
            studies=normalized_studies or (),
            scenarios=scenario_count,
            genes_seen=genes_seen,
            stable_genes=stable_genes,
            scenario_path=scenario_path,
            gene_path=gene_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _recurrent_genes(path: Path) -> tuple[str, ...]:
        with path.open(encoding="utf-8", newline="") as source:
            return tuple(
                row["gene_symbol"]
                for row in csv.DictReader(source, delimiter="\t")
                if row["recurrent"].lower() == "true"
            )

    @staticmethod
    def _write_rows(
        path: Path,
        rows: list[dict[str, object]],
        fields: tuple[str, ...],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
