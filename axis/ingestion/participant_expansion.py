"""Collapse GEO sample rows into independent participant cohorts."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ParticipantRecord:
    study_accession: str
    participant_id: str
    disease_group: str
    suggested_group: str
    sample_rows: int
    tissues: str
    cell_types: str
    treatment_statuses: str
    identity_basis: str


@dataclass(frozen=True)
class ParticipantCohort:
    accession: str
    assay: str
    participants: int
    axial_spa_participants: int
    ankylosing_spondylitis_participants: int
    peripheral_spa_participants: int
    psoriatic_arthritis_participants: int
    healthy_control_participants: int
    other_participants: int
    repeated_sample_rows: int
    participant_identity_coverage: float
    recommended_role: str
    automatic_eligibility: bool
    next_action: str


@dataclass(frozen=True)
class ParticipantExpansionRun:
    studies: int
    participants: int
    cohort_path: Path
    participant_path: Path
    summary_path: Path


def _characteristic_value(text: str, name: str) -> str:
    match = re.search(
        rf"(?:^|\|)\s*{re.escape(name)}\s*:\s*([^|]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _disease_group(characteristics: str, title: str) -> str:
    explicit = " ".join(
        (
            _characteristic_value(characteristics, "disease state"),
            _characteristic_value(characteristics, "disease"),
            _characteristic_value(characteristics, "working_diagnosis"),
            _characteristic_value(characteristics, "diagnosis"),
            _characteristic_value(characteristics, "phenotype"),
        )
    ).lower()

    def classify(disease: str) -> str:
        if (
            "healthy" in disease
            or "control" in disease
            or re.search(r"\bhc\b", disease)
        ):
            return "healthy_control"
        if (
            "axial spa" in disease
            or "axial spondyloarthritis" in disease
            or re.search(r"\b(?:nr-|r-)?axspa\b", disease)
        ):
            return "axial_spa"
        if "ankylosing spondylitis" in disease:
            return "ankylosing_spondylitis"
        if "peripheral spa" in disease:
            return "peripheral_spa"
        if "psoriatic arthritis" in disease:
            return "psoriatic_arthritis"
        if "rheumatoid arthritis" in disease:
            return "rheumatoid_arthritis"
        if "psoriasis" in disease:
            return "psoriasis"
        return "other"

    explicit_group = classify(explicit)
    if explicit_group != "other":
        return explicit_group
    disease = title.lower()
    if (
        "healthy" in disease
        or "control" in disease
        or re.search(r"\bhc\b", disease)
    ):
        return "healthy_control"
    if (
        "axial spa" in disease
        or "axial spondyloarthritis" in disease
        or re.search(r"\b(?:nr-|r-)?axspa\b", disease)
    ):
        return "axial_spa"
    if "ankylosing spondylitis" in disease:
        return "ankylosing_spondylitis"
    if "peripheral spa" in disease:
        return "peripheral_spa"
    if "psoriatic arthritis" in disease:
        return "psoriatic_arthritis"
    if "rheumatoid arthritis" in disease:
        return "rheumatoid_arthritis"
    if "psoriasis" in disease:
        return "psoriasis"
    return "other"


def _participant_ids(row: dict[str, str], disease: str) -> tuple[list[str], str]:
    explicit = row.get("subject_identifier", "").strip()
    if explicit:
        return [explicit], "deposited_subject_identifier"
    characteristics = row.get("characteristics", "")
    for field in ("pid", "participant", "individual", "donor", "subject"):
        value = _characteristic_value(characteristics, field)
        if value:
            return [f"{disease}:{value}"], "deposited_characteristic_identifier"
    title = row.get("title", "").strip()
    pooled = sorted(set(re.findall(r"KAS\d+", title, re.IGNORECASE)))
    if pooled:
        return (
            [f"{disease}:{value.upper()}" for value in pooled],
            "pooled_title_identifiers",
        )
    for pattern in (
        r"^([A-Z]{1,2}\d{3,5})(?:[_:]|\b)",
        r"^(EA\d+)(?::|\b)",
        r"\bPatient\s+(\d+)\b",
        r"\bHealthy (?:Volunteer|control)\s+(\d+)\b",
    ):
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return [f"{disease}:{match.group(1).upper()}"], "title_identifier"
    return [], "unresolved"


class ParticipantExpansionBuilder:
    """Create conservative participant counts from audited GEO sample metadata."""

    def build(
        self,
        sample_metadata_path: str | Path,
        catalog_path: str | Path,
        *,
        output_root: str | Path = Path("data/catalog/participant-expansion"),
    ) -> ParticipantExpansionRun:
        samples = self._read(Path(sample_metadata_path))
        catalog = {
            row["accession"]: row for row in self._read(Path(catalog_path))
        }
        grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
        unresolved_by_study: Counter[str] = Counter()
        rows_by_study: Counter[str] = Counter()
        for row in samples:
            accession = row["study_accession"]
            rows_by_study[accession] += 1
            study_title = catalog.get(accession, {}).get("title", "")
            disease = _disease_group(
                row.get("characteristics", ""),
                f"{row['title']} {study_title}",
            )
            participant_ids, basis = _participant_ids(row, disease)
            if not participant_ids:
                unresolved_by_study[accession] += 1
                continue
            enriched = {**row, "_disease": disease, "_basis": basis}
            for participant_id in participant_ids:
                grouped.setdefault((accession, participant_id), []).append(
                    enriched
                )

        participants = [
            self._participant(accession, participant_id, records)
            for (accession, participant_id), records in grouped.items()
        ]
        participants.sort(
            key=lambda row: (
                row.study_accession,
                row.disease_group,
                row.participant_id,
            )
        )
        by_study: dict[str, list[ParticipantRecord]] = {}
        for participant in participants:
            by_study.setdefault(participant.study_accession, []).append(participant)
        cohorts = [
            self._cohort(
                accession,
                records,
                catalog.get(accession, {}),
                rows_by_study[accession],
                unresolved_by_study[accession],
            )
            for accession, records in by_study.items()
        ]
        cohorts.sort(
            key=lambda row: (
                -row.axial_spa_participants
                - row.ankylosing_spondylitis_participants,
                -row.healthy_control_participants,
                row.accession,
            )
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        cohort_path = destination / "participant-cohorts.tsv"
        participant_path = destination / "participants.tsv"
        summary_path = destination / "participant-expansion.json"
        self._write(cohort_path, cohorts)
        self._write(participant_path, participants)
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "studies_with_resolved_participants": len(cohorts),
                    "resolved_participants": len(participants),
                    "axspa_case_control_candidates": [
                        row.accession
                        for row in cohorts
                        if row.recommended_role == "axspa_case_control_candidate"
                    ],
                    "policy": (
                        "Repeated cell types, tissues, runs and longitudinal rows "
                        "are collapsed by deposited or title-derived participant "
                        "identifier. Title-derived identities require review."
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ParticipantExpansionRun(
            len(cohorts),
            len(participants),
            cohort_path,
            participant_path,
            summary_path,
        )

    @staticmethod
    def _participant(
        accession: str,
        participant_id: str,
        records: list[dict[str, str]],
    ) -> ParticipantRecord:
        diseases = Counter(row["_disease"] for row in records)
        groups = Counter(row["suggested_group"] for row in records)
        tissues = {
            _characteristic_value(row.get("characteristics", ""), "tissue")
            for row in records
        }
        cell_types = {
            _characteristic_value(row.get("characteristics", ""), "cell type")
            for row in records
        }
        return ParticipantRecord(
            study_accession=accession,
            participant_id=participant_id,
            disease_group=diseases.most_common(1)[0][0],
            suggested_group=groups.most_common(1)[0][0],
            sample_rows=len(records),
            tissues="; ".join(sorted(value for value in tissues if value)),
            cell_types="; ".join(sorted(value for value in cell_types if value)),
            treatment_statuses="; ".join(
                sorted({row["treatment_signal"] for row in records})
            ),
            identity_basis=records[0]["_basis"],
        )

    @staticmethod
    def _cohort(
        accession: str,
        records: list[ParticipantRecord],
        catalog: dict[str, str],
        sample_rows: int,
        unresolved_rows: int,
    ) -> ParticipantCohort:
        counts = Counter(row.disease_group for row in records)
        cases = counts["axial_spa"] + counts["ankylosing_spondylitis"]
        controls = counts["healthy_control"]
        experiment = catalog.get("experiment_type", "")
        expression = "Expression profiling" in experiment
        targeted = "RT-PCR" in experiment
        noncoding = "Non-coding RNA profiling" in experiment
        if cases >= 10 and controls >= 10 and targeted:
            role = "targeted_expression_validation_candidate"
            next_action = "verify_targets_and_axspa_subgroup"
        elif cases >= 10 and controls >= 10 and noncoding:
            role = "mirna_case_control_candidate"
            next_action = "verify_processed_mirna_counts_and_covariates"
        elif cases >= 10 and controls >= 10 and expression:
            role = "axspa_case_control_candidate"
            next_action = "verify_modality_treatment_and_processed_matrix"
        elif cases and controls:
            role = "axspa_supporting_context"
            next_action = "manual_design_review"
        else:
            role = "non_axspa_or_no_control_context"
            next_action = "do_not_use_as_primary_axspa_replication"
        return ParticipantCohort(
            accession=accession,
            assay=experiment,
            participants=len(records),
            axial_spa_participants=counts["axial_spa"],
            ankylosing_spondylitis_participants=counts[
                "ankylosing_spondylitis"
            ],
            peripheral_spa_participants=counts["peripheral_spa"],
            psoriatic_arthritis_participants=counts["psoriatic_arthritis"],
            healthy_control_participants=controls,
            other_participants=len(records)
            - cases
            - controls
            - counts["peripheral_spa"]
            - counts["psoriatic_arthritis"],
            repeated_sample_rows=sum(max(0, row.sample_rows - 1) for row in records),
            participant_identity_coverage=(
                round((sample_rows - unresolved_rows) / sample_rows, 4)
                if sample_rows
                else 0
            ),
            recommended_role=role,
            automatic_eligibility=False,
            next_action=next_action,
        )

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _write(
        path: Path,
        rows: list[ParticipantCohort] | list[ParticipantRecord],
    ) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        serialized = [asdict(row) for row in rows]
        fields = list(serialized[0])
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(serialized)
