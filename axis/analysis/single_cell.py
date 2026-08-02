"""Subject-aware design planning for processed single-cell studies."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class SingleCellPlanRun:
    included_cells: int
    case_subjects: int
    control_subjects: int
    eligible_cell_types: int
    output_path: Path
    subject_path: Path
    summary_path: Path


class SingleCellPlanBuilder:
    """Build a pseudobulk design without cell-level pseudoreplication."""

    def build(
        self,
        metadata_path: str | Path,
        *,
        accession: str = "GSE194315",
        case_status: str = "AXI",
        control_status: str = "Healthy",
        target_genes: tuple[str, ...] = ("CD2", "IL2RB", "IKZF3"),
        minimum_cells_per_subject: int = 20,
        minimum_subjects_per_group: int = 5,
        output_root: str | Path = Path("data/single-cell/GSE194315/plan"),
    ) -> SingleCellPlanRun:
        if minimum_cells_per_subject < 1 or minimum_subjects_per_group < 2:
            raise ValueError("single-cell design thresholds are invalid")
        metadata = Path(metadata_path)
        rows = self._read(metadata, {case_status, control_status})
        counts: dict[tuple[str, str, str], int] = defaultdict(int)
        samples: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            key = (row["CellType"], row["Subject"], row["Status"])
            counts[key] += 1
            samples[row["Subject"]].add(row["Sample"])
        subjects = sorted(
            {(subject, status) for _, subject, status in counts},
            key=lambda item: (item[1], item[0]),
        )
        cell_types = sorted({cell_type for cell_type, _, _ in counts})
        design_rows: list[dict[str, object]] = []
        for cell_type in cell_types:
            case_counts = {
                subject: count
                for (kind, subject, status), count in counts.items()
                if kind == cell_type
                and status == case_status
                and count >= minimum_cells_per_subject
            }
            control_counts = {
                subject: count
                for (kind, subject, status), count in counts.items()
                if kind == cell_type
                and status == control_status
                and count >= minimum_cells_per_subject
            }
            eligible = (
                len(case_counts) >= minimum_subjects_per_group
                and len(control_counts) >= minimum_subjects_per_group
            )
            design_rows.append(
                {
                    "cell_type": cell_type,
                    "case_subjects_with_minimum_cells": len(case_counts),
                    "control_subjects_with_minimum_cells": len(control_counts),
                    "case_cells": sum(case_counts.values()),
                    "control_cells": sum(control_counts.values()),
                    "minimum_cells_per_subject": minimum_cells_per_subject,
                    "minimum_subjects_per_group": minimum_subjects_per_group,
                    "eligible_for_pseudobulk": eligible,
                    "exclusion_reason": (
                        "" if eligible else "insufficient_subjects_with_minimum_cells"
                    ),
                }
            )
        design_rows.sort(
            key=lambda row: (
                not bool(row["eligible_for_pseudobulk"]),
                -int(str(row["case_cells"])),
                str(row["cell_type"]),
            )
        )
        subject_rows: list[dict[str, object]] = [
            {
                "subject": subject,
                "status": status,
                "analysis_group": ("case" if status == case_status else "control"),
                "samples": "|".join(sorted(samples[subject])),
                "included_cells": sum(
                    count
                    for (_, candidate, _), count in counts.items()
                    if candidate == subject
                ),
                "statistical_unit": "subject",
            }
            for subject, status in subjects
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "cell-type-design.tsv"
        self._write(output_path, design_rows)
        subject_path = destination / "subject-design.tsv"
        self._write(subject_path, subject_rows)
        case_subjects = sum(row["status"] == case_status for row in subject_rows)
        control_subjects = sum(row["status"] == control_status for row in subject_rows)
        eligible_count = sum(
            bool(row["eligible_for_pseudobulk"]) for row in design_rows
        )
        summary_path = destination / "single-cell-plan.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "subject_aware_single_cell_plan",
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": accession,
                    "source": "NCBI Gene Expression Omnibus",
                    "metadata_path": str(metadata),
                    "metadata_checksum": (
                        "sha256:" + hashlib.sha256(metadata.read_bytes()).hexdigest()
                    ),
                    "case_status": case_status,
                    "control_status": control_status,
                    "included_cells": len(rows),
                    "case_subjects": case_subjects,
                    "control_subjects": control_subjects,
                    "cell_types": len(design_rows),
                    "eligible_cell_types": eligible_count,
                    "target_genes": list(target_genes),
                    "primary_cell_types": ["CD4 TCM", "CD8 TEM"],
                    "model": (
                        "aggregate raw counts by subject and cell type; compare "
                        "subjects with a count-aware pseudobulk model"
                    ),
                    "independence_policy": (
                        "subjects are biological replicates; cells are repeated "
                        "measurements and must never be tested as independent"
                    ),
                    "multiple_testing": (
                        "targeted three-gene results remain separate from any "
                        "transcriptome-wide false-discovery analysis"
                    ),
                    "matrix_requirement": (
                        "raw or integer gene-by-cell counts aligned exactly to "
                        "CellName; normalized values are not accepted as counts"
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SingleCellPlanRun(
            included_cells=len(rows),
            case_subjects=case_subjects,
            control_subjects=control_subjects,
            eligible_cell_types=eligible_count,
            output_path=output_path,
            subject_path=subject_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _read(path: Path, statuses: set[str]) -> list[dict[str, str]]:
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", encoding="utf-8", newline="") as source:
                return [
                    row
                    for row in csv.DictReader(source, delimiter="\t")
                    if row.get("IncludedInStudy", "").upper() == "TRUE"
                    and row.get("Status") in statuses
                    and row.get("CellType", "").strip()
                    and row.get("Subject", "").strip()
                ]
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(
                f"cannot read single-cell metadata {path}: {error}"
            ) from error

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("subject",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
