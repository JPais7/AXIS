"""Eligibility registry and publication-readiness audit for CD8 evidence."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Cd8EvidenceReviewRun:
    candidates: int
    eligible: int
    registry_path: Path
    readiness_path: Path
    protocol_path: Path


class Cd8EvidenceReviewer:
    """Freeze transparent inclusion decisions before adding another cohort."""

    def review(
        self,
        *,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/CD8-evidence-review"
        ),
    ) -> Cd8EvidenceReviewRun:
        rows = self._candidates()
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        registry_path = destination / "candidate-cohort-registry.tsv"
        readiness_path = destination / "publication-readiness.json"
        protocol_path = destination / "systematic-review-protocol.md"
        search_log_path = destination / "literature-search-log.tsv"
        request_path = destination / "author-data-request.md"
        self._write(registry_path, rows)
        self._write(search_log_path, self._search_log())
        eligible = sum(row["meta_analysis_eligible"] is True for row in rows)
        readiness_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "question": (
                        "Is DDX24 expression altered in donor-level human CD8 "
                        "cells from ankylosing spondylitis versus healthy controls?"
                    ),
                    "eligible_independent_cohorts": eligible,
                    "eligible_total_participants": 47,
                    "third_public_cohort_found": True,
                    "third_cohort_accession": "PRJNA1168183",
                    "third_cohort_status": (
                        "public_raw_reads_only; donor-resolved but 535.16 GB "
                        "of GEX reads and no processed matrix listed"
                    ),
                    "systematic_review_draft_possible": True,
                    "publication_ready_systematic_review": False,
                    "publication_ready_meta_analysis": False,
                    "blocking_requirements": [
                        "Run reproducible searches in at least two bibliographic "
                        "databases in addition to repository searches.",
                        "Complete title/abstract and full-text screening with a "
                        "second independent reviewer.",
                        "Obtain the processed donor-resolved matrix for "
                        "PRJNA1168183 or reprocess 535.16 GB of GEX reads.",
                        "Complete study-level risk-of-bias assessment.",
                        "Register the protocol before confirmatory updating.",
                    ],
                    "current_valid_claim": (
                        "Targeted cross-cohort synthesis of two independent "
                        "CD8 datasets; not yet a systematic-review meta-analysis."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        protocol_path.write_text(self._protocol(), encoding="utf-8")
        request_path.write_text(self._author_request(), encoding="utf-8")
        return Cd8EvidenceReviewRun(
            candidates=len(rows),
            eligible=eligible,
            registry_path=registry_path,
            readiness_path=readiness_path,
            protocol_path=protocol_path,
        )

    @staticmethod
    def _candidates() -> list[dict[str, object]]:
        return [
            {
                "accession": "PRJNA1168183",
                "cases": 14,
                "controls": 3,
                "assay": "scRNA-seq",
                "cd8_scope": "PBMC CD8 subsets",
                "donor_resolved": True,
                "public_expression": False,
                "meta_analysis_eligible": False,
                "decision": "request_processed_matrix",
                "reason": (
                    "third cohort identified; 17 donor GEX runs total "
                    "535.16 GB and processed matrix is not listed"
                ),
                "source": "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1168183",
            },
            {
                "accession": "GSE194315",
                "cases": 10,
                "controls": 29,
                "assay": "scRNA/CITE-seq",
                "cd8_scope": "CD8 TEM",
                "donor_resolved": True,
                "public_expression": True,
                "meta_analysis_eligible": True,
                "decision": "include",
                "reason": "donor-level case-control CD8 expression",
                "source": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE194315",
            },
            {
                "accession": "GSE288581",
                "cases": 4,
                "controls": 4,
                "assay": "scRNA-seq",
                "cd8_scope": "CD45RO-positive CD8 memory",
                "donor_resolved": True,
                "public_expression": True,
                "meta_analysis_eligible": True,
                "decision": "include",
                "reason": "donor-level case-control sorted CD8 expression",
                "source": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE288581",
            },
            {
                "accession": "HRA001027",
                "cases": 1,
                "controls": 1,
                "assay": "scRNA-seq",
                "cd8_scope": "PBMC CD8 subset",
                "donor_resolved": False,
                "public_expression": False,
                "meta_analysis_eligible": False,
                "decision": "exclude_from_inference",
                "reason": "one pooled library per group; no donor replication",
                "source": "https://ngdc.cncb.ac.cn/gsa-human/browse/HRA001027",
            },
            {
                "accession": "GSE157595",
                "cases": 1,
                "controls": 1,
                "assay": "scATAC-seq",
                "cd8_scope": "PBMC CD8 subset",
                "donor_resolved": False,
                "public_expression": True,
                "meta_analysis_eligible": False,
                "decision": "mechanistic_only",
                "reason": "chromatin accessibility is not RNA expression",
                "source": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE157595",
            },
            {
                "accession": "GSE277791",
                "cases": 6,
                "controls": 0,
                "assay": "scRNA-seq",
                "cd8_scope": "PBMC CD8 subset",
                "donor_resolved": False,
                "public_expression": True,
                "meta_analysis_eligible": False,
                "decision": "treatment_mechanism_only",
                "reason": "no healthy controls and pooled TNFi-response libraries",
                "source": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE277791",
            },
            {
                "accession": "female_AS_multimodal_2022",
                "cases": 3,
                "controls": 5,
                "assay": "scRNA/TCR/ADT",
                "cd8_scope": "PBMC CD8 subsets",
                "donor_resolved": True,
                "public_expression": False,
                "meta_analysis_eligible": False,
                "decision": "contact_authors",
                "reason": "potential third cohort; reusable matrices not located",
                "source": "https://doi.org/10.1002/ctm2.1066",
            },
        ]

    @staticmethod
    def _search_log() -> list[dict[str, object]]:
        searched = "2026-07-30"
        return [
            {
                "source": "PubMed",
                "date_searched": searched,
                "query": (
                    '(ankylosing spondylitis OR axial spondyloarthritis) AND '
                    '(single-cell OR single cell) AND (RNA sequencing OR '
                    'transcriptom*) AND (CD8 OR peripheral blood OR PBMC)'
                ),
                "scope": "inception_to_search_date",
                "status": "executed_primary_pass",
            },
            {
                "source": "NCBI GEO/SRA",
                "date_searched": searched,
                "query": (
                    "ankylosing spondylitis AND Homo sapiens AND "
                    "single-cell RNA sequencing"
                ),
                "scope": "public_repository_records",
                "status": "executed_and_accessions_audited",
            },
            {
                "source": "BioStudies/ArrayExpress",
                "date_searched": searched,
                "query": (
                    "ankylosing spondylitis OR axial spondyloarthritis; "
                    "single-cell transcriptomics"
                ),
                "scope": "public_repository_records",
                "status": "executed_primary_pass",
            },
            {
                "source": "Embase_or_Web_of_Science",
                "date_searched": "",
                "query": "adapt PubMed concepts and controlled vocabulary",
                "scope": "inception_to_search_date",
                "status": "requires_institutional_access_and_second_reviewer",
            },
        ]

    @staticmethod
    def _author_request() -> str:
        return """# Data request: female AS single-cell cohort

