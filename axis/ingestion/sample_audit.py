"""Metadata-only audit of GEO samples before expression downloads."""

from __future__ import annotations

import codecs
import csv
import json
import re
import zlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx

from axis.ingestion.geo import GSE_PATTERN, GeoApiError
from axis.ingestion.geo_matrix import GEO_FTP_BASE_URL


@dataclass(frozen=True)
class GeoSample:
    accession: str
    title: str
    source: str
    characteristics: tuple[str, ...]
    platform_matrix: str

    @property
    def searchable_text(self) -> str:
        return " | ".join((self.title, self.source, *self.characteristics))


@dataclass(frozen=True)
class SampleAuditRun:
    requested_studies: int
    audited_studies: int
    design_review_candidates: int
    failed_studies: int
    study_path: Path
    design_queue_path: Path
    sample_path: Path
    summary_path: Path


class GeoSampleMetadataClient:
    """Streams only Series Matrix headers and stops before expression values."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 (GEO sample metadata audit)"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> GeoSampleMetadataClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def samples(self, accession: str) -> tuple[GeoSample, ...]:
        normalized = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(normalized):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        directory = self._matrix_directory_url(normalized)
        filenames = self._discover_filenames(normalized, directory)
        samples: list[GeoSample] = []
        for filename in filenames:
            lines = self._stream_header(urljoin(directory, filename))
            samples.extend(self._parse_header(lines, filename))
        unique: dict[str, GeoSample] = {}
        for sample in samples:
            unique.setdefault(sample.accession, sample)
        return tuple(unique.values())

    @staticmethod
    def _matrix_directory_url(accession: str) -> str:
        return f"{GEO_FTP_BASE_URL}/{accession[:-3]}nnn/{accession}/matrix/"

    def _discover_filenames(self, accession: str, directory: str) -> tuple[str, ...]:
        try:
            response = self._client.get(directory)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeoApiError(
                f"failed to list matrix metadata for {accession}: {error}"
            ) from error
        pattern = re.compile(
            rf'href=["\']({re.escape(accession)}'
            rf'(?:-[^"\'/]+)?_series_matrix\.txt\.gz)["\']',
            re.IGNORECASE,
        )
        filenames = tuple(
            dict.fromkeys(match.group(1) for match in pattern.finditer(response.text))
        )
        if not filenames:
            raise GeoApiError(f"no Series Matrix metadata found for {accession}")
        return filenames

    def _stream_header(self, source_uri: str) -> tuple[str, ...]:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoder = codecs.getincrementaldecoder("utf-8")()
        buffer = ""
        lines: list[str] = []
        try:
            with self._client.stream("GET", source_uri) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    buffer += decoder.decode(decompressor.decompress(chunk))
                    complete = buffer.splitlines(keepends=True)
                    if complete and not complete[-1].endswith(("\n", "\r")):
                        buffer = complete.pop()
                    else:
                        buffer = ""
                    for line in complete:
                        if line.startswith("!series_matrix_table_begin"):
                            return tuple(lines)
                        lines.append(line)
        except (httpx.HTTPError, zlib.error, UnicodeError) as error:
            raise GeoApiError(
                f"failed to stream sample metadata from {source_uri}: {error}"
            ) from error
        raise GeoApiError(f"Series Matrix header is incomplete at {source_uri}")

    @staticmethod
    def _parse_header(lines: tuple[str, ...], filename: str) -> tuple[GeoSample, ...]:
        metadata: dict[str, list[list[str]]] = {}
        try:
            for line in lines:
                if not line.startswith("!Sample_"):
                    continue
                values = next(csv.reader([line], delimiter="\t"))
                metadata.setdefault(values[0], []).append(
                    [value.strip().strip('"') for value in values[1:]]
                )
        except csv.Error as error:
            raise GeoApiError(
                f"invalid sample metadata in {filename}: {error}"
            ) from error
        accessions = GeoSampleMetadataClient._row(metadata, "!Sample_geo_accession")
        titles = GeoSampleMetadataClient._row(
            metadata, "!Sample_title", len(accessions)
        )
        sources = GeoSampleMetadataClient._row(
            metadata, "!Sample_source_name_ch1", len(accessions)
        )
        characteristic_rows = metadata.get("!Sample_characteristics_ch1", [])
        if any(len(row) != len(accessions) for row in characteristic_rows):
            raise GeoApiError(f"inconsistent sample metadata in {filename}")
        return tuple(
            GeoSample(
                accession=sample,
                title=titles[index],
                source=sources[index],
                characteristics=tuple(
                    row[index] for row in characteristic_rows if row[index]
                ),
                platform_matrix=filename,
            )
            for index, sample in enumerate(accessions)
        )

    @staticmethod
    def _row(
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


class PrioritySampleAuditor:
    """Suggests case/control structure while preserving human approval gates."""

    CASE = re.compile(
        r"ankylosing spondylitis|\baxspa\b|\bspondyloarthritis\b|"
        r"\bAS[-_ ]?\d+\b|\bpatient\b",
        re.IGNORECASE,
    )
    CONTROL = re.compile(r"healthy|unaffected|\bnormal\b|\bcontrol\b", re.IGNORECASE)
    TREATED = re.compile(
        r"post[\s-]?treatment|after treatment|\btreated\b|anti[\s-]?tnf|"
        r"adalimumab|infliximab|secukinumab|etanercept|golimumab|"
        r"methotrexate|sulfasalazine|prednisolone|corticosteroid",
        re.IGNORECASE,
    )
    UNTREATED = re.compile(
        r"untreated|treatment[\s-]?naive|drug[\s-]?naive|\bbaseline\b|"
        r"pre[\s-]?treatment",
        re.IGNORECASE,
    )

    def build(
        self,
        client: GeoSampleMetadataClient,
        priority_path: str | Path = Path(
            "data/catalog/direct-study-priority-queue.tsv"
        ),
        *,
        output_root: str | Path = Path("data/catalog/sample-audit"),
        maximum: int | None = None,
    ) -> SampleAuditRun:
        source = Path(priority_path)
        with source.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        if not rows or "accession" not in rows[0]:
            raise ValueError("priority queue has no accession column")
        selected = rows if maximum is None else rows[:maximum]
        study_rows: list[dict[str, object]] = []
        sample_rows: list[dict[str, object]] = []
        for priority in selected:
            accession = priority["accession"]
            try:
                samples = client.samples(accession)
            except (GeoApiError, ValueError) as error:
                study_rows.append(self._failed_row(priority, error=str(error)))
                continue
            classified = [self._classify(sample) for sample in samples]
            sample_rows.extend(
                {"study_accession": accession, **row} for row in classified
            )
            study_rows.append(self._study_row(priority, classified))

        study_rows.sort(
            key=lambda row: (
                row["audit_status"] != "design_review_candidate",
                -int(str(row["usable_case_control_samples"])),
                str(row["accession"]),
            )
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        study_path = destination / "study-sample-audit.tsv"
        design_queue_path = destination / "design-review-queue.tsv"
        sample_path = destination / "sample-metadata.tsv"
        summary_path = destination / "sample-audit.json"
        self._write(study_path, study_rows)
        self._write(
            design_queue_path,
            [
                row
                for row in study_rows
                if row["audit_status"] == "design_review_candidate"
            ],
        )
        self._write(sample_path, sample_rows)
        statuses = Counter(str(row["audit_status"]) for row in study_rows)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "priority_study_sample_metadata_audit",
                    "created_at": datetime.now(UTC).isoformat(),
                    "priority_queue": str(source),
                    "requested_studies": len(selected),
                    "audited_studies": len(selected) - statuses["metadata_unavailable"],
                    "sample_records": len(sample_rows),
                    "audit_statuses": dict(sorted(statuses.items())),
                    "automatic_eligibility": False,
                    "warning": (
                        "Groups are keyword suggestions from GEO sample metadata. "
                        "A human must verify disease definition, treatment, repeated "
                        "participants, covariates and independence before analysis."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SampleAuditRun(
            requested_studies=len(selected),
            audited_studies=len(selected) - statuses["metadata_unavailable"],
            design_review_candidates=statuses["design_review_candidate"],
            failed_studies=statuses["metadata_unavailable"],
            study_path=study_path,
            design_queue_path=design_queue_path,
            sample_path=sample_path,
            summary_path=summary_path,
        )

    def _classify(self, sample: GeoSample) -> dict[str, object]:
        text = sample.searchable_text
        case = self.CASE.search(text) is not None
        control = self.CONTROL.search(text) is not None
        if case and control:
            suggested = "ambiguous"
        elif case:
            suggested = "case"
        elif control:
            suggested = "control"
        else:
            suggested = "unassigned"
        treated = self.TREATED.search(text) is not None
        untreated = self.UNTREATED.search(text) is not None
        if treated and untreated:
            treatment = "ambiguous"
        elif treated:
            treatment = "treated"
        elif untreated:
            treatment = "untreated_or_baseline"
        else:
            treatment = "unknown"
        subject = self._subject_identifier(sample.characteristics)
        return {
            "sample_accession": sample.accession,
            "suggested_group": suggested,
            "treatment_signal": treatment,
            "subject_identifier": subject,
            "title": sample.title,
            "source": sample.source,
            "characteristics": " | ".join(sample.characteristics),
            "platform_matrix": sample.platform_matrix,
            "automatic_eligibility": False,
        }

    @staticmethod
    def _subject_identifier(characteristics: tuple[str, ...]) -> str:
        for item in characteristics:
            key, separator, value = item.partition(":")
            normalized = key.strip().lower()
            if (
                separator
                and value.strip()
                and any(
                    token in normalized
                    for token in ("subject", "patient id", "donor", "individual")
                )
            ):
                return value.strip()
        return ""

    @staticmethod
    def _study_row(
        priority: dict[str, str], samples: list[dict[str, object]]
    ) -> dict[str, object]:
        groups = Counter(str(row["suggested_group"]) for row in samples)
        treatments = Counter(str(row["treatment_signal"]) for row in samples)
        subjects = [
            str(row["subject_identifier"])
            for row in samples
            if row["subject_identifier"]
        ]
        repeated = len(subjects) - len(set(subjects))
        usable = groups["case"] + groups["control"]
        treated_cases = sum(
            row["suggested_group"] == "case" and row["treatment_signal"] == "treated"
            for row in samples
        )
        untreated_cases = sum(
            row["suggested_group"] == "case"
            and row["treatment_signal"] == "untreated_or_baseline"
            for row in samples
        )
        unknown_treatment_cases = sum(
            row["suggested_group"] == "case" and row["treatment_signal"] == "unknown"
            for row in samples
        )
        if groups["case"] >= 3 and groups["control"] >= 3:
            status = "design_review_candidate"
            next_action = "verify_sample_sheet_and_treatment"
        elif groups["case"] and groups["control"]:
            status = "small_or_ambiguous_case_control"
            next_action = "manual_group_review"
        else:
            status = "no_case_control_structure_detected"
            next_action = "manual_relevance_review"
        blockers: list[str] = []
        if treated_cases:
            blockers.append("treated_cases_require_exclusion_or_separate_contrast")
        if groups["ambiguous"]:
            blockers.append("ambiguous_groups")
        if groups["unassigned"]:
            blockers.append("unassigned_samples")
        if repeated:
            blockers.append("repeated_subject_rows")
        if unknown_treatment_cases:
            blockers.append("case_treatment_status_unknown")
        return {
            "accession": priority["accession"],
            "catalog_priority_tier": priority.get("priority_tier", ""),
            "catalog_priority_score": priority.get("priority_score", ""),
            "samples": len(samples),
            "suggested_cases": groups["case"],
            "suggested_controls": groups["control"],
            "ambiguous_samples": groups["ambiguous"],
            "unassigned_samples": groups["unassigned"],
            "treated_samples": treatments["treated"],
            "treated_cases": treated_cases,
            "untreated_or_baseline_cases": untreated_cases,
            "unknown_treatment_cases": unknown_treatment_cases,
            "untreated_or_baseline_samples": treatments["untreated_or_baseline"],
            "unknown_treatment_samples": treatments["unknown"],
            "subject_ids_found": len(subjects),
            "repeated_subject_rows": repeated,
            "usable_case_control_samples": usable,
            "audit_status": status,
            "design_blockers": "|".join(blockers),
            "automatic_eligibility": False,
            "next_action": next_action,
            "error": "",
        }

    @staticmethod
    def _failed_row(priority: dict[str, str], *, error: str) -> dict[str, object]:
        return {
            "accession": priority["accession"],
            "catalog_priority_tier": priority.get("priority_tier", ""),
            "catalog_priority_score": priority.get("priority_score", ""),
            "samples": 0,
            "suggested_cases": 0,
            "suggested_controls": 0,
            "ambiguous_samples": 0,
            "unassigned_samples": 0,
            "treated_samples": 0,
            "treated_cases": 0,
            "untreated_or_baseline_cases": 0,
            "unknown_treatment_cases": 0,
            "untreated_or_baseline_samples": 0,
            "unknown_treatment_samples": 0,
            "subject_ids_found": 0,
            "repeated_subject_rows": 0,
            "usable_case_control_samples": 0,
            "audit_status": "metadata_unavailable",
            "design_blockers": "metadata_unavailable",
            "automatic_eligibility": False,
            "next_action": "inspect_GEO_manually",
            "error": error,
        }

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
