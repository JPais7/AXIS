"""Prepare downloaded GEO Series Matrix files for case/control analysis."""

from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class PreparedMatrix:
    source_path: Path
    output_directory: Path
    sample_manifest_path: Path
    case_matrix_path: Path
    control_matrix_path: Path
    case_samples: int
    control_samples: int
    unassigned_samples: int
    ambiguous_samples: int
    excluded_samples: int
    feature_rows: int


@dataclass(frozen=True)
class GeoPreparation:
    accession: str
    matrices: tuple[PreparedMatrix, ...]


@dataclass(frozen=True)
class _Sample:
    accession: str
    title: str
    source: str
    characteristics: tuple[str, ...]

    @property
    def searchable_text(self) -> str:
        return " | ".join(
            (self.accession, self.title, self.source, *self.characteristics)
        )


class GeoMatrixPreparer:
    """Separates expression columns using auditable case/control patterns."""

    def prepare(
        self,
        accession: str,
        *,
        data_root: str | Path = Path("data/geo"),
        case_pattern: str,
        control_pattern: str,
        include_pattern: str | None = None,
    ) -> GeoPreparation:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        case_regex = self._compile_pattern(case_pattern, "case")
        control_regex = self._compile_pattern(control_pattern, "control")
        include_regex = (
            self._compile_pattern(include_pattern, "include")
            if include_pattern is not None
            else None
        )
        study_directory = Path(data_root) / accession
        matrix_paths = tuple(
            sorted(study_directory.glob(f"{accession}*_series_matrix.txt.gz"))
        )
        if not matrix_paths:
            raise GeoApiError(
                f"no downloaded Series Matrix files found for {accession}; "
                f"run 'axis download {accession}' first"
            )
        matrices = tuple(
            self._prepare_matrix(
                path,
                case_regex=case_regex,
                control_regex=control_regex,
                include_regex=include_regex,
            )
            for path in matrix_paths
        )
        return GeoPreparation(accession=accession, matrices=matrices)

    @staticmethod
    def _compile_pattern(value: str, group: str) -> re.Pattern[str]:
        if not value.strip():
            raise ValueError(f"{group} pattern must not be empty")
        try:
            return re.compile(value, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"invalid {group} pattern: {error}") from error

    def _prepare_matrix(
        self,
        source_path: Path,
        *,
        case_regex: re.Pattern[str],
        control_regex: re.Pattern[str],
        include_regex: re.Pattern[str] | None,
    ) -> PreparedMatrix:
        samples = self._read_samples(source_path)
        groups = tuple(
            (
                "excluded"
                if include_regex is not None
                and include_regex.search(sample.searchable_text) is None
                else self._classify(
                    sample.searchable_text,
                    case_regex=case_regex,
                    control_regex=control_regex,
                )
            )
            for sample in samples
        )
        output_directory = (
            source_path.parent / "prepared" / source_path.name.removesuffix(".txt.gz")
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        sample_manifest_path = output_directory / "sample-groups.tsv"
        self._write_sample_manifest(sample_manifest_path, samples, groups)
        case_matrix_path = output_directory / "case-matrix.tsv.gz"
        control_matrix_path = output_directory / "control-matrix.tsv.gz"
        feature_rows = self._write_group_matrices(
            source_path,
            samples=samples,
            groups=groups,
            case_path=case_matrix_path,
            control_path=control_matrix_path,
        )
        summary_path = output_directory / "preparation.json"
        summary_path.write_text(
            json.dumps(
                {
                    "source_path": str(source_path),
                    "case_pattern": case_regex.pattern,
                    "control_pattern": control_regex.pattern,
                    "include_pattern": (
                        include_regex.pattern if include_regex is not None else None
                    ),
                    "case_samples": groups.count("case"),
                    "control_samples": groups.count("control"),
                    "unassigned_samples": groups.count("unassigned"),
                    "ambiguous_samples": groups.count("ambiguous"),
                    "excluded_samples": groups.count("excluded"),
                    "feature_rows": feature_rows,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return PreparedMatrix(
            source_path=source_path,
            output_directory=output_directory,
            sample_manifest_path=sample_manifest_path,
            case_matrix_path=case_matrix_path,
            control_matrix_path=control_matrix_path,
            case_samples=groups.count("case"),
            control_samples=groups.count("control"),
            unassigned_samples=groups.count("unassigned"),
            ambiguous_samples=groups.count("ambiguous"),
            excluded_samples=groups.count("excluded"),
            feature_rows=feature_rows,
        )

    @staticmethod
    def _classify(
        text: str,
        *,
        case_regex: re.Pattern[str],
        control_regex: re.Pattern[str],
    ) -> str:
        is_case = case_regex.search(text) is not None
        is_control = control_regex.search(text) is not None
        if is_case and is_control:
            return "ambiguous"
        if is_case:
            return "case"
        if is_control:
            return "control"
        return "unassigned"

    def _read_samples(self, source_path: Path) -> tuple[_Sample, ...]:
        metadata: dict[str, list[list[str]]] = {}
        try:
            with gzip.open(source_path, "rt", encoding="utf-8") as source:
                for line in source:
                    if line.startswith("!series_matrix_table_begin"):
                        break
                    if not line.startswith("!Sample_"):
                        continue
                    values = next(csv.reader([line], delimiter="\t"))
                    metadata.setdefault(values[0], []).append(
                        [self._clean(value) for value in values[1:]]
                    )
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(f"cannot read matrix {source_path}: {error}") from error

        accessions = self._metadata_row(metadata, "!Sample_geo_accession")
        titles = self._metadata_row(metadata, "!Sample_title", len(accessions))
        sources = self._metadata_row(
            metadata, "!Sample_source_name_ch1", len(accessions)
        )
        characteristic_rows = metadata.get("!Sample_characteristics_ch1", [])
        for row in characteristic_rows:
            if len(row) != len(accessions):
                raise GeoApiError(f"inconsistent sample metadata in {source_path.name}")
        return tuple(
            _Sample(
                accession=sample_accession,
                title=titles[index],
                source=sources[index],
                characteristics=tuple(
                    row[index] for row in characteristic_rows if row[index]
                ),
            )
            for index, sample_accession in enumerate(accessions)
        )

    @staticmethod
    def _metadata_row(
        metadata: dict[str, list[list[str]]],
        key: str,
        expected: int | None = None,
    ) -> list[str]:
        rows = metadata.get(key)
        if not rows:
            if expected is None:
                raise GeoApiError(f"Series Matrix is missing {key}")
            return [""] * expected
        values = rows[0]
        if expected is not None and len(values) != expected:
            raise GeoApiError("inconsistent sample metadata column counts")
        return values

    @staticmethod
    def _clean(value: str) -> str:
        return value.strip().strip('"')

    @staticmethod
    def _write_sample_manifest(
        path: Path,
        samples: tuple[_Sample, ...],
        groups: tuple[str, ...],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(
                ("accession", "group", "title", "source", "characteristics")
            )
            for sample, group in zip(samples, groups, strict=True):
                writer.writerow(
                    (
                        sample.accession,
                        group,
                        sample.title,
                        sample.source,
                        " | ".join(sample.characteristics),
                    )
                )

    def _write_group_matrices(
        self,
        source_path: Path,
        *,
        samples: tuple[_Sample, ...],
        groups: tuple[str, ...],
        case_path: Path,
        control_path: Path,
    ) -> int:
        feature_rows = 0
        try:
            with (
                gzip.open(source_path, "rt", encoding="utf-8") as source,
                gzip.open(case_path, "wt", encoding="utf-8", newline="") as case_file,
                gzip.open(
                    control_path, "wt", encoding="utf-8", newline=""
                ) as control_file,
            ):
                feature_rows = self._copy_table(
                    source,
                    samples=samples,
                    groups=groups,
                    case_file=case_file,
                    control_file=control_file,
                )
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(
                f"cannot prepare matrix {source_path}: {error}"
            ) from error
        return feature_rows

    def _copy_table(
        self,
        source: TextIO,
        *,
        samples: tuple[_Sample, ...],
        groups: tuple[str, ...],
        case_file: TextIO,
        control_file: TextIO,
    ) -> int:
        for line in source:
            if line.startswith("!series_matrix_table_begin"):
                break
        else:
            raise GeoApiError("Series Matrix has no expression table")

        reader = csv.reader(source, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as error:
            raise GeoApiError("Series Matrix expression table is empty") from error
        clean_header = tuple(self._clean(value) for value in header)
        sample_accessions = tuple(sample.accession for sample in samples)
        if clean_header[1:] != sample_accessions:
            raise GeoApiError(
                "expression columns do not match the sample metadata order"
            )

        case_indexes = tuple(
            index + 1 for index, group in enumerate(groups) if group == "case"
        )
        control_indexes = tuple(
            index + 1 for index, group in enumerate(groups) if group == "control"
        )
        case_writer = csv.writer(case_file, delimiter="\t", lineterminator="\n")
        control_writer = csv.writer(control_file, delimiter="\t", lineterminator="\n")
        case_writer.writerow(
            (clean_header[0], *(clean_header[i] for i in case_indexes))
        )
        control_writer.writerow(
            (clean_header[0], *(clean_header[i] for i in control_indexes))
        )
        feature_rows = 0
        for row in reader:
            if row and row[0].startswith("!series_matrix_table_end"):
                break
            if len(row) != len(clean_header):
                raise GeoApiError("inconsistent expression table column counts")
            case_writer.writerow((self._clean(row[0]), *(row[i] for i in case_indexes)))
            control_writer.writerow(
                (self._clean(row[0]), *(row[i] for i in control_indexes))
            )
            feature_rows += 1
        return feature_rows
