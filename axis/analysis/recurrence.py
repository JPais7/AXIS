"""Rank genes that recur across independent GEO studies."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.eligibility import verify_study_eligibility
from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class RecurrenceRanking:
    studies: tuple[str, ...]
    output_path: Path
    summary_path: Path
    genes: int
    recurrent_genes: int


@dataclass(frozen=True)
class _GeneResult:
    gene: str
    effect: float
    p_value: float
    adjusted_p_value: float

    @property
    def direction(self) -> str:
        if self.effect > 0:
            return "higher_in_case"
        if self.effect < 0:
            return "lower_in_case"
        return "unchanged"


class RecurrenceRanker:
    """Combines gene-level evidence without pooling incompatible effect scales."""

    def rank(
        self,
        studies: list[str] | tuple[str, ...],
        *,
        data_root: str | Path = Path("data/geo"),
        output_root: str | Path = Path("data/analysis"),
        alpha: float = 0.05,
        min_abs_difference: float = 0.0,
        min_recurrence: int = 2,
        analysis_role: str = "primary",
    ) -> RecurrenceRanking:
        normalized = tuple(dict.fromkeys(study.strip().upper() for study in studies))
        if len(normalized) < 2:
            raise ValueError("recurrence ranking requires at least two studies")
        invalid = next(
            (study for study in normalized if not GSE_PATTERN.fullmatch(study)),
            None,
        )
        if invalid is not None:
            raise ValueError(f"invalid GEO Series accession: {invalid!r}")
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be between 0 and 1")
        if min_abs_difference < 0:
            raise ValueError("minimum absolute difference must not be negative")
        if not 2 <= min_recurrence <= len(normalized):
            raise ValueError(
                "minimum recurrence must be between 2 and the number of studies"
            )
        if analysis_role not in {"primary", "sensitivity"}:
            raise ValueError("analysis role must be primary or sensitivity")

        eligibility = {
            study: self._verify_study(study, Path(data_root)) for study in normalized
        }
        species = {str(payload["species"]) for payload in eligibility.values()}
        if len(species) != 1:
            raise GeoApiError(
                f"approved studies use different species: {sorted(species)}"
            )
        study_results = {
            study: self._read_study(study, Path(data_root)) for study in normalized
        }
        genes = tuple(
            sorted({gene for results in study_results.values() for gene in results})
        )
        combined_p_values = np.asarray(
            [
                self._fisher(
                    tuple(
                        results[gene].p_value
                        for results in study_results.values()
                        if gene in results
                    )
                )
                for gene in genes
            ],
            dtype=float,
        )
        combined_adjusted = self._benjamini_hochberg(combined_p_values)
        records = [
            self._record(
                gene,
                study_results=study_results,
                combined_p_value=combined_p_values[index],
                combined_adjusted=combined_adjusted[index],
                alpha=alpha,
                min_abs_difference=min_abs_difference,
                min_recurrence=min_recurrence,
            )
            for index, gene in enumerate(genes)
        ]
        records.sort(
            key=lambda record: (
                not record["recurrent"],
                -int(record["significant_studies"]),
                -float(record["direction_consistency"]),
                float(record["combined_adjusted_p_value"]),
                str(record["gene_symbol"]),
            )
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "recurrence-ranking.tsv"
        self._write_results(output_path, records)
        recurrent_genes = sum(bool(record["recurrent"]) for record in records)
        summary_path = destination / "recurrence-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": analysis_role,
                    "studies": normalized,
                    "method": {
                        "per_study_evidence": (
                            "gene-level Simes p-value and median probe effect"
                        ),
                        "combined_p_value": "Fisher across available studies",
                        "multiple_testing": "Benjamini-Hochberg across genes",
                        "effect_pooling": (
                            "none; directions retained because effect scales may differ"
                        ),
                    },
                    "alpha": alpha,
                    "minimum_absolute_mean_difference": min_abs_difference,
                    "minimum_recurrent_studies": min_recurrence,
                    "eligibility": eligibility,
                    "genes": len(genes),
                    "recurrent_genes": recurrent_genes,
                    "warning": (
                        "Exploratory result. Included studies must be independent "
                        "and biologically comparable; review species, tissue, "
                        "assay, design and confounders."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return RecurrenceRanking(
            studies=normalized,
            output_path=output_path,
            summary_path=summary_path,
            genes=len(genes),
            recurrent_genes=recurrent_genes,
        )

    def _read_study(self, study: str, data_root: Path) -> dict[str, _GeneResult]:
        paths = tuple(
            sorted((data_root / study / "prepared").glob("*/gene-level-results.tsv"))
        )
        if not paths:
            raise GeoApiError(
                f"no gene-level results found for {study}; "
                f"run 'axis analyze {study} --platform GPL...' first"
            )
        by_gene: dict[str, list[_GeneResult]] = {}
        for path in paths:
            try:
                with path.open(encoding="utf-8", newline="") as source:
                    for row in csv.DictReader(source, delimiter="\t"):
                        result = _GeneResult(
                            gene=row["gene_symbol"],
                            effect=float(row["median_mean_difference"]),
                            p_value=float(row["simes_p_value"]),
                            adjusted_p_value=float(row["adjusted_p_value"]),
                        )
                        by_gene.setdefault(result.gene, []).append(result)
            except (OSError, KeyError, ValueError, csv.Error) as error:
                raise GeoApiError(
                    f"cannot read gene-level results {path}: {error}"
                ) from error
        return {
            gene: self._collapse_study_gene(gene, values)
            for gene, values in by_gene.items()
        }

    @staticmethod
    def _verify_study(study: str, data_root: Path) -> dict[str, object]:
        paths = tuple(
            sorted((data_root / study / "prepared").glob("*/gene-level-results.tsv"))
        )
        if not paths:
            raise GeoApiError(
                f"no gene-level results found for {study}; "
                f"run 'axis analyze {study} --platform GPL...' first"
            )
        manifests = tuple(
            verify_study_eligibility(path, required_role="discovery") for path in paths
        )
        first = manifests[0]
        if any(
            manifest.get("species") != first.get("species")
            or manifest.get("tissue") != first.get("tissue")
            for manifest in manifests[1:]
        ):
            raise GeoApiError(
                f"multiple matrices for {study} have incompatible eligibility"
            )
        return first

    def _collapse_study_gene(self, gene: str, values: list[_GeneResult]) -> _GeneResult:
        effects = np.asarray([value.effect for value in values], dtype=float)
        p_values = tuple(value.p_value for value in values)
        return _GeneResult(
            gene=gene,
            effect=float(np.median(effects)),
            p_value=self._simes(p_values),
            adjusted_p_value=min(value.adjusted_p_value for value in values),
        )

    def _record(
        self,
        gene: str,
        *,
        study_results: dict[str, dict[str, _GeneResult]],
        combined_p_value: float,
        combined_adjusted: float,
        alpha: float,
        min_abs_difference: float,
        min_recurrence: int,
    ) -> dict[str, str | int | float | bool]:
        available = {
            study: results[gene]
            for study, results in study_results.items()
            if gene in results
        }
        significant = {
            study: result
            for study, result in available.items()
            if result.adjusted_p_value <= alpha
            and abs(result.effect) >= min_abs_difference
        }
        directions = [result.direction for result in significant.values()]
        consistency = (
            max(directions.count(direction) for direction in set(directions))
            / len(directions)
            if directions
            else 0.0
        )
        direction_concordant = len(set(directions)) <= 1
        recurrent = len(significant) >= min_recurrence and direction_concordant
        return {
            "gene_symbol": gene,
            "available_studies": len(available),
            "significant_studies": len(significant),
            "significant_study_ids": "|".join(significant),
            "directions": "|".join(
                f"{study}:{result.direction}" for study, result in significant.items()
            ),
            "effects": "|".join(
                f"{study}:{result.effect:.12g}" for study, result in available.items()
            ),
            "direction_consistency": consistency,
            "direction_concordant": direction_concordant,
            "contradictory": (
                len(significant) >= min_recurrence and not direction_concordant
            ),
            "combined_p_value": combined_p_value,
            "combined_adjusted_p_value": combined_adjusted,
            "recurrent": recurrent,
        }

    @staticmethod
    def _write_results(
        path: Path,
        records: list[dict[str, str | int | float | bool]],
    ) -> None:
        fields = (
            "gene_symbol",
            "available_studies",
            "significant_studies",
            "significant_study_ids",
            "directions",
            "effects",
            "direction_consistency",
            "direction_concordant",
            "contradictory",
            "combined_p_value",
            "combined_adjusted_p_value",
            "recurrent",
        )
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def _fisher(p_values: tuple[float, ...]) -> float:
        safe = np.clip(np.asarray(p_values, dtype=float), 1e-300, 1.0)
        return float(stats.combine_pvalues(safe, method="fisher").pvalue)

    @staticmethod
    def _simes(p_values: tuple[float, ...]) -> float:
        ordered = np.sort(np.asarray(p_values, dtype=float))
        count = len(ordered)
        return float(
            min(
                np.min(ordered * count / np.arange(1, count + 1)),
                1.0,
            )
        )

    @staticmethod
    def _benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
        count = len(p_values)
        order = np.argsort(p_values)
        ranked = p_values[order] * count / np.arange(1, count + 1)
        ranked = np.minimum.accumulate(ranked[::-1])[::-1]
        adjusted = np.empty(count, dtype=float)
        adjusted[order] = np.minimum(ranked, 1.0)
        return adjusted
