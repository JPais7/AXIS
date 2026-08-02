"""Auditable registry and decision rules for single-cell replication cohorts."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ReplicationPlanRun:
    studies: int
    eligible: int
    output_path: Path
    candidate_path: Path
    summary_path: Path


class SingleCellReplicationPlanner:
    """Separate direct replication, orthogonal evidence and response studies."""

    STUDIES: tuple[dict[str, object], ...] = (
        {
            "accession": "GSE194315",
            "title": "AS PBMC CITE-seq discovery cohort",
            "cases": 10,
            "controls": 29,
            "independent_from_discovery": False,
            "healthy_controls": True,
            "subject_level_available": True,
            "processed_counts_available": True,
            "primary_cell_scope": "PBMC including CD4 TCM and CD8 TEM",
            "role": "discovery_only",
            "source_url": (
                "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE194315"
            ),
            "limitation": "already used for discovery",
        },
        {
            "accession": "PRJNA749866",
            "title": "AS PBMC single-cell NK study",
            "cases": 3,
            "controls": 3,
            "independent_from_discovery": True,
            "healthy_controls": True,
            "subject_level_available": True,
            "processed_counts_available": False,
            "primary_cell_scope": "PBMC with detailed NK subsets",
            "role": "secondary_direct_replication",
            "source_url": "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA749866",
            "limitation": (
                "small cohort; raw SRA processing required; strongest for NK "
                "rather than CD4 TCM or CD8 TEM"
            ),
        },
        {
            "accession": "GSE277791",
            "title": "TNF inhibitor response in AS PBMC",
            "cases": 6,
            "controls": 0,
            "independent_from_discovery": True,
            "healthy_controls": False,
            "subject_level_available": False,
            "processed_counts_available": True,
            "primary_cell_scope": "pooled PBMC pre/post TNF inhibitor",
            "role": "treatment_response_only",
            "source_url": (
                "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE277791"
            ),
            "limitation": (
                "no healthy controls and donors are pooled; cannot replicate "
                "disease-versus-control effects"
            ),
        },
        {
            "accession": "PUBLICATION_25_SUBJECT_CITESEQ",
            "title": "HLA-B27 AS and acute anterior uveitis CITE-seq",
            "cases": 10,
            "controls": 10,
            "independent_from_discovery": True,
            "healthy_controls": True,
            "subject_level_available": True,
            "processed_counts_available": False,
            "primary_cell_scope": "PBMC with detailed TNK phenotypes",
            "role": "preferred_direct_replication_pending_data",
            "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11926545/",
            "limitation": (
                "full-text and supplementary audit found only GSE194315, cited "
                "as a prior validation dataset; no primary accession was "
                "reported reproducibly"
            ),
        },
    )

    def build(
        self,
        candidate_path: str | Path,
        *,
        output_root: str | Path = Path("data/single-cell/independent-replication"),
    ) -> ReplicationPlanRun:
        studies = [self._assess(dict(study)) for study in self.STUDIES]
        candidates = self._candidate_rows(Path(candidate_path), studies)
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "study-eligibility.tsv"
        candidate_path_out = destination / "candidate-replication-plan.tsv"
        summary_path = destination / "replication-plan.json"
        self._write(output_path, studies)
        self._write(candidate_path_out, candidates)
        eligible = sum(
            bool(row["direct_replication_eligible"]) for row in studies
        )
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "independent_single_cell_replication_plan",
                    "created_at": datetime.now(UTC).isoformat(),
                    "studies_reviewed": len(studies),
                    "direct_replication_eligible_now": eligible,
                    "primary_recommendation": (
                        "request the primary accession or processed object for "
                        "the independent 25-subject HLA-B27 CITE-seq cohort"
                    ),
                    "secondary_recommendation": (
                        "process PRJNA749866 only as a low-powered, NK-enriched "
                        "secondary replication"
                    ),
                    "exclusion_rule": (
                        "datasets without healthy controls or independent "
                        "subject-level replication cannot validate disease effects"
                    ),
                    "computational_gate": (
                        "raw SRA reconstruction is not started automatically "
                        "because it requires large downloads, Cell Ranger/reference "
                        "resources and materially more computation"
                    ),
                    "warning": (
                        "A non-significant result in a 3-versus-3 cohort cannot "
                        "exclude a true effect; direction and uncertainty must be "
                        "reported together."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ReplicationPlanRun(
            studies=len(studies),
            eligible=eligible,
            output_path=output_path,
            candidate_path=candidate_path_out,
            summary_path=summary_path,
        )

    @staticmethod
    def _assess(study: dict[str, object]) -> dict[str, object]:
        eligible = all(
            (
                study["independent_from_discovery"],
                study["healthy_controls"],
                study["subject_level_available"],
            )
        )
        executable = bool(eligible and study["processed_counts_available"])
        if executable:
            status = "ready"
        elif eligible:
            status = "eligible_but_data_processing_blocked"
        else:
            status = "not_eligible_for_direct_replication"
        study["direct_replication_eligible"] = eligible
        study["executable_now"] = executable
        study["status"] = status
        return study

    @staticmethod
    def _candidate_rows(
        path: Path, studies: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        with path.open(encoding="utf-8", newline="") as source:
            candidates = [
                row
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("decision") == "generate_causal_evidence"
            ]
        direct = [
            str(row["accession"])
            for row in studies
            if row["direct_replication_eligible"]
        ]
        return [
            {
                "gene_symbol": row["gene_symbol"],
                "current_decision": row["decision"],
                "replication_accessions": "|".join(direct),
                "primary_cell_type": row.get("best_cell_type", ""),
                "required_statistical_unit": "subject",
                "success_rule": (
                    "same direction with effect estimate and confidence interval; "
                    "FDR is supportive but not required in the 3+3 cohort"
                ),
                "failure_rule": (
                    "opposite direction with a precise interval triggers "
                    "deprioritisation; imprecise null remains inconclusive"
                ),
                "next_action": (
                    "resolve_25_subject_processed_data_then_run_pseudobulk"
                ),
            }
            for row in candidates
        ]

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
