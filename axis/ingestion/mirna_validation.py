"""Validate a deposited GEO microRNA cohort before statistical analysis."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class MirnaCohortValidation:
    accession: str
    participants: int
    radiographic_axspa: int
    nonradiographic_axspa: int
    healthy_controls: int
    mirnas: int
    complete_age: int
    complete_sex: int
    complete_crp: int
    raw_counts_are_integers: bool
    empty_raw_libraries: tuple[str, ...]
    normalized_missing_values: int
    sample_order_matches: bool
    feature_order_matches: bool
    eligible_for_analysis: bool
    sample_sheet_path: Path
    report_path: Path


class MirnaCohortValidator:
    """Cross-check metadata, raw counts and normalized microRNA values."""

    def validate(
        self,
        accession: str,
        *,
        data_root: str | Path = Path("data/geo"),
    ) -> MirnaCohortValidation:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        root = Path(data_root) / accession
        matrix = root / f"{accession}_series_matrix.txt.gz"
        raw = root / "supplementary" / f"{accession}_seq_raw.txt.gz"
        normalized = root / "supplementary" / f"{accession}_seq_norm.txt.gz"
        for path in (matrix, raw, normalized):
            if not path.exists():
                raise GeoApiError(f"required microRNA file is missing: {path}")

        metadata = self._metadata(matrix)
        (
            raw_samples,
            raw_features,
            raw_integer,
            raw_missing,
            empty_raw,
        ) = self._expression(raw, integers=True)
        norm_samples, norm_features, _, norm_missing, _ = self._expression(
            normalized, integers=False
        )
        titles = metadata["title"]
        if len(set(titles)) != len(titles):
            raise GeoApiError("participant identifiers are not unique")
        diagnoses = [value.lower() for value in metadata["diagnosis"]]
        permitted = {"r-axspa", "nr-axspa", "hc"}
        if set(diagnoses) - permitted:
            raise GeoApiError("unrecognized diagnoses in GEO metadata")

        sample_order_matches = titles == raw_samples == norm_samples
        feature_order_matches = raw_features == norm_features
        participants = len(titles)
        eligible = (
            participants == 96
            and diagnoses.count("r-axspa") == 38
            and diagnoses.count("nr-axspa") == 38
            and diagnoses.count("hc") == 20
            and len(raw_features) == 1900
            and raw_integer
            and raw_missing == 0
            and sample_order_matches
            and feature_order_matches
        )
        output = root / "mirna-validation"
        output.mkdir(parents=True, exist_ok=True)
        sample_sheet = output / "sample-sheet.tsv"
        with sample_sheet.open("w", encoding="utf-8", newline="") as target:
            fieldnames = ("participant_id", "diagnosis", "group", "sex", "age", "crp")
            writer = csv.DictWriter(target, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for index, title in enumerate(titles):
                diagnosis = diagnoses[index]
                writer.writerow(
                    {
                        "participant_id": title,
                        "diagnosis": diagnosis,
                        "group": "control" if diagnosis == "hc" else "case",
                        "sex": metadata["gender"][index],
                        "age": metadata["age"][index],
                        "crp": metadata["crp"][index],
                    }
                )

        result = MirnaCohortValidation(
            accession=accession,
            participants=participants,
            radiographic_axspa=diagnoses.count("r-axspa"),
            nonradiographic_axspa=diagnoses.count("nr-axspa"),
            healthy_controls=diagnoses.count("hc"),
            mirnas=len(raw_features),
            complete_age=sum(bool(value) for value in metadata["age"]),
            complete_sex=sum(bool(value) for value in metadata["gender"]),
            complete_crp=sum(bool(value) for value in metadata["crp"]),
            raw_counts_are_integers=raw_integer,
            empty_raw_libraries=empty_raw,
            normalized_missing_values=norm_missing,
            sample_order_matches=sample_order_matches,
            feature_order_matches=feature_order_matches,
            eligible_for_analysis=eligible,
            sample_sheet_path=sample_sheet,
            report_path=output / "validation.json",
        )
        report = asdict(result)
        report["sample_sheet_path"] = str(result.sample_sheet_path)
        report["report_path"] = str(result.report_path)
        report["files"] = {
            path.name: self._checksum(path) for path in (matrix, raw, normalized)
        }
        result.report_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        return result

    @staticmethod
    def _metadata(path: Path) -> dict[str, list[str]]:
        rows: dict[str, list[list[str]]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as source:
            for line in source:
                if line.startswith("!series_matrix_table_begin"):
                    break
                if not line.startswith("!Sample_"):
                    continue
                values = next(csv.reader([line], delimiter="\t"))
                rows.setdefault(values[0], []).append(
                    [value.strip().strip('"') for value in values[1:]]
                )
        titles = rows.get("!Sample_title", [[]])[0]
        characteristics = rows.get("!Sample_characteristics_ch1", [])
        result = {"title": titles}
        for field in ("gender", "age", "crp", "diagnosis"):
            prefix = f"{field}:"
            matching = next(
                (
                    [value.partition(":")[2].strip() for value in row]
                    for row in characteristics
                    if row and row[0].lower().startswith(prefix)
                ),
                [],
            )
            if len(matching) != len(titles):
                raise GeoApiError(f"incomplete {field} metadata in {path.name}")
            result[field] = matching
        return result

    @staticmethod
    def _expression(
        path: Path, *, integers: bool
    ) -> tuple[list[str], list[str], bool, int, tuple[str, ...]]:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.reader(source, delimiter="\t")
            header = next(reader, [])
            if not header or header[0] != "miRNA":
                raise GeoApiError(f"invalid microRNA header in {path.name}")
            samples = header[1:]
            features: list[str] = []
            valid_integers = True
            missing_values = 0
            sample_totals = [0.0] * len(samples)
            for row in reader:
                if len(row) != len(header):
                    raise GeoApiError(f"inconsistent row width in {path.name}")
                features.append(row[0])
                for index, value in enumerate(row[1:]):
                    if not value.strip() and not integers:
                        missing_values += 1
                        continue
                    try:
                        number = float(value)
                    except ValueError as error:
                        raise GeoApiError(
                            f"non-numeric expression value in {path.name}"
                        ) from error
                    if not math.isfinite(number) or number < 0:
                        raise GeoApiError(
                            f"invalid expression value in {path.name}"
                        )
                    if integers and not number.is_integer():
                        valid_integers = False
                    sample_totals[index] += number
        if len(set(samples)) != len(samples) or len(set(features)) != len(features):
            raise GeoApiError(f"duplicate samples or features in {path.name}")
        empty = tuple(
            sample for sample, total in zip(samples, sample_totals, strict=True)
            if total == 0
        )
        return samples, features, valid_integers, missing_values, empty

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
