"""Participant-level audit of candidates represented in NCBI SRA run tables."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


class SraAuditClient(Protocol):
    def fetch_runinfo(self, accession: str) -> str: ...


@dataclass(frozen=True)
class SraBiologicalSample:
    run: str
    biosample: str
    sample_name: str
    participant_id: str
    organism: str
    sex: str
    disease: str
    body_site: str
    group: str
    group_basis: str


@dataclass(frozen=True)
class SraStudyAudit:
    accession: str
    runs: int
    biological_samples: int
    participants: int
    case_participants: int
    control_participants: int
    unresolved_participants: int
    total_raw_gb: float
    total_bases: int
    raw_reanalysis_scale: str
    processed_expression_status: str
    case_pattern: str
    control_pattern: str
    group_mapping_status: str
    recommended_role: str
    eligibility_status: str
    limitations: str


@dataclass(frozen=True)
class SraAuditRun:
    studies: int
    output_path: Path
    summary_path: Path


def _classify(
    row: dict[str, str],
    *,
    case_pattern: re.Pattern[str] | None,
    control_pattern: re.Pattern[str] | None,
) -> tuple[str, str]:
    explicit = " ".join(
        row.get(field, "")
        for field in ("Disease", "Affection_Status", "source")
    ).strip()
    lowered = explicit.lower()
    if any(term in lowered for term in ("healthy", "control", "unaffected")):
        return "control", "explicit_metadata"
    if any(
        term in lowered
        for term in (
            "ankylosing spondylitis",
            "axial spondyloarthritis",
            "affected",
        )
    ):
        return "case", "explicit_metadata"
    sample_name = row.get("SampleName", "").strip()
    if case_pattern and case_pattern.search(sample_name):
        return "case", "declared_sample_name_pattern"
    if control_pattern and control_pattern.search(sample_name):
        return "control", "declared_sample_name_pattern"
    return "unresolved", "insufficient_metadata"


class SraCandidateAuditor:
    """Collapse SRA runs into BioSamples and preserve uncertain group labels."""

    def audit(
        self,
        client: SraAuditClient,
        accessions: tuple[str, ...],
        *,
        output_root: str | Path = Path(
            "data/catalog/cross-repository/sample-audit"
        ),
        case_pattern: str | None = None,
        control_pattern: str | None = None,
    ) -> SraAuditRun:
        case_re = re.compile(case_pattern, re.IGNORECASE) if case_pattern else None
        control_re = (
            re.compile(control_pattern, re.IGNORECASE) if control_pattern else None
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        audits: list[SraStudyAudit] = []
        for accession in dict.fromkeys(item.strip() for item in accessions if item):
            text = client.fetch_runinfo(accession)
            samples, runs, total_raw_gb, total_bases = self._parse(
                text, case_pattern=case_re, control_pattern=control_re
            )
            audit = self._summarize(
                accession,
                runs,
                samples,
                case_pattern or "",
                control_pattern or "",
                total_raw_gb,
                total_bases,
            )
            study_dir = destination / accession
            study_dir.mkdir(parents=True, exist_ok=True)
            (study_dir / "runinfo.csv").write_text(text, encoding="utf-8")
            self._write_samples(study_dir / "biological-samples.tsv", samples)
            (study_dir / "study-audit.json").write_text(
                json.dumps(
                    {
                        **asdict(audit),
                        "generated_at": datetime.now(UTC).isoformat(),
                        "analysis_role": "participant_level_metadata_audit",
                        "recommended_next_step": (
                            "Use a deposited processed matrix when available; "
                            "otherwise plan a reproducible raw-read workflow "
                            "separately from lightweight AXIS analyses."
                        ),
                        "warning": (
                            "Declared sample-name patterns require scientific "
                            "confirmation."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            audits.append(audit)
        output_path = destination / "sra-study-audit.tsv"
        self._write_audits(output_path, audits)
        summary_path = destination / "sra-study-audit.json"
        summary_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "studies": len(audits),
                    "accessions": [audit.accession for audit in audits],
                    "output": str(output_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return SraAuditRun(len(audits), output_path, summary_path)

    @staticmethod
    def _parse(
        text: str,
        *,
        case_pattern: re.Pattern[str] | None,
        control_pattern: re.Pattern[str] | None,
    ) -> tuple[tuple[SraBiologicalSample, ...], int, float, int]:
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows or not rows[0]:
            raise ValueError("SRA runinfo is empty")
        samples: dict[str, SraBiologicalSample] = {}
        for row in rows:
            biosample = row.get("BioSample", "").strip()
            sample_name = row.get("SampleName", "").strip()
            key = biosample or row.get("Sample", "").strip() or sample_name
            if not key:
                continue
            group, basis = _classify(
                row,
                case_pattern=case_pattern,
                control_pattern=control_pattern,
            )
            participant = row.get("Subject_ID", "").strip() or key
            samples[key] = SraBiologicalSample(
                run=row.get("Run", "").strip(),
                biosample=biosample,
                sample_name=sample_name,
                participant_id=participant,
                organism=row.get("ScientificName", "").strip(),
                sex=row.get("Sex", "").strip(),
                disease=row.get("Disease", "").strip(),
                body_site=row.get("Body_Site", "").strip(),
                group=group,
                group_basis=basis,
            )
        total_raw_gb = sum(
            float(row.get("size_MB", "") or 0) for row in rows
        ) / 1024
        total_bases = sum(int(row.get("bases", "") or 0) for row in rows)
        return tuple(samples.values()), len(rows), total_raw_gb, total_bases

    @staticmethod
    def _summarize(
        accession: str,
        runs: int,
        samples: tuple[SraBiologicalSample, ...],
        case_pattern: str,
        control_pattern: str,
        total_raw_gb: float,
        total_bases: int,
    ) -> SraStudyAudit:
        participants: dict[str, str] = {}
        for sample in samples:
            participants[sample.participant_id] = sample.group
        counts = Counter(participants.values())
        scale = (
            "large_local_reprocessing"
            if total_raw_gb >= 20
            else "moderate_local_reprocessing"
            if total_raw_gb >= 5
            else "small_or_unknown"
        )
        declared_mapping = bool(case_pattern and control_pattern)
        if counts["case"] >= 3 and counts["control"] >= 3:
            role = "bulk_replication_candidate"
            eligibility = "manual_review_required"
            mapping = (
                "declared_patterns"
                if declared_mapping
                else "explicit_metadata"
            )
            limitations = (
                "Confirm the declared group mapping, tissue matching, treatment "
                "and participant independence before analysis."
            )
        else:
            role = "supporting_context_only"
            eligibility = "not_ready_for_replication"
            mapping = "unresolved"
            limitations = (
                "Case/control groups cannot be established from deposited "
                "metadata without a documented mapping."
            )
        return SraStudyAudit(
            accession=accession,
            runs=runs,
            biological_samples=len(samples),
            participants=len(participants),
            case_participants=counts["case"],
            control_participants=counts["control"],
            unresolved_participants=counts["unresolved"],
            total_raw_gb=round(total_raw_gb, 3),
            total_bases=total_bases,
            raw_reanalysis_scale=scale,
            processed_expression_status="not_listed_in_sra_runinfo",
            case_pattern=case_pattern,
            control_pattern=control_pattern,
            group_mapping_status=mapping,
            recommended_role=role,
            eligibility_status=eligibility,
            limitations=limitations,
        )

    @staticmethod
    def _write_samples(
        path: Path, samples: tuple[SraBiologicalSample, ...]
    ) -> None:
        fields = list(SraBiologicalSample.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(asdict(sample) for sample in samples)

    @staticmethod
    def _write_audits(path: Path, audits: list[SraStudyAudit]) -> None:
        fields = list(SraStudyAudit.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(asdict(audit) for audit in audits)
