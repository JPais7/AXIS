"""Exploratory differential expression over prepared GEO matrices."""

from __future__ import annotations

import csv
import gzip
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.empirical_bayes import (
    moderated_linear_model,
    moderated_two_group_test,
)
from axis.analysis.sample_design import SampleDesignBuilder
from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class DifferentialAnalysis:
    accession: str
    platform: str
    output_path: Path
    gene_output_path: Path
    summary_path: Path
    features: int
    mapped_features: int
    significant_features: int
    genes: int
    significant_genes: int


class DifferentialAnalyzer:
    """Calculates probe-level Welch tests and multiple-testing correction."""

    def analyze(
        self,
        accession: str,
        *,
        platform: str,
        data_root: str | Path = Path("data/geo"),
        alpha: float = 0.05,
        min_abs_difference: float = 0.0,
        method: str = "auto",
        sample_sheet: str | Path | None = None,
        covariates: tuple[str, ...] = (),
        subject_column: str | None = None,
    ) -> tuple[DifferentialAnalysis, ...]:
        accession = accession.strip().upper()
        platform = platform.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if not re_fullmatch_platform(platform):
            raise ValueError(f"invalid GEO platform accession: {platform!r}")
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be between 0 and 1")
        if min_abs_difference < 0:
            raise ValueError("minimum absolute difference must not be negative")
        if method not in {"auto", "moderated", "welch"}:
            raise ValueError("method must be auto, moderated, or welch")

        root = Path(data_root)
        annotation_path = root / "platforms" / platform / f"{platform}.annot.gz"
        if not annotation_path.exists():
            raise GeoApiError(
                f"platform annotation is missing: {annotation_path}; "
                f"run 'axis platform {platform}' first"
            )
        annotations = self._read_annotations(annotation_path)
        prepared_root = root / accession / "prepared"
        preparation_directories = (
            tuple(path for path in sorted(prepared_root.iterdir()) if path.is_dir())
            if prepared_root.exists()
            else ()
        )
        if not preparation_directories:
            raise GeoApiError(
                f"no prepared matrices found for {accession}; "
                f"run 'axis prepare {accession} ...' first"
            )
        return tuple(
            self._analyze_matrix(
                accession,
                platform,
                directory,
                annotations=annotations,
                alpha=alpha,
                min_abs_difference=min_abs_difference,
                requested_method=method,
                sample_sheet=Path(sample_sheet) if sample_sheet is not None else None,
                covariates=covariates,
                subject_column=subject_column,
            )
            for directory in preparation_directories
        )

    def _analyze_matrix(
        self,
        accession: str,
        platform: str,
        directory: Path,
        *,
        annotations: dict[str, tuple[str, ...]],
        alpha: float,
        min_abs_difference: float,
        requested_method: str,
        sample_sheet: Path | None,
        covariates: tuple[str, ...],
        subject_column: str | None,
    ) -> DifferentialAnalysis:
        case_ids, case_samples, case_values = self._read_matrix(
            directory / "case-matrix.tsv.gz"
        )
        control_ids, control_samples, control_values = self._read_matrix(
            directory / "control-matrix.tsv.gz"
        )
        if case_ids != control_ids:
            raise GeoApiError("case and control matrices have different feature IDs")
        if case_values.shape[1] < 2 or control_values.shape[1] < 2:
            raise GeoApiError(
                "differential testing requires at least two samples per group"
            )

        case_means = np.mean(case_values, axis=1)
        control_means = np.mean(control_values, axis=1)
        differences = case_means - control_means
        selected_method, method_details = self._select_method(
            directory, requested_method, sample_sheet=sample_sheet
        )
        if selected_method == "linear-model":
            assert sample_sheet is not None
            sample_ids = case_samples + control_samples
            values = np.column_stack((case_values, control_values))
            design = SampleDesignBuilder().build(
                sample_sheet,
                sample_ids=sample_ids,
                covariates=covariates,
                subject_column=subject_column,
            )
            model = moderated_linear_model(
                values,
                design.matrix,
                design.contrast,
            )
            differences = model.coefficient
            p_values = model.p_value
            method_details.update(
                {
                    "design_columns": design.columns,
                    "contrast": "group_case",
                    "sample_sheet": str(sample_sheet),
                    "modeled_covariates": list(covariates),
                    "subject_column": subject_column,
                    "prior_variance": model.prior_variance,
                    "prior_degrees_of_freedom": (model.prior_degrees_of_freedom),
                    "residual_degrees_of_freedom": (model.residual_degrees_of_freedom),
                    "design_rank": model.design_rank,
                }
            )
            declared = method_details.get("declared_but_unmodeled_covariates", [])
            if isinstance(declared, list):
                method_details["declared_but_unmodeled_covariates"] = [
                    value for value in declared if value not in covariates
                ]
        elif selected_method == "moderated":
            test = moderated_two_group_test(case_values, control_values)
            p_values = np.asarray(test.p_value, dtype=float)
            method_details.update(
                {
                    "prior_variance": test.prior_variance,
                    "prior_degrees_of_freedom": (test.prior_degrees_of_freedom),
                    "residual_degrees_of_freedom": (test.residual_degrees_of_freedom),
                }
            )
        else:
            welch = stats.ttest_ind(
                case_values,
                control_values,
                axis=1,
                equal_var=False,
                nan_policy="omit",
            )
            p_values = np.asarray(welch.pvalue, dtype=float)
        p_values = np.where(np.isfinite(p_values), p_values, 1.0)
        adjusted = self._benjamini_hochberg(p_values)
        order = np.lexsort((-np.abs(differences), adjusted))

        output_path = directory / "differential-expression.tsv"
        with output_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "probe_id",
                    "gene_symbols",
                    "case_mean",
                    "control_mean",
                    "mean_difference",
                    "p_value",
                    "adjusted_p_value",
                    "significant",
                )
            )
            for index in order:
                probe_id = case_ids[index]
                is_significant = (
                    adjusted[index] <= alpha
                    and abs(differences[index]) >= min_abs_difference
                )
                writer.writerow(
                    (
                        probe_id,
                        "|".join(annotations.get(probe_id, ())),
                        self._number(case_means[index]),
                        self._number(control_means[index]),
                        self._number(differences[index]),
                        self._number(p_values[index]),
                        self._number(adjusted[index]),
                        str(bool(is_significant)).lower(),
                    )
                )

        mapped_features = sum(probe_id in annotations for probe_id in case_ids)
        significant_features = int(
            np.sum((adjusted <= alpha) & (np.abs(differences) >= min_abs_difference))
        )
        (
            gene_output_path,
            gene_count,
            significant_genes,
        ) = self._write_gene_results(
            directory,
            probe_ids=case_ids,
            annotations=annotations,
            differences=differences,
            p_values=p_values,
            alpha=alpha,
            min_abs_difference=min_abs_difference,
        )
        summary_path = directory / "differential-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "accession": accession,
                    "platform": platform,
                    "method": method_details,
                    "multiple_testing": "Benjamini-Hochberg",
                    "alpha": alpha,
                    "minimum_absolute_mean_difference": min_abs_difference,
                    "case_samples": int(case_values.shape[1]),
                    "control_samples": int(control_values.shape[1]),
                    "features": len(case_ids),
                    "mapped_features": mapped_features,
                    "significant_features": significant_features,
                    "gene_aggregation": {
                        "effect": "median probe mean difference",
                        "p_value": "Simes combination across probes",
                        "multiple_testing": "Benjamini-Hochberg across genes",
                    },
                    "genes": gene_count,
                    "significant_genes": significant_genes,
                    "annotation_path": str(
                        Path("platforms") / platform / f"{platform}.annot.gz"
                    ),
                    "warning": (
                        "Exploratory result. Confirm study design, preprocessing, "
                        "pairing, covariates and biological replication before "
                        "scientific interpretation."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return DifferentialAnalysis(
            accession=accession,
            platform=platform,
            output_path=output_path,
            gene_output_path=gene_output_path,
            summary_path=summary_path,
            features=len(case_ids),
            mapped_features=mapped_features,
            significant_features=significant_features,
            genes=gene_count,
            significant_genes=significant_genes,
        )

    @staticmethod
    def _select_method(
        directory: Path,
        requested: str,
        *,
        sample_sheet: Path | None,
    ) -> tuple[str, dict[str, object]]:
        design_path = directory / "experimental-design.json"
        design: dict[str, object] = {}
        if design_path.exists():
            design = json.loads(design_path.read_text(encoding="utf-8"))
        selected = "linear-model" if sample_sheet is not None else requested
        if requested == "auto" and sample_sheet is None:
            selected = (
                "moderated"
                if design.get("assay") == "microarray"
                and design.get("independence") == "independent"
                else "welch"
            )
        if selected == "moderated" and design.get("independence") == "repeated":
            raise GeoApiError(
                "repeated samples require a blocked model; the two-group "
                "moderated backend is not valid"
            )
        details: dict[str, object] = {
            "selected": selected,
            "requested": requested,
            "name": (
                "limma-style moderated two-group t-test"
                if selected == "moderated"
                else "moderated general linear model"
                if selected == "linear-model"
                else "Welch independent two-sample t-test"
            ),
            "native_limma": False,
            "modeled_covariates": [],
        }
        declared = design.get("covariates", [])
        if isinstance(declared, list):
            details["declared_but_unmodeled_covariates"] = declared
        return selected, details

    def _write_gene_results(
        self,
        directory: Path,
        *,
        probe_ids: tuple[str, ...],
        annotations: dict[str, tuple[str, ...]],
        differences: np.ndarray,
        p_values: np.ndarray,
        alpha: float,
        min_abs_difference: float,
    ) -> tuple[Path, int, int]:
        grouped: dict[str, list[tuple[str, float, float]]] = {}
        for probe_id, difference, p_value in zip(
            probe_ids, differences, p_values, strict=True
        ):
            for gene_symbol in annotations.get(probe_id, ()):
                grouped.setdefault(gene_symbol, []).append(
                    (probe_id, float(difference), float(p_value))
                )

        genes = tuple(sorted(grouped))
        gene_effects = np.asarray(
            [np.median([probe[1] for probe in grouped[gene]]) for gene in genes],
            dtype=float,
        )
        gene_p_values = np.asarray(
            [
                self._simes(
                    np.asarray(
                        [probe[2] for probe in grouped[gene]],
                        dtype=float,
                    )
                )
                for gene in genes
            ],
            dtype=float,
        )
        gene_adjusted = self._benjamini_hochberg(gene_p_values)
        order = np.lexsort((-np.abs(gene_effects), gene_adjusted))
        significant = (gene_adjusted <= alpha) & (
            np.abs(gene_effects) >= min_abs_difference
        )
        output_path = directory / "gene-level-results.tsv"
        with output_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "gene_symbol",
                    "probe_count",
                    "probe_ids",
                    "median_mean_difference",
                    "direction",
                    "simes_p_value",
                    "adjusted_p_value",
                    "significant",
                )
            )
            for index in order:
                gene = genes[index]
                probes = grouped[gene]
                effect = gene_effects[index]
                direction = (
                    "higher_in_case"
                    if effect > 0
                    else "lower_in_case"
                    if effect < 0
                    else "unchanged"
                )
                writer.writerow(
                    (
                        gene,
                        len(probes),
                        "|".join(probe[0] for probe in probes),
                        self._number(effect),
                        direction,
                        self._number(gene_p_values[index]),
                        self._number(gene_adjusted[index]),
                        str(bool(significant[index])).lower(),
                    )
                )
        return output_path, len(genes), int(np.sum(significant))

    @staticmethod
    def _read_matrix(
        path: Path,
    ) -> tuple[tuple[str, ...], tuple[str, ...], np.ndarray]:
        if not path.exists():
            raise GeoApiError(f"prepared matrix is missing: {path}")
        identifiers: list[str] = []
        values: list[list[float]] = []
        try:
            with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
                reader = csv.reader(source, delimiter="\t")
                header: list[str] = next(reader)
                if len(header) < 2:
                    raise GeoApiError(f"matrix has no sample columns: {path}")
                sample_ids = tuple(header[1:])
                expected = len(header)
                for row in reader:
                    if len(row) != expected:
                        raise GeoApiError(f"inconsistent matrix column count in {path}")
                    identifiers.append(row[0])
                    values.append([float(value) for value in row[1:]])
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            if isinstance(error, GeoApiError):
                raise
            raise GeoApiError(f"cannot read numeric matrix {path}: {error}") from error
        if not identifiers:
            raise GeoApiError(f"matrix has no expression features: {path}")
        return (
            tuple(identifiers),
            sample_ids,
            np.asarray(values, dtype=float),
        )

    @staticmethod
    def _read_annotations(path: Path) -> dict[str, tuple[str, ...]]:
        annotations: dict[str, tuple[str, ...]] = {}
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as source:
                reader = DifferentialAnalyzer._annotation_rows(source)
                header = next(reader)
                id_index = header.index("ID")
                symbol_index = header.index("Gene symbol")
                for row in reader:
                    if len(row) <= max(id_index, symbol_index):
                        continue
                    symbols = tuple(
                        dict.fromkeys(
                            symbol.strip()
                            for symbol in row[symbol_index].split("///")
                            if symbol.strip() and symbol.strip() != "---"
                        )
                    )
                    if symbols:
                        annotations[row[id_index]] = symbols
        except (OSError, UnicodeError, csv.Error, ValueError, StopIteration) as error:
            raise GeoApiError(
                f"cannot read platform annotation {path}: {error}"
            ) from error
        return annotations

    @staticmethod
    def _annotation_rows(source: TextIO) -> Iterator[list[str]]:
        yield from csv.reader(
            (line for line in source if not line.startswith(("#", "!", "^"))),
            delimiter="\t",
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

    @staticmethod
    def _simes(p_values: np.ndarray) -> float:
        ordered = np.sort(p_values)
        count = len(ordered)
        scaled = ordered * count / np.arange(1, count + 1)
        return float(min(np.min(scaled), 1.0))

    @staticmethod
    def _number(value: float | np.floating[Any]) -> str:
        number = float(value)
        return f"{number:.12g}" if math.isfinite(number) else ""


def re_fullmatch_platform(value: str) -> bool:
    return value.startswith("GPL") and value[3:].isdigit()
