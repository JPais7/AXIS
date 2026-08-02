"""Conservative selection of independent validation and reference cohorts."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ValidationCohortSelectionRun:
    evaluated: int
    priority_review: int
    bulk_candidates: int
    single_cell_candidates: int
    priorities_path: Path
    review_path: Path
    summary_path: Path


class ValidationCohortSelector:
    """Rank quarantined studies without granting automatic eligibility."""

    def select(
        self,
        *,
        quarantine_path: str | Path,
        cohort_evaluation_path: str | Path,
        sample_validation_path: str | Path,
        participant_cohorts_path: str | Path,
        output_root: str | Path = Path(
            "data/catalog/validation-cohort-selection"
        ),
    ) -> ValidationCohortSelectionRun:
        quarantine = self._rows(Path(quarantine_path))
        evaluations = self._indexed(Path(cohort_evaluation_path))
        validations = self._indexed(Path(sample_validation_path))
        participants = self._indexed(Path(participant_cohorts_path))
        preferred = self._preferred_repository_records(quarantine)
        rows = [
            self._evaluate(
                row,
                evaluations.get(row["accession"], {}),
                validations.get(row["accession"], {}),
                participants.get(row["accession"], {}),
                preferred,
            )
            for row in quarantine
            if row.get("disease_signal") == "axspa_specific"
        ]
        rows.sort(
            key=lambda row: (
                -int(str(row["selection_score"])),
                str(row["accession"]),
            )
        )
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        review_rows = [
            {
                "rank": row["rank"],
                "accession": row["accession"],
                "proposed_role": row["proposed_role"],
                "selection_decision": row["selection_decision"],
                "blocking_reasons": row["blocking_reasons"],
                "manual_checks": row["manual_checks"],
                "source_uri": row["source_uri"],
            }
            for row in rows
            if row["selection_decision"] == "priority_manual_review"
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        priorities_path = destination / "validation-cohort-priorities.tsv"
        review_path = destination / "priority-manual-review.tsv"
        summary_path = destination / "validation-selection.json"
        self._write(priorities_path, rows)
        self._write(review_path, review_rows)
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "independent_validation_cohort_selection",
                    "evaluated": len(rows),
                    "priority_manual_review": len(review_rows),
                    "recommended_sequence": [
                        (
                            "Resolve treatment and participant identity in "
                            "primary-blood candidates."
                        ),
                        (
                            "Confirm broad cell-type coverage, controls and "
                            "donor independence in single-cell candidates."
                        ),
                        "Check publication and BioProject overlap.",
                        "Approve new cohorts for validation only.",
                        "Freeze the validation protocol before download.",
                    ],
                    "guardrails": [
                        "No row is automatically eligible.",
                        "Repository duplicates cannot count as independent cohorts.",
                        "Treated cases cannot validate an untreated disease signal.",
                        (
                            "Sorted-cell studies are mechanistic, not "
                            "whole-blood replication."
                        ),
                        "Unknown metadata is a blocker, not a negative assumption.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ValidationCohortSelectionRun(
            evaluated=len(rows),
            priority_review=len(review_rows),
            bulk_candidates=sum(
                row["proposed_role"] == "primary_bulk_validation"
                and row["selection_decision"] == "priority_manual_review"
                for row in rows
            ),
            single_cell_candidates=sum(
                row["proposed_role"] == "single_cell_reference_validation"
                and row["selection_decision"] == "priority_manual_review"
                for row in rows
            ),
            priorities_path=priorities_path,
            review_path=review_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _preferred_repository_records(
        rows: list[dict[str, str]],
    ) -> dict[str, str]:
        preferred: dict[str, str] = {}
        order = {"GEO": 0, "BioStudies-ArrayExpress": 1, "NCBI-SRA": 2}
        for row in sorted(rows, key=lambda value: order.get(value["source"], 9)):
            key = row.get("bioproject_id") or ValidationCohortSelector._title_key(
                row["title"]
            )
            preferred.setdefault(key, row["accession"])
        return preferred

    @staticmethod
    def _evaluate(
        row: dict[str, str],
        evaluation: dict[str, str],
        validation: dict[str, str],
        participants: dict[str, str],
        preferred: dict[str, str],
    ) -> dict[str, object]:
        accession = row["accession"]
        title = row["title"].lower()
        assay = row["assay"].lower()
        key = row.get("bioproject_id") or ValidationCohortSelector._title_key(
            row["title"]
        )
        duplicate = preferred.get(key) != accession
        single_cell = "single-cell" in assay or "scrna" in title
        noncoding = any(
            token in assay or token in title
            for token in ("non-coding", "mirna", "circrna", "lncrna")
        )
        wrong_assay = any(
            token in assay
            for token in (
                "methylation",
                "genome binding",
                "other",
                "tcr",
                "targeted-capture",
            )
        ) and not single_cell
        blood = any(
            token in title
            for token in ("blood", "pbmc", "monocyte", "macrophage")
        )
        sorted_cells = any(
            token in title
            for token in ("il-17-producing", "cd8", "b cell", "macrophage")
        )
        treated = (
            int(evaluation.get("treated_cases") or 0) > 0
            or "before and after" in title
            or "treatment" in title
            or "inhibitor response" in title
        )
        cases = int(
            evaluation.get("suggested_cases")
            or participants.get("ankylosing_spondylitis_participants")
            or validation.get("proposed_include")
            or 0
        )
        controls = int(
            evaluation.get("suggested_controls")
            or participants.get("healthy_control_participants")
            or validation.get("proposed_include")
            or 0
        )
        proposed_role = (
            "single_cell_reference_validation"
            if single_cell and blood
            else "mechanistic_sorted_cell_validation"
            if sorted_cells
            else "primary_bulk_validation"
            if blood and not noncoding
            else "context_only"
        )
        blockers: list[str] = []
        if duplicate:
            blockers.append("duplicate_repository_record")
        if noncoding:
            blockers.append("noncoding_assay")
        if wrong_assay:
            blockers.append("incompatible_assay")
        if treated:
            blockers.append("treated_or_perturbed_cases")
        if not blood:
            blockers.append("not_blood_or_immune_context")
        if evaluation.get("different_disease_in_cases") == "True":
            blockers.append("different_disease_in_cases")
        if (
            participants
            and int(participants.get("healthy_control_participants") or 0) == 0
        ):
            blockers.append("no_healthy_controls")
        unknown_design = not evaluation and not validation and not participants
        score = 0
        score += 8 if proposed_role == "primary_bulk_validation" else 0
        score += 7 if proposed_role == "single_cell_reference_validation" else 0
        score += 4 if proposed_role == "mechanistic_sorted_cell_validation" else 0
        score += 3 if cases >= 6 and controls >= 6 else 0
        score += 2 if int(row.get("sample_count") or 0) >= 12 else 0
        score -= 8 * len(blockers)
        if unknown_design:
            score -= 2
        disqualifying = {
            "duplicate_repository_record",
            "noncoding_assay",
            "incompatible_assay",
            "treated_or_perturbed_cases",
            "different_disease_in_cases",
            "no_healthy_controls",
        }
        if disqualifying.intersection(blockers):
            decision = "deprioritised"
        elif proposed_role in {
            "primary_bulk_validation",
            "single_cell_reference_validation",
            "mechanistic_sorted_cell_validation",
        } and score >= 4:
            decision = "priority_manual_review"
        else:
            decision = "secondary_manual_review"
        manual_checks = [
            "participant_identity",
            "case_control_definition",
            "tissue_and_cell_types",
            "treatment_status",
            "data_availability",
            "publication_and_bioproject_overlap",
        ]
        if single_cell:
            manual_checks.extend(
                [
                    "broad_lineage_coverage",
                    "donor_level_replication",
                    "healthy_control_donors",
                ]
            )
        return {
            "rank": 0,
            "accession": accession,
            "source": row["source"],
            "selection_score": score,
            "selection_decision": decision,
            "proposed_role": proposed_role,
            "suggested_cases": cases or "",
            "suggested_controls": controls or "",
            "sample_count": row["sample_count"],
            "blocking_reasons": "|".join(blockers),
            "metadata_completeness": (
                "local_design_metadata"
                if not unknown_design
                else "repository_metadata_required"
            ),
            "manual_checks": "|".join(manual_checks),
            "assay": row["assay"],
            "title": row["title"],
            "source_uri": row["source_uri"],
            "automatic_eligibility": False,
        }

    @staticmethod
    def _title_key(value: str) -> str:
        return "".join(character.lower() for character in value if character.isalnum())

    @staticmethod
    def _rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @classmethod
    def _indexed(cls, path: Path) -> dict[str, dict[str, str]]:
        return {row["accession"]: row for row in cls._rows(path)}

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]) if rows else ("accession",),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
