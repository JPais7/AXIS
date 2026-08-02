"""Visual and numeric quality control for prepared expression matrices."""

from __future__ import annotations

import csv
import gzip
import json
import os
from dataclasses import dataclass
from pathlib import Path

_cache_root = Path(os.environ.get("AXIS_CACHE_DIR", ".axis-cache"))
_matplotlib_cache = _cache_root / "matplotlib"
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # type: ignore[import-untyped]  # noqa: E402

from axis.ingestion.geo import GSE_PATTERN, GeoApiError  # noqa: E402

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


@dataclass(frozen=True)
class QualityControlResult:
    accession: str
    output_directory: Path
    report_path: Path
    distribution_plot: Path
    pca_plot: Path
    correlation_plot: Path
    samples: int
    features: int
    outlier_samples: tuple[str, ...]


class ExpressionQualityControl:
    """Produces reproducible QC metrics and plots before inference."""

    def run(
        self,
        accession: str,
        *,
        data_root: str | Path = Path("data/geo"),
        max_features: int = 5000,
    ) -> tuple[QualityControlResult, ...]:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if max_features < 2:
            raise ValueError("max_features must be at least 2")
        prepared_root = Path(data_root) / accession / "prepared"
        directories = (
            tuple(
                path
                for path in sorted(prepared_root.iterdir())
                if path.is_dir()
                and (path / "case-matrix.tsv.gz").exists()
                and (path / "control-matrix.tsv.gz").exists()
            )
            if prepared_root.exists()
            else ()
        )
        if not directories:
            raise GeoApiError(
                f"no prepared case/control matrices found for {accession}"
            )
        return tuple(
            self._run_matrix(accession, directory, max_features=max_features)
            for directory in directories
        )

    def _run_matrix(
        self,
        accession: str,
        directory: Path,
        *,
        max_features: int,
    ) -> QualityControlResult:
        case_ids, case_features, case_values = self._read_matrix(
            directory / "case-matrix.tsv.gz"
        )
        control_ids, control_features, control_values = self._read_matrix(
            directory / "control-matrix.tsv.gz"
        )
        if case_features != control_features:
            raise GeoApiError("case and control QC matrices have different features")
        sample_ids = case_ids + control_ids
        groups = ("case",) * len(case_ids) + ("control",) * len(control_ids)
        values = np.column_stack((case_values, control_values))
        variances = np.var(values, axis=1, ddof=1)
        selected_count = min(max_features, len(variances))
        selected = np.argsort(variances)[-selected_count:]
        selected_values = values[selected]
        centered = selected_values - np.mean(selected_values, axis=1, keepdims=True)
        sample_matrix = centered.T
        u, singular, _ = np.linalg.svd(sample_matrix, full_matrices=False)
        scores = u * singular
        total_variance = float(np.sum(singular**2))
        explained = (
            singular**2 / total_variance
            if total_variance > 0
            else np.zeros_like(singular)
        )
        pc_count = min(3, scores.shape[1])
        distances = np.sqrt(np.sum(scores[:, :pc_count] ** 2, axis=1))
        median_distance = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median_distance)))
        threshold = median_distance + 3.0 * 1.4826 * mad if mad > 0 else float("inf")
        outliers = tuple(
            sample
            for sample, distance in zip(sample_ids, distances, strict=True)
            if distance > threshold
        )
        group_associations = self._group_associations(
            scores,
            case_count=len(case_ids),
            components=min(5, scores.shape[1]),
        )
        correlations = np.corrcoef(values.T)
        output_directory = directory / "qc"
        output_directory.mkdir(parents=True, exist_ok=True)
        distribution_plot = output_directory / "sample-distributions.png"
        pca_plot = output_directory / "pca.png"
        correlation_plot = output_directory / "sample-correlation.png"
        self._plot_distributions(
            values,
            sample_ids=sample_ids,
            groups=groups,
            path=distribution_plot,
        )
        self._plot_pca(
            scores,
            explained=explained,
            sample_ids=sample_ids,
            groups=groups,
            outliers=set(outliers),
            path=pca_plot,
        )
        self._plot_correlations(
            correlations,
            sample_ids=sample_ids,
            path=correlation_plot,
        )
        report_path = output_directory / "qc-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "accession": accession,
                    "matrix": directory.name,
                    "samples": len(sample_ids),
                    "case_samples": len(case_ids),
                    "control_samples": len(control_ids),
                    "features": len(case_features),
                    "pca_features": selected_count,
                    "explained_variance_ratio": [
                        float(value) for value in explained[:5]
                    ],
                    "group_associations": group_associations,
                    "outlier_method": (
                        "distance in first three PCs > median + 3 scaled MAD"
                    ),
                    "outlier_threshold": threshold,
                    "outlier_samples": outliers,
                    "minimum_sample_correlation": float(
                        np.min(correlations[np.triu_indices_from(correlations, 1)])
                    ),
                    "plots": {
                        "distributions": distribution_plot.name,
                        "pca": pca_plot.name,
                        "correlation": correlation_plot.name,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return QualityControlResult(
            accession=accession,
            output_directory=output_directory,
            report_path=report_path,
            distribution_plot=distribution_plot,
            pca_plot=pca_plot,
            correlation_plot=correlation_plot,
            samples=len(sample_ids),
            features=len(case_features),
            outlier_samples=outliers,
        )

    @staticmethod
    def _read_matrix(
        path: Path,
    ) -> tuple[tuple[str, ...], tuple[str, ...], np.ndarray]:
        features: list[str] = []
        values: list[list[float]] = []
        try:
            with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
                reader = csv.reader(source, delimiter="\t")
                header = next(reader)
                sample_ids = tuple(header[1:])
                for row in reader:
                    features.append(row[0])
                    values.append([float(value) for value in row[1:]])
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            raise GeoApiError(f"cannot read QC matrix {path}: {error}") from error
        if len(sample_ids) < 2 or not features:
            raise GeoApiError(f"QC matrix is empty or undersampled: {path}")
        return sample_ids, tuple(features), np.asarray(values, dtype=float)

    @staticmethod
    def _group_associations(
        scores: np.ndarray,
        *,
        case_count: int,
        components: int,
    ) -> list[dict[str, float | int]]:
        results: list[dict[str, float | int]] = []
        for index in range(components):
            test = stats.ttest_ind(
                scores[:case_count, index],
                scores[case_count:, index],
                equal_var=False,
            )
            results.append(
                {
                    "component": index + 1,
                    "statistic": float(test.statistic),
                    "p_value": float(test.pvalue),
                }
            )
        return results

    @staticmethod
    def _plot_distributions(
        values: np.ndarray,
        *,
        sample_ids: tuple[str, ...],
        groups: tuple[str, ...],
        path: Path,
    ) -> None:
        figure, axis = plt.subplots(figsize=(max(8, len(sample_ids) * 0.38), 5))
        box = axis.boxplot(
            [values[:, index] for index in range(values.shape[1])],
            tick_labels=sample_ids,
            patch_artist=True,
            showfliers=False,
        )
        colors = {"case": "#d95f02", "control": "#1b9e77"}
        for patch, group in zip(box["boxes"], groups, strict=True):
            patch.set_facecolor(colors[group])
            patch.set_alpha(0.65)
        axis.set_ylabel("Processed expression value")
        axis.set_title("Sample distributions")
        axis.tick_params(axis="x", rotation=75, labelsize=7)
        axis.grid(axis="y", alpha=0.2)
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)

    @staticmethod
    def _plot_pca(
        scores: np.ndarray,
        *,
        explained: np.ndarray,
        sample_ids: tuple[str, ...],
        groups: tuple[str, ...],
        outliers: set[str],
        path: Path,
    ) -> None:
        figure, axis = plt.subplots(figsize=(7, 6))
        styles = {
            "case": ("#d95f02", "o"),
            "control": ("#1b9e77", "s"),
        }
        for group in ("case", "control"):
            indexes = [index for index, value in enumerate(groups) if value == group]
            color, marker = styles[group]
            axis.scatter(
                scores[indexes, 0],
                scores[indexes, 1],
                color=color,
                marker=marker,
                label=group,
                s=45,
            )
        for index, sample_id in enumerate(sample_ids):
            axis.annotate(
                f"{sample_id}{'*' if sample_id in outliers else ''}",
                (scores[index, 0], scores[index, 1]),
                xytext=(4, 3),
                textcoords="offset points",
                fontsize=7,
            )
        axis.set_xlabel(f"PC1 ({explained[0] * 100:.1f}%)")
        axis.set_ylabel(f"PC2 ({explained[1] * 100:.1f}%)")
        axis.set_title("PCA of most variable features")
        axis.legend(frameon=False)
        axis.grid(alpha=0.2)
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)

    @staticmethod
    def _plot_correlations(
        correlations: np.ndarray,
        *,
        sample_ids: tuple[str, ...],
        path: Path,
    ) -> None:
        size = max(6, len(sample_ids) * 0.35)
        figure, axis = plt.subplots(figsize=(size, size))
        image = axis.imshow(correlations, vmin=-1, vmax=1, cmap="coolwarm")
        axis.set_xticks(range(len(sample_ids)), sample_ids, rotation=90, fontsize=7)
        axis.set_yticks(range(len(sample_ids)), sample_ids, fontsize=7)
        axis.set_title("Sample correlation")
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
        figure.tight_layout()
        figure.savefig(path, dpi=160)
        plt.close(figure)
