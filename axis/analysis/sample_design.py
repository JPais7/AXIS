"""Load auditable sample sheets and construct full-rank design matrices."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class SampleDesign:
    matrix: np.ndarray
    columns: tuple[str, ...]
    contrast: np.ndarray
    sample_ids: tuple[str, ...]
    source_path: Path


class SampleDesignBuilder:
    """Aligns a sample sheet to expression columns and encodes covariates."""

    def build(
        self,
        path: str | Path,
        *,
        sample_ids: tuple[str, ...],
        covariates: tuple[str, ...] = (),
        subject_column: str | None = None,
    ) -> SampleDesign:
        source_path = Path(path)
        rows = self._read_rows(source_path)
        by_sample: dict[str, dict[str, str]] = {}
        for row in rows:
            sample_id = row.get("sample_id", "").strip()
            if not sample_id:
                raise GeoApiError("sample sheet contains an empty sample_id")
            if sample_id in by_sample:
                raise GeoApiError(f"duplicate sample_id in sample sheet: {sample_id}")
            by_sample[sample_id] = row
        missing = tuple(sample for sample in sample_ids if sample not in by_sample)
        extra = tuple(sample for sample in by_sample if sample not in sample_ids)
        if missing or extra:
            raise GeoApiError(
                f"sample sheet does not match the matrix; missing={missing}, "
                f"extra={extra}"
            )
        aligned = tuple(by_sample[sample] for sample in sample_ids)
        groups = tuple(row.get("group", "").strip().lower() for row in aligned)
        invalid_groups = tuple(sorted(set(groups) - {"case", "control"}))
        if invalid_groups:
            raise GeoApiError(f"group must be case or control, found {invalid_groups}")
        columns: list[np.ndarray] = [np.ones(len(aligned), dtype=float)]
        names = ["intercept"]
        group_column = np.asarray(
            [1.0 if group == "case" else 0.0 for group in groups],
            dtype=float,
        )
        if np.all(group_column == 0) or np.all(group_column == 1):
            raise GeoApiError("sample sheet requires both case and control groups")
        columns.append(group_column)
        names.append("group_case")
        for covariate in covariates:
            encoded, encoded_names = self._encode(aligned, covariate)
            columns.extend(encoded)
            names.extend(encoded_names)
        if subject_column is not None:
            encoded, encoded_names = self._encode(
                aligned,
                subject_column,
                force_categorical=True,
            )
            columns.extend(encoded)
            names.extend(encoded_names)
        matrix = np.column_stack(columns)
        rank = int(np.linalg.matrix_rank(matrix))
        if rank != matrix.shape[1]:
            raise GeoApiError(
                "design matrix is collinear; remove redundant covariates "
                "or subject effects"
            )
        if matrix.shape[0] - rank < 1:
            raise GeoApiError("design matrix has no residual degrees of freedom")
        contrast = np.zeros(matrix.shape[1], dtype=float)
        contrast[names.index("group_case")] = 1.0
        return SampleDesign(
            matrix=matrix,
            columns=tuple(names),
            contrast=contrast,
            sample_ids=sample_ids,
            source_path=source_path,
        )

    @staticmethod
    def _read_rows(path: Path) -> tuple[dict[str, str], ...]:
        try:
            with path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source, delimiter="\t")
                if reader.fieldnames is None:
                    raise GeoApiError("sample sheet has no header")
                required = {"sample_id", "group"}
                missing = required - set(reader.fieldnames)
                if missing:
                    raise GeoApiError(
                        f"sample sheet is missing columns {sorted(missing)}"
                    )
                return tuple(reader)
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(f"cannot read sample sheet {path}: {error}") from error

    def _encode(
        self,
        rows: tuple[dict[str, str], ...],
        name: str,
        *,
        force_categorical: bool = False,
    ) -> tuple[list[np.ndarray], list[str]]:
        values = tuple(row.get(name, "").strip() for row in rows)
        if any(not value for value in values):
            raise GeoApiError(f"covariate {name!r} contains missing values")
        if not force_categorical:
            try:
                numeric = np.asarray([float(value) for value in values])
            except ValueError:
                pass
            else:
                if np.all(numeric == numeric[0]):
                    raise GeoApiError(f"covariate {name!r} is constant")
                centered = numeric - np.mean(numeric)
                return [centered], [name]
        levels = tuple(sorted(set(values)))
        if len(levels) < 2:
            raise GeoApiError(f"covariate {name!r} is constant")
        encoded = [
            np.asarray([1.0 if value == level else 0.0 for value in values])
            for level in levels[1:]
        ]
        names = [f"{name}[{level}]" for level in levels[1:]]
        return encoded, names


def write_sample_sheet_template(
    sample_groups_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Create an editable sample sheet from a preparation manifest."""
    source_path = Path(sample_groups_path)
    destination = Path(output_path)
    with source_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(
            row
            for row in csv.DictReader(source, delimiter="\t")
            if row["group"] in {"case", "control"}
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("sample_id", "group", "subject", "sex", "age", "batch"))
        for row in rows:
            metadata = _characteristics(row.get("characteristics", ""))
            writer.writerow(
                (
                    row["accession"],
                    row["group"],
                    "",
                    metadata.get("sex", metadata.get("gender", "")),
                    metadata.get("age", ""),
                    metadata.get(
                        "batch",
                        metadata.get("set", _title_batch(row.get("title", ""))),
                    ),
                )
            )
    return destination


def _characteristics(value: str) -> dict[str, str]:
    """Parse GEO's pipe-separated ``key: value`` sample characteristics."""
    parsed: dict[str, str] = {}
    for item in value.split("|"):
        key, separator, item_value = item.partition(":")
        if separator and key.strip() and item_value.strip():
            normalized = key.strip().lower()
            if normalized in {"age (yr)", "age (years)", "age (year)"}:
                normalized = "age"
            parsed[normalized] = item_value.strip()
    return parsed


def _title_batch(value: str) -> str:
    """Recover array/chip identifiers such as ``AS [9963831033_D]``."""
    match = re.search(r"\[([^]_\s]+)_[^]]+\]\s*$", value)
    return match.group(1) if match is not None else ""
