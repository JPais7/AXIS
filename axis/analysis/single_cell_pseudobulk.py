"""Streaming targeted pseudobulk analysis of 10x matrices in a tar archive."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class SingleCellPseudobulkRun:
    runs: int
    subjects: int
    comparisons: int
    output_path: Path
    pseudobulk_path: Path
    summary_path: Path


class SingleCellPseudobulkAnalyzer:
    """Aggregate cells to subjects before testing any expression difference."""

    def analyze(
        self,
        archive_path: str | Path,
        metadata_path: str | Path,
        *,
        target_genes: tuple[str, ...] = ("CD2", "IL2RB", "IKZF3"),
        cell_types: tuple[str, ...] = ("CD4 TCM", "CD8 TEM"),
        case_status: str = "AXI",
        control_status: str = "Healthy",
        minimum_cells: int = 20,
        output_root: str | Path = Path("data/single-cell/GSE194315/pseudobulk"),
    ) -> SingleCellPseudobulkRun:
        archive = Path(archive_path)
        metadata = Path(metadata_path)
        selected = self._metadata(
            metadata,
            cell_types=set(cell_types),
            statuses={case_status, control_status},
        )
        gene_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
        library_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        cell_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        seen_cells: set[str] = set()
        run_parts: dict[str, dict[str, object]] = defaultdict(dict)
        completed_runs = 0
        try:
            with tarfile.open(archive, "r|gz") as source:
                for member in source:
                    if not member.isfile():
                        continue
                    run, kind = self._member(member.name)
                    if run is None:
                        continue
                    extracted = source.extractfile(member)
                    if extracted is None:
                        continue
                    if kind == "barcodes":
                        run_parts[run]["barcodes"] = self._barcodes(
                            extracted, run, selected
                        )
                    elif kind == "features":
                        run_parts[run]["features"] = self._features(
                            extracted, set(target_genes)
                        )
                    elif kind == "matrix":
                        parts = run_parts[run]
                        barcodes = parts.get("barcodes")
                        features = parts.get("features")
                        if not isinstance(barcodes, dict) or not isinstance(
                            features, dict
                        ):
                            raise GeoApiError(f"archive order is invalid for run {run}")
                        self._matrix(
                            extracted,
                            barcodes=barcodes,
                            features=features,
                            gene_counts=gene_counts,
                            library_counts=library_counts,
                            cell_counts=cell_counts,
                            seen_cells=seen_cells,
                        )
                        completed_runs += 1
                        del run_parts[run]
        except (OSError, tarfile.TarError, EOFError) as error:
            raise GeoApiError(
                f"cannot stream 10x archive {archive}: {error}"
            ) from error

        pseudobulk_rows = self._pseudobulk_rows(
            gene_counts,
            library_counts,
            cell_counts,
            genes=target_genes,
        )
        results = self._results(
            pseudobulk_rows,
            genes=target_genes,
            cell_types=cell_types,
            case_status=case_status,
            control_status=control_status,
            minimum_cells=minimum_cells,
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "targeted-single-cell-results.tsv"
        self._write(output_path, results)
        pseudobulk_path = destination / "targeted-pseudobulk.tsv"
        self._write(pseudobulk_path, pseudobulk_rows)
        subjects = {str(row["subject"]) for row in pseudobulk_rows}
        summary_path = destination / "targeted-single-cell-analysis.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "targeted_subject_level_pseudobulk",
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE194315",
                    "archive_path": str(archive),
                    "archive_checksum": ("sha256:" + self._checksum(archive)),
                    "metadata_path": str(metadata),
                    "runs": completed_runs,
                    "matched_cells": len(seen_cells),
                    "subjects": len(subjects),
                    "target_genes": list(target_genes),
                    "cell_types": list(cell_types),
                    "case_status": case_status,
                    "control_status": control_status,
                    "statistical_unit": "subject",
                    "normalisation": "log2(raw pseudobulk CPM + 0.5)",
                    "test": "Welch independent two-sample t-test across subjects",
                    "multiple_testing": (
                        "Benjamini-Hochberg across predeclared target genes "
                        "within each cell type"
                    ),
                    "warning": (
                        "This targeted analysis is subject-aware but does not "
                        "replace a full count-model analysis with donor-level "
                        "clinical covariates."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SingleCellPseudobulkRun(
            runs=completed_runs,
            subjects=len(subjects),
            comparisons=len(results),
            output_path=output_path,
            pseudobulk_path=pseudobulk_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _metadata(
        path: Path, *, cell_types: set[str], statuses: set[str]
    ) -> dict[str, tuple[str, str, str]]:
        selected: dict[str, tuple[str, str, str]] = {}
        try:
            with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source, delimiter="\t"):
                    if (
                        row.get("IncludedInStudy") == "TRUE"
                        and row.get("CellType") in cell_types
                        and row.get("Status") in statuses
                    ):
                        selected[row["CellName"]] = (
                            row["Subject"],
                            row["Status"],
                            row["CellType"],
                        )
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read cell metadata {path}: {error}") from error
        return selected

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _member(name: str) -> tuple[str | None, str]:
        for suffix, kind in (
            (".barcodes.tsv.gz", "barcodes"),
            (".features.tsv.gz", "features"),
            (".matrix.mtx.gz", "matrix"),
        ):
            if name.endswith(suffix):
                return name.removesuffix(suffix), kind
        return None, ""

    @staticmethod
    def _text(fileobj: IO[bytes]) -> io.TextIOWrapper:
        return io.TextIOWrapper(gzip.GzipFile(fileobj=fileobj), encoding="utf-8")

    @classmethod
    def _barcodes(
        cls,
        fileobj: IO[bytes],
        run: str,
        selected: dict[str, tuple[str, str, str]],
    ) -> dict[int, tuple[str, str, str, str]]:
        result: dict[int, tuple[str, str, str, str]] = {}
        with cls._text(fileobj) as source:
            for index, line in enumerate(source, start=1):
                barcode = line.strip().removesuffix("-1")
                cell_name = f"{run}_{barcode}"
                annotation = selected.get(cell_name)
                if annotation is not None:
                    result[index] = (*annotation, cell_name)
        return result

    @classmethod
    def _features(cls, fileobj: IO[bytes], genes: set[str]) -> dict[int, str]:
        result: dict[int, str] = {}
        with cls._text(fileobj) as source:
            for index, line in enumerate(source, start=1):
                fields = line.rstrip("\n").split("\t")
                if len(fields) >= 2 and fields[1] in genes:
                    result[index] = fields[1]
        return result

    @classmethod
    def _matrix(
        cls,
        fileobj: IO[bytes],
        *,
        barcodes: dict[int, tuple[str, str, str, str]],
        features: dict[int, str],
        gene_counts: dict[tuple[str, str, str, str], int],
        library_counts: dict[tuple[str, str, str], int],
        cell_counts: dict[tuple[str, str, str], int],
        seen_cells: set[str],
    ) -> None:
        dimensions_seen = False
        with cls._text(fileobj) as source:
            for line in source:
                if line.startswith("%"):
                    continue
                if not dimensions_seen:
                    dimensions_seen = True
                    continue
                fields = line.split()
                if len(fields) != 3:
                    continue
                feature_index, cell_index, raw_value = map(int, fields)
                annotation = barcodes.get(cell_index)
                if annotation is None:
                    continue
                subject, status, cell_type, cell_name = annotation
                group = (subject, status, cell_type)
                if cell_name not in seen_cells:
                    seen_cells.add(cell_name)
                    cell_counts[group] += 1
                library_counts[group] += raw_value
                gene = features.get(feature_index)
                if gene is not None:
                    gene_counts[(*group, gene)] += raw_value

    @staticmethod
    def _pseudobulk_rows(
        gene_counts: dict[tuple[str, str, str, str], int],
        library_counts: dict[tuple[str, str, str], int],
        cell_counts: dict[tuple[str, str, str], int],
        *,
        genes: tuple[str, ...],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for group, library in library_counts.items():
            subject, status, cell_type = group
            for gene in genes:
                count = gene_counts.get((*group, gene), 0)
                cpm = count / library * 1_000_000 if library else 0.0
                rows.append(
                    {
                        "subject": subject,
                        "status": status,
                        "cell_type": cell_type,
                        "gene_symbol": gene,
                        "cells": cell_counts[group],
                        "raw_pseudobulk_count": count,
                        "library_count": library,
                        "cpm": cpm,
                        "log2_cpm": math.log2(cpm + 0.5),
                    }
                )
        rows.sort(
            key=lambda row: (
                str(row["cell_type"]),
                str(row["gene_symbol"]),
                str(row["status"]),
                str(row["subject"]),
            )
        )
        return rows

    @staticmethod
    def _results(
        rows: list[dict[str, object]],
        *,
        genes: tuple[str, ...],
        cell_types: tuple[str, ...],
        case_status: str,
        control_status: str,
        minimum_cells: int,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for cell_type in cell_types:
            indices: list[int] = []
            p_values: list[float] = []
            for gene in genes:
                case = np.asarray(
                    [
                        float(str(row["log2_cpm"]))
                        for row in rows
                        if row["cell_type"] == cell_type
                        and row["gene_symbol"] == gene
                        and row["status"] == case_status
                        and int(str(row["cells"])) >= minimum_cells
                    ]
                )
                control = np.asarray(
                    [
                        float(str(row["log2_cpm"]))
                        for row in rows
                        if row["cell_type"] == cell_type
                        and row["gene_symbol"] == gene
                        and row["status"] == control_status
                        and int(str(row["cells"])) >= minimum_cells
                    ]
                )
                statistic, p_value = stats.ttest_ind(case, control, equal_var=False)
                effect = float(np.mean(case) - np.mean(control))
                results.append(
                    {
                        "gene_symbol": gene,
                        "cell_type": cell_type,
                        "case_subjects": len(case),
                        "control_subjects": len(control),
                        "case_mean_log2_cpm": float(np.mean(case)),
                        "control_mean_log2_cpm": float(np.mean(control)),
                        "log2_cpm_difference": effect,
                        "direction": (
                            "higher_in_case"
                            if effect > 0
                            else "lower_in_case"
                            if effect < 0
                            else "unchanged"
                        ),
                        "welch_statistic": float(statistic),
                        "p_value": float(p_value),
                        "adjusted_p_value": 1.0,
                    }
                )
                indices.append(len(results) - 1)
                p_values.append(float(p_value))
            adjusted = SingleCellPseudobulkAnalyzer._bh(p_values)
            for index, value in zip(indices, adjusted, strict=True):
                results[index]["adjusted_p_value"] = value
        return results

    @staticmethod
    def _bh(values: list[float]) -> list[float]:
        if not values:
            return []
        order = np.argsort(values)
        adjusted = np.empty(len(values), dtype=float)
        previous = 1.0
        for rank_index in range(len(values) - 1, -1, -1):
            original = int(order[rank_index])
            rank = rank_index + 1
            value = min(previous, values[original] * len(values) / rank)
            adjusted[original] = value
            previous = value
        return adjusted.tolist()

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
