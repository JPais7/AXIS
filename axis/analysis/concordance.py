"""Direction concordance below conventional significance thresholds."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.recurrence import RecurrenceRanker, _GeneResult
from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class DirectionConcordance:
    studies: tuple[str, ...]
    genes: int
    concordant_genes: int
    output_path: Path
    summary_path: Path


class _ConcordanceRecord(TypedDict):
    gene_symbol: str
    available_studies: int
    direction: str
    direction_concordant: bool
    nominal_supporting_studies: int
    study_directions: str
    study_effects: str
    mean_absolute_effect_percentile: float
    combined_p_value: float
    combined_adjusted_p_value: float


class DirectionConcordanceAnalyzer:
    """Rank directionally stable effects without declaring recurrence."""

    def run(
        self,
        studies: list[str] | tuple[str, ...],
        *,
        data_root: str | Path = Path("data/geo"),
        output_root: str | Path = Path("data/analysis/concordance"),
        minimum_studies: int = 2,
        nominal_alpha: float = 0.05,
    ) -> DirectionConcordance:
        normalized = tuple(dict.fromkeys(study.strip().upper() for study in studies))
        if len(normalized) < 2:
            raise ValueError("direction concordance requires at least two studies")
        invalid = next(
            (study for study in normalized if not GSE_PATTERN.fullmatch(study)),
            None,
        )
        if invalid is not None:
            raise ValueError(f"invalid GEO Series accession: {invalid!r}")
        if not 2 <= minimum_studies <= len(normalized):
            raise ValueError(
                "minimum studies must be between 2 and the number of studies"
            )
        if not 0.0 < nominal_alpha < 1.0:
            raise ValueError("nominal alpha must be between 0 and 1")

        root = Path(data_root)
        ranker = RecurrenceRanker()
        eligibility = {study: ranker._verify_study(study, root) for study in normalized}
        species = {str(payload["species"]) for payload in eligibility.values()}
        if len(species) != 1:
            raise GeoApiError(
                f"approved studies use different species: {sorted(species)}"
            )
        study_results = {study: ranker._read_study(study, root) for study in normalized}
        percentiles = {
            study: self._effect_percentiles(results)
            for study, results in study_results.items()
        }
        genes = tuple(
            sorted({gene for results in study_results.values() for gene in results})
        )
        records = [
            self._record(
                gene,
                study_results=study_results,
                percentiles=percentiles,
                minimum_studies=minimum_studies,
                nominal_alpha=nominal_alpha,
            )
            for gene in genes
        ]
        included = [
            record
            for record in records
            if int(record["available_studies"]) >= minimum_studies
        ]
        combined = np.asarray(
            [float(record["combined_p_value"]) for record in included],
            dtype=float,
        )
        adjusted = ranker._benjamini_hochberg(combined)
        for record, adjusted_value in zip(included, adjusted, strict=True):
            record["combined_adjusted_p_value"] = float(adjusted_value)
        included.sort(
            key=lambda record: (
                not bool(record["direction_concordant"]),
                -float(record["mean_absolute_effect_percentile"]),
                float(record["combined_adjusted_p_value"]),
                str(record["gene_symbol"]),
            )
        )

        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "direction-concordance.tsv"
        self._write(output_path, included)
        concordant_genes = sum(
            bool(record["direction_concordant"]) for record in included
        )
        summary_path = destination / "direction-concordance-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "exploratory_direction_concordance",
                    "publication_eligible": False,
                    "studies": normalized,
                    "minimum_available_studies": minimum_studies,
                    "nominal_p_value_threshold": nominal_alpha,
                    "eligibility": eligibility,
                    "genes": len(included),
                    "directionally_concordant_genes": concordant_genes,
                    "ranking": (
                        "concordant direction, then mean within-study absolute "
                        "effect percentile; raw effect scales are not pooled"
                    ),
                    "warning": (
                        "Directional agreement is not statistical recurrence "
                        "and cannot be promoted to a primary AXIS claim."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return DirectionConcordance(
            studies=normalized,
            genes=len(included),
            concordant_genes=concordant_genes,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _effect_percentiles(
        results: dict[str, _GeneResult],
    ) -> dict[str, float]:
        genes = tuple(results)
        effects = np.asarray(
            [abs(results[gene].effect) for gene in genes],
            dtype=float,
        )
        ranks = stats.rankdata(effects, method="average") / len(effects)
        return {gene: float(rank) for gene, rank in zip(genes, ranks, strict=True)}

    @staticmethod
    def _record(
        gene: str,
        *,
        study_results: dict[str, dict[str, _GeneResult]],
        percentiles: dict[str, dict[str, float]],
        minimum_studies: int,
        nominal_alpha: float,
    ) -> _ConcordanceRecord:
        available = {
            study: results[gene]
            for study, results in study_results.items()
            if gene in results
        }
        directions = tuple(
            result.direction
            for result in available.values()
            if result.direction != "unchanged"
        )
        concordant = (
            len(available) >= minimum_studies
            and len(directions) == len(available)
            and len(set(directions)) == 1
        )
        p_values = np.asarray(
            [result.p_value for result in available.values()],
            dtype=float,
        )
        safe = np.clip(p_values, 1e-300, 1.0)
        combined = float(stats.combine_pvalues(safe, method="fisher").pvalue)
        mean_percentile = float(
            np.mean([percentiles[study][gene] for study in available])
        )
        return {
            "gene_symbol": gene,
            "available_studies": len(available),
            "direction": directions[0] if concordant else "mixed",
            "direction_concordant": concordant,
            "nominal_supporting_studies": sum(
                result.p_value <= nominal_alpha for result in available.values()
            ),
            "study_directions": "|".join(
                f"{study}:{result.direction}" for study, result in available.items()
            ),
            "study_effects": "|".join(
                f"{study}:{result.effect:.12g}" for study, result in available.items()
            ),
            "mean_absolute_effect_percentile": mean_percentile,
            "combined_p_value": combined,
            "combined_adjusted_p_value": 1.0,
        }

    @staticmethod
    def _write(path: Path, records: list[_ConcordanceRecord]) -> None:
        fields = (
            "gene_symbol",
            "available_studies",
            "direction",
            "direction_concordant",
            "nominal_supporting_studies",
            "study_directions",
            "study_effects",
            "mean_absolute_effect_percentile",
            "combined_p_value",
            "combined_adjusted_p_value",
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