To: Prof. Tai-Ming Ko <tmko@nycu.edu.tw>
Subject: Request for donor-resolved processed scRNA-seq data from Chen et al. (2022)

Dear Professor Ko,

I am conducting a reproducible secondary analysis of donor-level CD8 T-cell
gene expression in ankylosing spondylitis and healthy controls. Your study,
“Multimodal single-cell analysis provides novel insights on ankylosing
spondylitis in females” (Clinical and Translational Medicine, 2022;
doi:10.1002/ctm2.1066), is potentially an important independent validation
cohort.

Could you please share, or point me to a repository containing:

1. the processed gene-by-cell RNA count matrix;
2. cell barcodes and gene annotations;
3. donor-level metadata linking cells to the three AS participants and five
   healthy controls;
4. the cell-type or cluster annotations used in the paper; and
5. any relevant batch, treatment and clinical-status variables.

The primary analysis is predeclared and limited to donor-level pseudobulk
expression of DDX24 in CD8 T-cell populations. Participants, rather than cells,
will be treated as independent statistical units. The study will be cited and
the original cohort will not be redistributed beyond the permissions you
specify.

I would be grateful for any processed Seurat object, h5ad file, Matrix Market
files, or equivalent data that preserve donor identifiers.

Kind regards,

[Your name]
[Institution, if applicable]
[Contact email]
"""

    @staticmethod
    def _protocol() -> str:
        return """# Protocol: DDX24 expression in CD8 cells in ankylosing spondylitis

## Review question

In humans with ankylosing spondylitis, is donor-level DDX24 RNA expression in
peripheral-blood CD8 T cells different from healthy controls?

## Eligibility

Include human case-control RNA-expression studies with separable CD8 cells,
at least two biological participants per group, donor-resolved labels, and
available effect estimates or expression matrices. Exclude stimulated-only
contrasts, studies without healthy controls, pooled libraries without
participant resolution, non-RNA assays, and duplicated repository records.

## Search and screening

Search MEDLINE/PubMed, Embase or Web of Science, GEO, BioStudies/ArrayExpress,
SRA and GSA-Human from inception. Preserve complete queries, dates, deduplicated
records, exclusion reasons and a PRISMA flow. Two reviewers independently screen
titles/abstracts and full texts; resolve disagreements by consensus.

## Outcomes and synthesis

The primary outcome is case-minus-control log2-normalized DDX24 expression in a
predeclared memory/effector CD8 population. Use the human participant as the
statistical unit. Pool compatible standardized or common-scale effects with a
random-effects model; report fixed-effect sensitivity, confidence intervals,
prediction interval when at least three studies exist, tau-squared, I-squared,
leave-one-study-out results and CD8-state sensitivity. Do not combine multiple
cell states from the same participants as independent studies.

## Bias and certainty

Assess participant selection, phenotype definition, treatment/confounding,
sample processing, donor-level analysis, missing data and selective reporting.
Grade certainty separately from statistical significance. Treat the present
two-cohort synthesis as hypothesis-strengthening evidence, not causality or
therapeutic validation.
"""

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
