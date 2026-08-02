"""Participant-level auditing of ArrayExpress studies hosted by BioStudies."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class BioStudiesAuditClient(Protocol):
    def fetch_study(self, accession: str) -> dict[str, Any]: ...

    def fetch_study_info(self, accession: str) -> dict[str, Any]: ...

    def fetch_text(self, url: str) -> str: ...


@dataclass(frozen=True)
class MageTabSample:
    source_name: str
    participant_id: str
    organism: str
    disease: str
    group: str
    tissue: str
    cell_type: str
    sex: str
    age: str
    treatment: str
    ena_sample: str


@dataclass(frozen=True)
class BioStudiesStudyAudit:
    accession: str
    title: str
    sdrf_url: str
    sdrf_rows: int
    biological_samples: int
    participants: int
    case_participants: int
    control_participants: int
    other_participants: int
    tissues: str
    treatments: str
    participant_identity_status: str
    comparison_status: str
    recommended_role: str
    eligibility_status: str
    limitations: str


@dataclass(frozen=True)
class BioStudiesAuditRun:
    studies: int
    output_path: Path
    summary_path: Path
    sample_paths: tuple[Path, ...]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _values(row: list[str], headers: list[str], *names: str) -> list[str]:
    wanted = {_norm(name) for name in names}
    return [
        value.strip()
        for header, value in zip(headers, row, strict=False)
        if _norm(header) in wanted and value.strip()
    ]


def _first(row: list[str], headers: list[str], *names: str) -> str:
    values = _values(row, headers, *names)
    return values[0] if values else ""


def _group(disease: str) -> str:
    value = _norm(disease)
    if any(term in value for term in ("healthy", "control", "normal")):
        return "control"
    if any(
        term in value
        for term in (
            "ankylosing spondylitis",
            "axial spondyloarthritis",
            "spondyloarthritis",
        )
    ):
        return "case"
    return "other"


def _treatment(row: list[str], headers: list[str]) -> str:
    values: list[str] = []
    for header, value in zip(headers, row, strict=False):
        normalized_header = _norm(header)
        normalized_value = _norm(value)
        if not normalized_value:
            continue
        if "factor value[" not in normalized_header:
            continue
        if any(
            excluded in normalized_header
            for excluded in ("organism part", "disease", "individual")
        ):
            continue
        if normalized_value in {
            "none",
            "not applicable",
            "unstimulated",
            "untreated",
            "no treatment",
        }:
            continue
        match = re.search(r"factor value\[(.+)]", normalized_header)
        factor = match.group(1) if match else "factor"
        values.append(f"{factor}={value.strip()}")
    return "; ".join(dict.fromkeys(values))


def parse_sdrf(text: str) -> tuple[MageTabSample, ...]:
    """Parse SDRF without losing repeated MAGE-TAB column names."""
    records = list(csv.reader(io.StringIO(text), delimiter="\t"))
    if not records:
        raise ValueError("SDRF is empty")
    headers = records[0]
    samples: dict[tuple[str, str], MageTabSample] = {}
    for index, row in enumerate(records[1:], start=1):
        if not any(value.strip() for value in row):
            continue
        source_name = _first(row, headers, "Source Name", "Sample Name")
        ena_sample = _first(
            row, headers, "Comment[ENA_SAMPLE]", "Comment[BioSD_SAMPLE]"
        )
        participant_id = _first(
            row,
            headers,
            "Characteristics[individual]",
            "Characteristics[donor]",
            "Characteristics[patient]",
            "Characteristics[subject]",
        )
        if not participant_id:
            participant_id = source_name or ena_sample or f"unresolved-{index}"
        disease = _first(
            row,
            headers,
            "Characteristics[disease]",
            "Factor Value[disease]",
        )
        sample = MageTabSample(
            source_name=source_name or ena_sample or f"sample-{index}",
            participant_id=participant_id,
            organism=_first(row, headers, "Characteristics[organism]"),
            disease=disease,
            group=_group(disease),
            tissue=_first(
                row,
                headers,
                "Characteristics[organism part]",
                "Factor Value[organism part]",
            ),
            cell_type=_first(row, headers, "Characteristics[cell type]"),
            sex=_first(row, headers, "Characteristics[sex]"),
            age=_first(row, headers, "Characteristics[age]"),
            treatment=_treatment(row, headers),
            ena_sample=ena_sample,
        )
        samples[(sample.source_name, sample.ena_sample)] = sample
    return tuple(samples.values())


def _walk_files(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str):
            paths.append(path)
        for nested in value.values():
            paths.extend(_walk_files(nested))
    elif isinstance(value, list):
        for nested in value:
            paths.extend(_walk_files(nested))
    return paths


def _study_title(payload: dict[str, Any], accession: str) -> str:
    for attribute in payload.get("attributes", []):
        if (
            isinstance(attribute, dict)
            and attribute.get("name") == "Title"
            and attribute.get("value")
        ):
            return str(attribute["value"])
    return accession


class BioStudiesCandidateAuditor:
    """Download small metadata files and assess true biological replication."""

    def audit(
        self,
        client: BioStudiesAuditClient,
        accessions: tuple[str, ...],
        *,
        output_root: str | Path = Path(
            "data/catalog/cross-repository/sample-audit"
        ),
    ) -> BioStudiesAuditRun:
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        audits: list[BioStudiesStudyAudit] = []
        sample_paths: list[Path] = []

        for accession in dict.fromkeys(item.strip() for item in accessions if item):
            payload = client.fetch_study(accession)
            info = client.fetch_study_info(accession)
            sdrf_names = sorted(
                {
                    path
                    for path in _walk_files(payload)
                    if path.lower().endswith(".sdrf.txt")
                }
            )
            if not sdrf_names:
                raise ValueError(f"{accession} has no SDRF file")
            base_url = str(info.get("httpLink", "")).rstrip("/")
            if not base_url:
                raise ValueError(f"{accession} has no public BioStudies file URL")
            sdrf_url = f"{base_url}/Files/{sdrf_names[0]}"
            text = client.fetch_text(sdrf_url)
            samples = parse_sdrf(text)
            audit = self._summarize(
                accession,
                _study_title(payload, accession),
                sdrf_url,
                text,
                samples,
            )
            study_dir = destination / accession
            study_dir.mkdir(parents=True, exist_ok=True)
            sdrf_path = study_dir / sdrf_names[0]
            sdrf_path.write_text(text, encoding="utf-8")
            sample_path = study_dir / "biological-samples.tsv"
            self._write_samples(sample_path, samples)
            (study_dir / "study-audit.json").write_text(
                json.dumps(
                    {
                        **asdict(audit),
                        "generated_at": datetime.now(UTC).isoformat(),
                        "analysis_role": "participant_level_metadata_audit",
                        "warning": (
                            "Metadata classification is not automatic scientific "
                            "eligibility."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            audits.append(audit)
            sample_paths.append(sample_path)

        output_path = destination / "biostudies-study-audit.tsv"
        self._write_audits(output_path, audits)
        summary_path = destination / "biostudies-study-audit.json"
        summary_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "studies": len(audits),
                    "accessions": [audit.accession for audit in audits],
                    "role_counts": dict(
                        Counter(audit.recommended_role for audit in audits)
                    ),
                    "output": str(output_path),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return BioStudiesAuditRun(
            len(audits), output_path, summary_path, tuple(sample_paths)
        )

    @staticmethod
    def _summarize(
        accession: str,
        title: str,
        sdrf_url: str,
        text: str,
        samples: tuple[MageTabSample, ...],
    ) -> BioStudiesStudyAudit:
        participants: dict[str, set[str]] = {}
        for sample in samples:
            participants.setdefault(sample.participant_id, set()).add(sample.group)
        participant_groups = {
            participant: (
                "case"
                if "case" in groups
                else "control"
                if "control" in groups
                else "other"
            )
            for participant, groups in participants.items()
        }
        counts = Counter(participant_groups.values())
        tissues = sorted({sample.tissue for sample in samples if sample.tissue})
        treatments = sorted(
            {sample.treatment for sample in samples if sample.treatment}
        )
        unresolved = sum(
            participant.startswith("unresolved-") for participant in participants
        )
        identity_status = "resolved" if not unresolved else "partially_unresolved"
        if counts["case"] >= 3 and counts["control"] >= 3 and not treatments:
            comparison = "case_control_available"
            role = "independent_single_cell_replication_candidate"
            eligibility = "manual_review_required"
            limitations = (
                "Confirm treatment, matching, batch and processed-data access."
            )
        elif treatments:
            comparison = (
                "case_control_with_perturbation"
                if counts["control"]
                else "no_independent_controls"
            )
            role = "mechanistic_perturbation_context"
            eligibility = "not_primary_replication"
            limitations = (
                "Perturbed samples cannot be treated as independent baseline "
                "case-control replication."
            )
        elif len(tissues) > 1 and not counts["control"]:
            comparison = "paired_tissue_without_controls"
            role = "mechanistic_tissue_context"
            eligibility = "not_primary_replication"
            limitations = (
                "Within-patient tissue comparison with no healthy control cohort."
            )
        else:
            comparison = "insufficient_case_control_replication"
            role = "supporting_context_only"
            eligibility = "not_primary_replication"
            limitations = "Fewer than three independent cases or controls."
        return BioStudiesStudyAudit(
            accession=accession,
            title=title,
            sdrf_url=sdrf_url,
            sdrf_rows=max(0, len(text.splitlines()) - 1),
            biological_samples=len(samples),
            participants=len(participants),
            case_participants=counts["case"],
            control_participants=counts["control"],
            other_participants=counts["other"],
            tissues="; ".join(tissues),
            treatments="; ".join(treatments),
            participant_identity_status=identity_status,
            comparison_status=comparison,
            recommended_role=role,
            eligibility_status=eligibility,
            limitations=limitations,
        )

    @staticmethod
    def _write_samples(
        path: Path, samples: tuple[MageTabSample, ...]
    ) -> None:
        fields = list(MageTabSample.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(asdict(sample) for sample in samples)

    @staticmethod
    def _write_audits(
        path: Path, audits: list[BioStudiesStudyAudit]
    ) -> None:
        fields = list(BioStudiesStudyAudit.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(asdict(audit) for audit in audits)
