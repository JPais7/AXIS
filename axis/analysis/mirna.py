"""Covariate-adjusted differential analysis of deposited microRNA counts."""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from axis.analysis.empirical_bayes import moderated_linear_model
from axis.ingestion.geo import GSE_PATTERN, GeoApiError
from axis.ingestion.mirna_validation import MirnaCohortValidator


@dataclass(frozen=True)
class MirnaComparison:
    name: str
    cases: int
    controls: int
    tested_mirnas: int
    significant_mirnas: int
    results_path: Path


@dataclass(frozen=True)
class MirnaAnalysisRun:
    accession: str
    participants: int
    detected_mirnas: int
    tested_mirnas: int
    comparisons: tuple[MirnaComparison, ...]
    normalized_matrix_path: Path
    sensitivity_path: Path
    summary_path: Path


class MirnaDifferentialAnalyzer:
    """Normalize raw counts and fit moderated models with clinical covariates."""

    COMPARISONS = (
        ("all_axspa_vs_hc", {"r-axspa", "nr-axspa"}),
        ("radiographic_axspa_vs_hc", {"r-axspa"}),
        ("nonradiographic_axspa_vs_hc", {"nr-axspa"}),
    )
    MODELS = ("unadjusted", "age_sex", "age_sex_crp")

    def analyze(
        self,
        accession: str,
        *,
        data_root: str | Path = Path("data/geo"),
        alpha: float = 0.05,
        min_base_mean: float = 10.0,
    ) -> MirnaAnalysisRun:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        if min_base_mean < 0:
            raise ValueError("minimum base mean must not be negative")
        root = Path(data_root) / accession
        validation = MirnaCohortValidator().validate(
            accession, data_root=data_root
        )
        if not validation.eligible_for_analysis:
            raise GeoApiError(f"{accession} did not pass microRNA validation")
        sample_sheet = self._read_sample_sheet(validation.sample_sheet_path)
        feature_ids, sample_ids, counts = self._read_counts(
            root / "supplementary" / f"{accession}_seq_raw.txt.gz"
        )
        metadata = {row["participant_id"]: row for row in sample_sheet}
        if set(sample_ids) != set(metadata):
            raise GeoApiError("raw-count samples and sample sheet do not match")
        library_totals = np.sum(counts, axis=0)
        retained = library_totals > 0
        excluded_samples = tuple(
            sample for sample, keep in zip(sample_ids, retained, strict=True)
            if not keep
        )
        sample_ids = tuple(
            sample for sample, keep in zip(sample_ids, retained, strict=True) if keep
        )
        counts = counts[:, retained]
        size_factors = self._size_factors(counts)
        normalized = counts / size_factors[None, :]
        log_values = np.log2(normalized + 0.5)
        base_means = np.mean(normalized, axis=1)
        tested = base_means >= min_base_mean
        if int(np.sum(tested)) < 2:
            raise GeoApiError("too few microRNAs pass the abundance filter")

        output = root / "mirna-analysis"
        output.mkdir(parents=True, exist_ok=True)
        normalized_path = output / "normalized-log2-counts.tsv.gz"
        self._write_matrix(normalized_path, feature_ids, sample_ids, log_values)
        comparisons = tuple(
            self._comparison(
                f"{name}__{model_name}",
                case_diagnoses,
                model_name=model_name,
                output=output,
                feature_ids=feature_ids,
                sample_ids=sample_ids,
                log_values=log_values,
                base_means=base_means,
                tested=tested,
                metadata=metadata,
                alpha=alpha,
            )
            for name, case_diagnoses in self.COMPARISONS
            for model_name in self.MODELS
        )
        sensitivity_path = output / "sensitivity-consensus.tsv"
        self._write_sensitivity(sensitivity_path, comparisons)
        result = MirnaAnalysisRun(
            accession=accession,
            participants=len(sample_ids),
            detected_mirnas=len(feature_ids),
            tested_mirnas=int(np.sum(tested)),
            comparisons=comparisons,
            normalized_matrix_path=normalized_path,
            sensitivity_path=sensitivity_path,
            summary_path=output / "analysis.json",
        )
        report = asdict(result)
        report["normalized_matrix_path"] = str(normalized_path)
        report["sensitivity_path"] = str(sensitivity_path)
        report["summary_path"] = str(result.summary_path)
        for comparison in report["comparisons"]:
            comparison["results_path"] = str(comparison["results_path"])
        report.update(
            {
                "input": str(
                    root / "supplementary" / f"{accession}_seq_raw.txt.gz"
                ),
                "normalization": (
                    "median-of-ratios size factors using positive-count "
                    "geometric means"
                ),
                "transformation": "log2(normalized count + 0.5)",
                "model": (
                    "moderated linear-model sensitivity analysis: unadjusted; "
                    "age+sex adjusted; age+sex+log1p(CRP) adjusted"
                ),
                "multiple_testing": "Benjamini-Hochberg within each comparison",
                "alpha": alpha,
                "minimum_base_mean": min_base_mean,
                "excluded_empty_libraries": excluded_samples,
                "analyzable_participants": len(sample_ids),
                "interpretation": (
                    "Independent microRNA validation layer; do not merge these "
                    "features directly into gene-expression recurrence ranks."
                ),
            }
        )
        result.summary_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        return result

    def _comparison(
        self,
        name: str,
        case_diagnoses: set[str],
        *,
        model_name: str,
        output: Path,
        feature_ids: tuple[str, ...],
        sample_ids: tuple[str, ...],
        log_values: np.ndarray,
        base_means: np.ndarray,
        tested: np.ndarray,
        metadata: dict[str, dict[str, str]],
        alpha: float,
    ) -> MirnaComparison:
        selected = [
            index
            for index, sample in enumerate(sample_ids)
            if metadata[sample]["diagnosis"] in case_diagnoses | {"hc"}
        ]
        groups = np.asarray(
            [
                0.0
                if metadata[sample_ids[index]]["diagnosis"] == "hc"
                else 1.0
                for index in selected
            ]
        )
        ages = np.asarray(
            [float(metadata[sample_ids[index]]["age"]) for index in selected]
        )
        sexes = np.asarray(
            [
                1.0 if metadata[sample_ids[index]]["sex"].lower() == "male" else 0.0
                for index in selected
            ]
        )
        crp = np.log1p(
            np.asarray(
                [float(metadata[sample_ids[index]]["crp"]) for index in selected]
            )
        )
        if model_name == "unadjusted":
            design = np.column_stack((np.ones(len(selected)), groups))
        elif model_name == "age_sex":
            design = np.column_stack(
                (np.ones(len(selected)), groups, self._standardize(ages), sexes)
            )
        elif model_name == "age_sex_crp":
            design = np.column_stack(
                (
                    np.ones(len(selected)),
                    groups,
                    self._standardize(ages),
                    sexes,
                    self._standardize(crp),
                )
            )
        else:
            raise ValueError(f"unsupported microRNA model: {model_name}")
        model = moderated_linear_model(
            log_values[tested][:, selected],
            design,
            np.asarray([0.0, 1.0, *([0.0] * (design.shape[1] - 2))]),
        )
        adjusted = self._benjamini_hochberg(model.p_value)
        tested_indices = np.flatnonzero(tested)
        order = np.lexsort((-np.abs(model.coefficient), adjusted))
        path = output / f"{name}.tsv"
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "mirna",
                    "base_mean",
                    "adjusted_log2_effect",
                    "p_value",
                    "adjusted_p_value",
                    "significant",
                )
            )
            for position in order:
                feature_index = tested_indices[position]
                writer.writerow(
                    (
                        feature_ids[feature_index],
                        f"{base_means[feature_index]:.12g}",
                        f"{model.coefficient[position]:.12g}",
                        f"{model.p_value[position]:.12g}",
                        f"{adjusted[position]:.12g}",
                        str(bool(adjusted[position] <= alpha)),
                    )
                )
        return MirnaComparison(
            name=name,
            cases=int(np.sum(groups)),
            controls=int(np.sum(groups == 0)),
            tested_mirnas=len(tested_indices),
            significant_mirnas=int(np.sum(adjusted <= alpha)),
            results_path=path,
        )

    @staticmethod
    def _write_sensitivity(
        path: Path, comparisons: tuple[MirnaComparison, ...]
    ) -> None:
        grouped: dict[str, dict[str, dict[str, tuple[float, float]]]] = {}
        for comparison in comparisons:
            contrast, model = comparison.name.rsplit("__", 1)
            with comparison.results_path.open(
                encoding="utf-8", newline=""
            ) as source:
                rows = csv.DictReader(source, delimiter="\t")
                grouped.setdefault(contrast, {})[model] = {
                    row["mirna"]: (
                        float(row["adjusted_log2_effect"]),
                        float(row["adjusted_p_value"]),
                    )
                    for row in rows
                }
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "comparison",
                    "mirna",
                    "unadjusted_q",
                    "age_sex_q",
                    "age_sex_crp_q",
                    "consistent_direction",
                    "significant_all_models",
                )
            )
            for contrast, models in grouped.items():
                for mirna in models["unadjusted"]:
                    values = [
                        models[model][mirna]
                        for model in MirnaDifferentialAnalyzer.MODELS
                    ]
                    effects = [value[0] for value in values]
                    consistent = all(effect > 0 for effect in effects) or all(
                        effect < 0 for effect in effects
                    )
                    writer.writerow(
                        (
                            contrast,
                            mirna,
                            *(f"{value[1]:.12g}" for value in values),
                            str(consistent),
                            str(all(value[1] <= 0.05 for value in values)),
                        )
                    )

    @staticmethod
    def _read_sample_sheet(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _read_counts(path: Path) -> tuple[tuple[str, ...], tuple[str, ...], np.ndarray]:
        features: list[str] = []
        rows: list[list[float]] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.reader(source, delimiter="\t")
            header = next(reader)
            samples = tuple(header[1:])
            for row in reader:
                features.append(row[0])
                rows.append([float(value) for value in row[1:]])
        return tuple(features), samples, np.asarray(rows, dtype=float)

    @staticmethod
    def _size_factors(counts: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            log_counts = np.where(counts > 0, np.log(counts), np.nan)
        geometric_means = np.exp(np.nanmean(log_counts, axis=1))
        factors: list[float] = []
        for column in range(counts.shape[1]):
            valid = (counts[:, column] > 0) & np.isfinite(geometric_means)
            ratios = counts[valid, column] / geometric_means[valid]
            factors.append(float(np.median(ratios)))
        result = np.asarray(factors, dtype=float)
        if np.any(~np.isfinite(result)) or np.any(result <= 0):
            raise GeoApiError("could not calculate positive library size factors")
        return np.asarray(
            result / np.exp(np.mean(np.log(result))),
            dtype=float,
        )

    @staticmethod
    def _standardize(values: np.ndarray) -> np.ndarray:
        deviation = float(np.std(values))
        if deviation == 0:
            raise GeoApiError("a modeled covariate has no variation")
        return np.asarray((values - np.mean(values)) / deviation, dtype=float)

    @staticmethod
    def _benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
        count = len(p_values)
        order = np.argsort(p_values)
        ranked = p_values[order]
        adjusted = np.minimum.accumulate(
            (ranked * count / np.arange(1, count + 1))[::-1]
        )[::-1]
        result = np.empty(count)
        result[order] = np.minimum(adjusted, 1.0)
        return result

    @staticmethod
    def _write_matrix(
        path: Path,
        features: tuple[str, ...],
        samples: tuple[str, ...],
        values: np.ndarray,
    ) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, delimiter="\t", lineterminator="\n")
            writer.writerow(("miRNA", *samples))
            for feature, row in zip(features, values, strict=True):
                writer.writerow((feature, *(f"{value:.12g}" for value in row)))
