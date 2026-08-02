"""Differential analysis for normalized RNA-seq abundance tables."""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class NormalizedRnaSeqAnalysis:
    accession: str
    output_directory: Path
    transcript_output_path: Path
    gene_output_path: Path
    summary_path: Path
    transcripts: int
    genes: int
    significant_genes: int


@dataclass(frozen=True)
class _TranscriptResult:
    identifier: str
    gene: str
    effect: float
    p_value: float
    adjusted_p_value: float


class NormalizedRnaSeqAnalyzer:
    """Analyzes non-negative, normalized RNA-seq abundances."""

    def analyze(
        self,
        accession: str,
        *,
        input_path: str | Path,
        case_pattern: str,
        control_pattern: str,
        data_root: str | Path = Path("data/geo"),
        gene_column: str = "Gene",
        transcript_column: str = "mRNA",
        exclude_column_pattern: str | None = None,
        analysis_label: str | None = None,
        alpha: float = 0.05,
        min_abs_log2_fold_change: float = 0.0,
    ) -> NormalizedRnaSeqAnalysis:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        case_regex = self._compile(case_pattern, "case")
        control_regex = self._compile(control_pattern, "control")
        exclude_regex = (
            self._compile(exclude_column_pattern, "exclude")
            if exclude_column_pattern is not None
            else None
        )
        if analysis_label is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*", analysis_label
        ):
            raise ValueError("analysis label contains unsupported characters")
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be between 0 and 1")
        if min_abs_log2_fold_change < 0:
            raise ValueError("minimum absolute log2 fold change must not be negative")

        (
            identifiers,
            genes,
            case_values,
            control_values,
            case_columns,
            control_columns,
        ) = self._read_table(
            Path(input_path),
            case_regex=case_regex,
            control_regex=control_regex,
            gene_column=gene_column,
            transcript_column=transcript_column,
            exclude_regex=exclude_regex,
        )
        log_case = np.log2(case_values + 1.0)
        log_control = np.log2(control_values + 1.0)
        effects = np.mean(log_case, axis=1) - np.mean(log_control, axis=1)
        test = stats.ttest_ind(
            log_case,
            log_control,
            axis=1,
            equal_var=False,
            nan_policy="omit",
        )
        p_values = np.asarray(test.pvalue, dtype=float)
        p_values = np.where(np.isfinite(p_values), p_values, 1.0)
        adjusted = self._benjamini_hochberg(p_values)
        directory_name = "rnaseq-normalized"
        if analysis_label:
            directory_name = f"{directory_name}-{analysis_label}"
        output_directory = Path(data_root) / accession / "prepared" / directory_name
        output_directory.mkdir(parents=True, exist_ok=True)
        self._write_qc_matrix(
            output_directory / "case-matrix.tsv.gz",
            sample_ids=case_columns,
            feature_ids=identifiers,
            values=log_case,
        )
        self._write_qc_matrix(
            output_directory / "control-matrix.tsv.gz",
            sample_ids=control_columns,
            feature_ids=identifiers,
            values=log_control,
        )
        transcript_output_path = output_directory / "differential-expression.tsv"
        self._write_transcripts(
            transcript_output_path,
            identifiers=identifiers,
            genes=genes,
            effects=effects,
            p_values=p_values,
            adjusted=adjusted,
            alpha=alpha,
            min_abs_effect=min_abs_log2_fold_change,
        )
        gene_output_path, gene_count, significant_genes = self._write_genes(
            output_directory / "gene-level-results.tsv",
            identifiers=identifiers,
            genes=genes,
            effects=effects,
            p_values=p_values,
            alpha=alpha,
            min_abs_effect=min_abs_log2_fold_change,
        )
        summary_path = output_directory / "differential-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "accession": accession,
                    "input_path": str(input_path),
                    "data_type": "normalized RNA-seq abundance",
                    "transformation": "log2(value + 1)",
                    "method": "Welch independent two-sample t-test",
                    "multiple_testing": "Benjamini-Hochberg",
                    "case_columns": case_columns,
                    "control_columns": control_columns,
                    "excluded_column_pattern": (
                        exclude_regex.pattern if exclude_regex is not None else None
                    ),
                    "analysis_label": analysis_label,
                    "case_samples": len(case_columns),
                    "control_samples": len(control_columns),
                    "alpha": alpha,
                    "minimum_absolute_log2_fold_change": (min_abs_log2_fold_change),
                    "transcripts": len(identifiers),
                    "genes": gene_count,
                    "significant_genes": significant_genes,
                    "gene_aggregation": {
                        "effect": "median transcript log2 fold change",
                        "p_value": "Simes combination across transcripts",
                        "multiple_testing": "Benjamini-Hochberg across genes",
                    },
                    "warning": (
                        "Exploratory analysis of normalized abundance, not a "
                        "raw-count model. Confirm normalization and study design; "
                        "prefer DESeq2/edgeR for integer raw counts."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return NormalizedRnaSeqAnalysis(
            accession=accession,
            output_directory=output_directory,
            transcript_output_path=transcript_output_path,
            gene_output_path=gene_output_path,
            summary_path=summary_path,
            transcripts=len(identifiers),
            genes=gene_count,
            significant_genes=significant_genes,
        )

    @staticmethod
    def _write_qc_matrix(
        path: Path,
        *,
        sample_ids: tuple[str, ...],
        feature_ids: tuple[str, ...],
        values: np.ndarray,
    ) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(("feature_id", *sample_ids))
            for feature, row in zip(feature_ids, values, strict=True):
                writer.writerow((feature, *(f"{value:.12g}" for value in row)))

    def _read_table(
        self,
        path: Path,
        *,
        case_regex: re.Pattern[str],
        control_regex: re.Pattern[str],
        gene_column: str,
        transcript_column: str,
        exclude_regex: re.Pattern[str] | None,
    ) -> tuple[
        tuple[str, ...],
        tuple[str, ...],
        np.ndarray,
        np.ndarray,
        tuple[str, ...],
        tuple[str, ...],
    ]:
        try:
            with self._open(path) as source:
                reader = csv.DictReader(source, delimiter="\t")
                if reader.fieldnames is None:
                    raise GeoApiError(f"RNA-seq table has no header: {path}")
                fields = tuple(reader.fieldnames)
                for required in (gene_column, transcript_column):
                    if required not in fields:
                        raise GeoApiError(
                            f"RNA-seq table is missing column {required!r}"
                        )
                case_columns = tuple(
                    field
                    for field in fields
                    if case_regex.search(field)
                    and (exclude_regex is None or exclude_regex.search(field) is None)
                )
                control_columns = tuple(
                    field
                    for field in fields
                    if control_regex.search(field)
                    and (exclude_regex is None or exclude_regex.search(field) is None)
                )
                overlap = set(case_columns) & set(control_columns)
                if overlap:
                    raise GeoApiError(
                        f"sample columns match both groups: {sorted(overlap)}"
                    )
                if len(case_columns) < 2 or len(control_columns) < 2:
                    raise GeoApiError(
                        "RNA-seq analysis requires at least two columns per group"
                    )
                identifiers: list[str] = []
                genes: list[str] = []
                case_values: list[list[float]] = []
                control_values: list[list[float]] = []
                for row in reader:
                    identifier = row[transcript_column].strip()
                    gene = row[gene_column].strip()
                    if not identifier or not gene or gene == "---":
                        continue
                    case_row = [float(row[column]) for column in case_columns]
                    control_row = [float(row[column]) for column in control_columns]
                    if any(value < 0 for value in (*case_row, *control_row)):
                        raise GeoApiError(
                            "normalized RNA-seq abundances must be non-negative"
                        )
                    identifiers.append(identifier)
                    genes.append(gene)
                    case_values.append(case_row)
                    control_values.append(control_row)
        except (OSError, UnicodeError, csv.Error, KeyError, ValueError) as error:
            if isinstance(error, GeoApiError):
                raise
            raise GeoApiError(f"cannot read RNA-seq table {path}: {error}") from error
        if not identifiers:
            raise GeoApiError(f"RNA-seq table has no usable records: {path}")
        return (
            tuple(identifiers),
            tuple(genes),
            np.asarray(case_values, dtype=float),
            np.asarray(control_values, dtype=float),
            case_columns,
            control_columns,
        )

    @staticmethod
    def _open(path: Path) -> TextIO:
        if path.suffix == ".gz":
            return gzip.open(
                path,
                "rt",
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            )
        return path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        )

    def _write_transcripts(
        self,
        path: Path,
        *,
        identifiers: tuple[str, ...],
        genes: tuple[str, ...],
        effects: np.ndarray,
        p_values: np.ndarray,
        adjusted: np.ndarray,
        alpha: float,
        min_abs_effect: float,
    ) -> None:
        order = np.lexsort((-np.abs(effects), adjusted))
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(
                (
                    "transcript_id",
                    "gene_symbol",
                    "log2_fold_change",
                    "p_value",
                    "adjusted_p_value",
                    "significant",
                )
            )
            for index in order:
                writer.writerow(
                    (
                        identifiers[index],
                        genes[index],
                        self._number(effects[index]),
                        self._number(p_values[index]),
                        self._number(adjusted[index]),
                        str(
                            bool(
                                adjusted[index] <= alpha
                                and abs(effects[index]) >= min_abs_effect
                            )
                        ).lower(),
                    )
                )

    def _write_genes(
        self,
        path: Path,
        *,
        identifiers: tuple[str, ...],
        genes: tuple[str, ...],
        effects: np.ndarray,
        p_values: np.ndarray,
        alpha: float,
        min_abs_effect: float,
    ) -> tuple[Path, int, int]:
        grouped: dict[str, list[_TranscriptResult]] = {}
        for identifier, gene, effect, p_value in zip(
            identifiers, genes, effects, p_values, strict=True
        ):
            grouped.setdefault(gene, []).append(
                _TranscriptResult(
                    identifier=identifier,
                    gene=gene,
                    effect=float(effect),
                    p_value=float(p_value),
                    adjusted_p_value=1.0,
                )
            )
        gene_names = tuple(sorted(grouped))
        gene_effects = np.asarray(
            [
                np.median([result.effect for result in grouped[gene]])
                for gene in gene_names
            ],
            dtype=float,
        )
        gene_p_values = np.asarray(
            [
                self._simes(
                    np.asarray(
                        [result.p_value for result in grouped[gene]],
                        dtype=float,
                    )
                )
                for gene in gene_names
            ],
            dtype=float,
        )
        gene_adjusted = self._benjamini_hochberg(gene_p_values)
        significant = (gene_adjusted <= alpha) & (
            np.abs(gene_effects) >= min_abs_effect
        )
        order = np.lexsort((-np.abs(gene_effects), gene_adjusted))
        with path.open("w", encoding="utf-8", newline="") as output:
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
                gene = gene_names[index]
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
                        len(grouped[gene]),
                        "|".join(result.identifier for result in grouped[gene]),
                        self._number(effect),
                        direction,
                        self._number(gene_p_values[index]),
                        self._number(gene_adjusted[index]),
                        str(bool(significant[index])).lower(),
                    )
                )
        return path, len(gene_names), int(np.sum(significant))

    @staticmethod
    def _compile(value: str, group: str) -> re.Pattern[str]:
        if not value.strip():
            raise ValueError(f"{group} column pattern must not be empty")
        try:
            return re.compile(value, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"invalid {group} column pattern: {error}") from error

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
        return float(
            min(
                np.min(ordered * count / np.arange(1, count + 1)),
                1.0,
            )
        )

    @staticmethod
    def _number(value: float | np.floating[Any]) -> str:
        number = float(value)
        return f"{number:.12g}" if math.isfinite(number) else ""
