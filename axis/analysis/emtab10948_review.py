"""Eligibility and paired-tissue audit for E-MTAB-10948."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Emtab10948ReviewRun:
    decision: str
    participants: int
    biological_samples: int
    review_path: Path
    sample_sheet_path: Path
    file_inventory_path: Path


class Emtab10948Reviewer:
    """Keep a small paired-tissue Treg study in its defensible role."""

    def review(
        self,
        *,
        study_audit_path: str | Path,
        sdrf_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/E-MTAB-10948"
        ),
    ) -> Emtab10948ReviewRun:
        upstream = json.loads(
            Path(study_audit_path).read_text(encoding="utf-8")
        )
        if upstream.get("accession") != "E-MTAB-10948":
            raise ValueError("expected the E-MTAB-10948 participant audit")
        rows = self._sdrf_rows(Path(sdrf_path))
        samples = self._biological_samples(rows)
        participants = {str(row["participant_id"]) for row in samples}
        if len(participants) != 2 or len(samples) != 4:
            raise ValueError(
                "E-MTAB-10948 does not match the frozen 2-donor paired design"
            )
        if {str(row["tissue"]) for row in samples} != {
            "peripheral_blood",
            "synovial_fluid",
        }:
            raise ValueError("E-MTAB-10948 paired tissues are incomplete")

        files = self._processed_files(rows)
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        review_path = destination / "eligibility-review.json"
        sample_sheet_path = destination / "participant-tissue-sheet.tsv"
        file_inventory_path = destination / "processed-file-inventory.tsv"
        self._write(sample_sheet_path, samples)
        self._write(file_inventory_path, files)
        decision = "mechanistic_paired_tissue_only"
        review_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "E-MTAB-10948",
                    "decision": decision,
                    "automatic_eligibility": False,
                    "automatic_download": False,
                    "participants": {
                        "ankylosing_spondylitis": len(participants),
                        "healthy_controls": 0,
                        "ids": sorted(participants),
                        "HLA_B27": "positive",
                        "paired_tissues_per_participant": 2,
                    },
                    "biological_samples": len(samples),
                    "assay": {
                        "technology": "10x_5prime_single_cell_RNA_and_VDJ",
                        "cell_scope": (
                            "CD3_positive_CD45RA_negative_CD25_positive_"
                            "CD127_low_regulatory_T_cells"
                        ),
                        "tissues": [
                            "peripheral_blood",
                            "synovial_fluid",
                        ],
                    },
                    "allowed_roles": [
                        "paired_blood_synovial_Treg_mechanism",
                        "target_localisation_in_Tregs",
                        "hypothesis_generation_for_inflamed_joint",
                    ],
                    "prohibited_roles": [
                        "AS_versus_healthy_validation",
                        "whole_blood_cell_composition_reference",
                        "broad_PBMC_cell_atlas",
                        "independent_donor_replication_with_n_2",
                        "combining_blood_and_synovial_cells_as_replicates",
                    ],
                    "limitations": [
                        "Only two AS participants and no healthy controls.",
                        (
                            "The enriched Treg population does not represent "
                            "whole blood or broad PBMC composition."
                        ),
                        (
                            "Blood and synovial fluid are paired tissues from "
                            "the same people, not independent participants."
                        ),
                        (
                            "The associated publication also analyses a "
                            "separate psoriatic-arthritis dataset, E-MTAB-9492."
                        ),
                    ],
                    "advance_rule": (
                        "Download processed matrices only for a preregistered "
                        "paired-tissue Treg analysis; use participant as the "
                        "unit and report the result as mechanistic."
                    ),
                    "publication": {
                        "title": (
                            "Single cell analysis of spondyloarthritis "
                            "regulatory T cells identifies distinct synovial "
                            "gene expression patterns and clonal fates"
                        ),
                        "pmid": "34907325",
                    },
                    "sources": [
                        (
                            "https://www.ebi.ac.uk/biostudies/arrayexpress/"
                            "studies/E-MTAB-10948"
                        ),
                        "https://pubmed.ncbi.nlm.nih.gov/34907325/",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Emtab10948ReviewRun(
            decision=decision,
            participants=len(participants),
            biological_samples=len(samples),
            review_path=review_path,
            sample_sheet_path=sample_sheet_path,
            file_inventory_path=file_inventory_path,
        )

    @staticmethod
    def _sdrf_rows(path: Path) -> list[list[str]]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.reader(source, delimiter="\t"))
        if len(rows) < 2 or rows[0][:14] != [
            "Source Name",
            "Comment[ENA_SAMPLE]",
            "Comment[BioSD_SAMPLE]",
            "Characteristics[organism]",
            "Characteristics[individual]",
            "Characteristics[sex]",
            "Characteristics[age]",
            "Unit[time unit]",
            "Characteristics[developmental stage]",
            "Characteristics[disease]",
            "Characteristics[organism part]",
            "Characteristics[cell type]",
            "Characteristics[immunophenotype]",
            "Characteristics[clinical information]",
        ]:
            raise ValueError("unexpected E-MTAB-10948 SDRF schema")
        return rows[1:]

    @staticmethod
    def _biological_samples(
        rows: list[list[str]],
    ) -> list[dict[str, object]]:
        unique: dict[str, dict[str, object]] = {}
        for row in rows:
            source = row[0]
            tissue = (
                "peripheral_blood"
                if row[10].strip().lower() == "blood"
                else "synovial_fluid"
            )
            unique[source] = {
                "biological_sample_id": source,
                "participant_id": row[4].strip(),
                "diagnosis": row[9].strip().replace(" ", "_"),
                "sex": row[5].strip(),
                "age": row[6].strip(),
                "tissue": tissue,
                "cell_type": row[11].strip().replace(" ", "_"),
                "immunophenotype": row[12].strip().replace("; ", ";"),
                "clinical_information": row[13].strip().replace(" ", "_"),
                "healthy_control": False,
                "case_control_eligible": False,
                "paired_tissue_eligible": True,
            }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _processed_files(rows: list[list[str]]) -> list[dict[str, object]]:
        found: dict[str, dict[str, object]] = {}
        for row in rows:
            for value in row:
                if "E-MTAB-10948.processed." not in value:
                    continue
                uri = value.replace("ftp://", "https://")
                found[uri] = {
                    "source_uri": uri,
                    "file_name": uri.rsplit("/", 1)[-1],
                    "content": (
                        "matrix"
                        if ".processed.1." in uri
                        else "features"
                        if ".processed.2." in uri
                        else "barcodes"
                    ),
                    "download_status": "not_downloaded",
                    "download_priority": (
                        "optional_mechanistic_analysis_only"
                    ),
                }
        if len(found) != 3:
            raise ValueError(
                "expected three E-MTAB-10948 processed archives"
            )
        return [found[key] for key in sorted(found)]

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
