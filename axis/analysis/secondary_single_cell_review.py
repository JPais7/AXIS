"""Metadata-only review of secondary single-cell validation cohorts."""

from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SecondarySingleCellReviewRun:
    candidates: int
    selected_accession: str
    review_path: Path
    sample_path: Path
    summary_path: Path


class SecondarySingleCellReviewer:
    """Select a defensible external cohort before a large download."""

    def review(
        self,
        *,
        gse277117_matrices: tuple[str | Path, ...],
        gse288581_matrix: str | Path,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/secondary-cohorts"
        ),
    ) -> SecondarySingleCellReviewRun:
        rows277 = [
            row
            for matrix in gse277117_matrices
            for row in self._samples(Path(matrix))
        ]
        rows288 = self._samples(Path(gse288581_matrix))
        samples = self._sample_rows(rows277, rows288)
        reviews = [
            {
                "accession": "GSE288581",
                "decision": "selected_targeted_CD8_external_validation",
                "case_participants": 4,
                "control_participants": 4,
                "tissue": "peripheral_blood",
                "cell_scope": "FACS_sorted_CD45RO_positive_CD8_T_cells",
                "longitudinal_or_treatment": False,
                "pooled_participants": False,
                "broad_PBMC_reference": False,
                "priority": 1,
                "reason": (
                    "Independent AS and healthy blood donors; suitable for "
                    "targeted CD8-memory validation, not broad composition."
                ),
            },
            {
                "accession": "GSE277117",
                "decision": "mechanistic_treatment_response_only",
                "case_participants": 25,
                "control_participants": 0,
                "tissue": "PBMC",
                "cell_scope": "broad_PBMC",
                "longitudinal_or_treatment": True,
                "pooled_participants": True,
                "broad_PBMC_reference": False,
                "priority": 2,
                "reason": (
                    "TNF/IL17 inhibitor response study with no healthy controls "
                    "and multiple pooled libraries."
                ),
            },
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        review_path = destination / "candidate-decisions.tsv"
        sample_path = destination / "sample-inventory.tsv"
        summary_path = destination / "secondary-cohort-review.json"
        self._write(review_path, reviews)
        self._write(sample_path, samples)
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "selected_accession": "GSE288581",
                    "selected_role": (
                        "independent_targeted_CD8_memory_validation"
                    ),
                    "case_participants": 4,
                    "control_participants": 4,
                    "automatic_large_download": False,
                    "advance_rule": (
                        "Inventory processed GEX matrices and estimate download "
                        "size before testing DDX24; retain participant as unit."
                    ),
                    "sources": [
                        (
                            "https://www.ncbi.nlm.nih.gov/geo/query/"
                            "acc.cgi?acc=GSE288581"
                        ),
                        (
                            "https://www.ncbi.nlm.nih.gov/geo/query/"
                            "acc.cgi?acc=GSE277117"
                        ),
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SecondarySingleCellReviewRun(
            candidates=2,
            selected_accession="GSE288581",
            review_path=review_path,
            sample_path=sample_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _samples(path: Path) -> list[dict[str, str]]:
        metadata: dict[str, list[str]] = {}
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            for row in csv.reader(source, delimiter="\t"):
                if row and row[0] in {
                    "!Sample_title",
                    "!Sample_geo_accession",
                    "!Sample_source_name_ch1",
                }:
                    metadata[row[0]] = row[1:]
        return [
            {
                "accession": path.name.split("_", 1)[0].split("-", 1)[0],
                "library_id": library,
                "title": title,
                "source": source,
            }
            for library, title, source in zip(
                metadata["!Sample_geo_accession"],
                metadata["!Sample_title"],
                metadata["!Sample_source_name_ch1"],
                strict=True,
            )
        ]

    @staticmethod
    def _sample_rows(
        rows277: list[dict[str, str]],
        rows288: list[dict[str, str]],
    ) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows277 + rows288:
            if row["library_id"] in seen:
                continue
            seen.add(row["library_id"])
            title = row["title"]
            is288 = row["accession"] == "GSE288581"
            gex = "_GEX" in title or ", scRNA," in title
            donors = (
                (
                    re.findall(r"(?:SF|PB)(\d+(?:-\d+)?)", title)
                    or re.findall(r"HC(\d+)", title)
                )
                if is288
                else re.findall(r"KAS\d+", title)
            )
            output.append(
                {
                    **row,
                    "assay_component": (
                        "gene_expression"
                        if gex
                        else "TCR_or_CITE_or_WGS"
                    ),
                    "participant_ids": ";".join(dict.fromkeys(donors)),
                    "participant_count": len(set(donors)),
                    "group": (
                        "healthy_control"
                        if title.startswith("HC")
                        else "ankylosing_spondylitis"
                    ),
                    "baseline": "Pre" in title or is288,
                    "eligible_library": gex,
                }
            )
        return output

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
