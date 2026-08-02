"""Incremental study intake that cannot contaminate frozen discovery cohorts."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class StudyQuarantineRun:
    candidates: int
    direct_axspa: int
    queue_path: Path
    snapshot_path: Path


class StudyQuarantineBuilder:
    """Build a review queue while keeping every new study outside discovery."""

    FROZEN = {"GSE25101", "GSE18781", "GSE73754"}
    USED_VALIDATION = {"GSE181364", "GSE194315"}

    def build(
        self,
        *,
        geo_catalog_path: str | Path,
        cross_repository_path: str | Path,
        output_root: str | Path = Path("data/catalog/incremental-quarantine"),
    ) -> StudyQuarantineRun:
        geo_path = Path(geo_catalog_path)
        cross_path = Path(cross_repository_path)
        rows = self._geo(geo_path) + self._cross(cross_path)
        unique: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            key = (str(row["source"]), str(row["accession"]))
            unique.setdefault(key, row)
        candidates = sorted(
            unique.values(),
            key=lambda row: (
                -int(str(row["priority_score"])),
                str(row["accession"]),
            ),
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        queue_path = destination / "study-review-queue.tsv"
        snapshot_path = destination / "quarantine-snapshot.json"
        self._write(queue_path, candidates)
        snapshot_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "incremental_study_quarantine",
                    "candidate_count": len(candidates),
                    "direct_axspa_candidates": sum(
                        row["disease_signal"] == "axspa_specific"
                        for row in candidates
                    ),
                    "frozen_discovery": sorted(self.FROZEN),
                    "used_validation": sorted(self.USED_VALIDATION),
                    "source_checksums": {
                        str(geo_path): self._sha256(geo_path),
                        str(cross_path): self._sha256(cross_path),
                    },
                    "guardrails": [
                        "No quarantined study is automatically eligible.",
                        "Discovery cohorts cannot be changed by this command.",
                        (
                            "Participant, publication and BioProject overlap "
                            "require review."
                        ),
                        "New eligible studies enter validation, not discovery.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return StudyQuarantineRun(
            candidates=len(candidates),
            direct_axspa=sum(
                row["disease_signal"] == "axspa_specific" for row in candidates
            ),
            queue_path=queue_path,
            snapshot_path=snapshot_path,
        )

    def _geo(self, path: Path) -> list[dict[str, object]]:
        with path.open(encoding="utf-8", newline="") as source:
            return [
                self._row(
                    source_name="GEO",
                    accession=row["accession"],
                    title=row["title"],
                    disease_signal=(
                        "axspa_specific"
                        if "axspa_direct" in row.get("query_families", "")
                        else "related_disease"
                    ),
                    assay=row["experiment_type"],
                    samples=row["sample_count"],
                    bioproject=row["bioproject_id"],
                    publications=row["publication_ids"],
                    overlap=(
                        "catalog_overlap_flag"
                        if row.get("shared_publication_flag") == "True"
                        or row.get("shared_bioproject_flag") == "True"
                        else "not_detected"
                    ),
                    source_uri=row["source_uri"],
                )
                for row in csv.DictReader(source, delimiter="\t")
                if row["accession"] not in self.FROZEN | self.USED_VALIDATION
                and row.get("primary_role") == "direct_disease_candidate"
            ]

    def _cross(self, path: Path) -> list[dict[str, object]]:
        with path.open(encoding="utf-8", newline="") as source:
            return [
                self._row(
                    source_name=row["source"],
                    accession=row["accession"],
                    title=row["title"],
                    disease_signal=row["disease_signal"],
                    assay=row["assay"],
                    samples=row["sample_or_run_count"],
                    bioproject=row["bioproject_id"],
                    publications=row["publication_ids"],
                    overlap=row["overlap_status"],
                    source_uri=row["source_uri"],
                )
                for row in csv.DictReader(source, delimiter="\t")
                if row["accession"] not in self.FROZEN | self.USED_VALIDATION
                and row.get("disease_signal") in {"axspa_specific", "spa_related"}
            ]

    @staticmethod
    def _row(
        *,
        source_name: str,
        accession: str,
        title: str,
        disease_signal: str,
        assay: str,
        samples: str,
        bioproject: str,
        publications: str,
        overlap: str,
        source_uri: str,
    ) -> dict[str, object]:
        expression = "expression" in assay.lower() or "rna" in assay.lower()
        single_cell = "single" in assay.lower()
        direct = disease_signal == "axspa_specific"
        priority = 4 * int(direct) + 2 * int(expression) + int(single_cell)
        return {
            "source": source_name,
            "accession": accession,
            "priority_score": priority,
            "quarantine_status": "manual_review_required",
            "proposed_role": "independent_validation",
            "disease_signal": disease_signal,
            "assay": assay,
            "sample_count": samples,
            "bioproject_id": bioproject,
            "publication_ids": publications,
            "overlap_status": overlap,
            "title": title,
            "source_uri": source_uri,
            "required_review": (
                "participant_overlap|case_control_design|tissue|treatment|"
                "raw_or_normalized_data|covariates"
            ),
        }

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

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
