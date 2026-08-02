"""Eligibility review for the E-MTAB-12805/GSE232131 single-cell study."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Emtab12805ReviewRun:
    decision: str
    accessions: int
    review_path: Path
    overlap_path: Path
    requirements_path: Path
    metadata_request_path: Path


class Emtab12805Reviewer:
    """Freeze the allowed uses and independence of a stimulated PBMC study."""

    ACCESSIONS = (
        ("E-MTAB-12805", "BioStudies-ArrayExpress", "PRJEB62155"),
        ("GSE232131", "GEO", "PRJNA971102"),
    )
    TITLE = (
        "T-cell instructed monocyte activation is a key pathological feature "
        "in Ankylosing Spondylitis and provides novel therapeutic opportunities"
    )

    def review(
        self,
        *,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/E-MTAB-12805"
        ),
    ) -> Emtab12805ReviewRun:
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        review_path = destination / "eligibility-review.json"
        overlap_path = destination / "repository-overlap.tsv"
        requirements_path = destination / "reference-requirements.tsv"
        metadata_request_path = destination / "missing-metadata-request.md"
        decision = "mechanistic_not_reference_ready"

        overlap_rows: list[dict[str, object]] = [
            {
                "accession": accession,
                "repository": repository,
                "project_accession": project,
                "cohort_cluster": "EMTAB12805_GSE232131",
                "independent_cohort_count": 1,
                "same_study_evidence": "identical_title_and_cross_repository_links",
                "count_in_validation_total": "once",
            }
            for accession, repository, project in self.ACCESSIONS
        ]
        requirement_rows: list[dict[str, object]] = [
            {
                "requirement": "independent_donor_identifiers",
                "status": "unverified",
                "impact": "blocks_donor_level_pseudobulk",
            },
            {
                "requirement": "healthy_control_donors",
                "status": "not_established_from_repository_summary",
                "impact": "blocks_case_control_validation",
            },
            {
                "requirement": "untreated_baseline_cells",
                "status": "present_but_mixed_with_ex_vivo_stimulation",
                "impact": "baseline_must_be_analysed_separately",
            },
            {
                "requirement": "whole_blood_lineage_coverage",
                "status": "failed_PBMC_assay",
                "impact": "cannot_calibrate_whole_blood_deconvolution",
            },
            {
                "requirement": "raw_or_donor_level_count_matrix",
                "status": "repository_files_exist_not_locally_audited",
                "impact": "blocks_reproducible_target_validation",
            },
        ]
        self._write(overlap_path, overlap_rows)
        self._write(requirements_path, requirement_rows)
        review_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "E-MTAB-12805",
                    "linked_accessions": [
                        "GSE232131",
                        "PRJEB62155",
                        "PRJNA971102",
                    ],
                    "title": self.TITLE,
                    "decision": decision,
                    "automatic_eligibility": False,
                    "independent_cohorts": 1,
                    "allowed_roles": [
                        "mechanistic_T_cell_monocyte_interaction",
                        "donor_level_cell_type_target_validation_if_metadata_passes",
                    ],
                    "prohibited_roles": [
                        "independent_replication_counted_twice",
                        "whole_blood_cell_composition_reference",
                        "case_control_validation_before_donor_audit",
                        "cell_level_pseudoreplication",
                    ],
                    "assay": {
                        "material": "PBMC",
                        "technology": "10x_single_cell_RNA_sequencing",
                        "conditions": [
                            "unstimulated",
                            "LPS_16h",
                            "anti_CD2_CD3_CD28_beads_16h",
                        ],
                        "organism": "Homo_sapiens",
                    },
                    "reasoning": [
                        (
                            "E-MTAB-12805 and GSE232131 are cross-repository "
                            "records for one study and must count once."
                        ),
                        (
                            "Ex-vivo stimulation is central to the design, so "
                            "stimulated cells are mechanistic rather than a "
                            "baseline disease-validation cohort."
                        ),
                        (
                            "PBMC data do not represent granulocytes and other "
                            "whole-blood components needed to calibrate the "
                            "current composition question."
                        ),
                        (
                            "Donor-level labels, controls, treatment exposure "
                            "and matrices must be audited before pseudobulk."
                        ),
                    ],
                    "advance_rule": (
                        "Download the processed matrices and complete a donor-level "
                        "sample audit; analyse unstimulated cells separately and "
                        "use donors, never cells, as independent replicates."
                    ),
                    "sources": [
                        "https://www.ebi.ac.uk/biostudies/arrayexpress/studies/E-MTAB-12805",
                        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE232131",
                        "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA971102",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        metadata_request_path.write_text(
            self._metadata_request(),
            encoding="utf-8",
        )
        return Emtab12805ReviewRun(
            decision=decision,
            accessions=len(overlap_rows),
            review_path=review_path,
            overlap_path=overlap_path,
            requirements_path=requirements_path,
            metadata_request_path=metadata_request_path,
        )

    @staticmethod
    def _metadata_request() -> str:
        return "\n".join(
            [
                "# E-MTAB-12805 / GSE232131 data audit request",
                "",
                "Before donor-level pseudobulk validation, obtain or verify:",
                "",
                "1. A unique donor identifier for every 10x library.",
                "2. Case/control diagnosis and donor counts.",
                "3. Medication exposure and sampling time for every donor.",
                "4. The mapping of donor, condition and sequencing library.",
                "5. Cell annotations and filtered/raw count matrices.",
                "6. Confirmation of paired conditions from the same donors.",
                "7. Batch, sex, age and other prespecified covariates.",
                "",
                (
                    "Keep unstimulated, LPS and T-cell-bead conditions separate. "
                    "Do not treat individual cells as biological replicates."
                ),
                "",
            ]
        )

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
