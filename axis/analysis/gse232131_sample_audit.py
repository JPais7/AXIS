"""Donor, condition and file audit for the GSE232131 single-cell study."""

from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Gse232131SampleAuditRun:
    decision: str
    libraries: int
    donors: int
    sample_sheet_path: Path
    file_inventory_path: Path
    audit_path: Path


class Gse232131SampleAuditor:
    """Parse GEO metadata and reject invalid biological replication."""

    CONDITIONS = {
        "Unsti": "unstimulated_16h",
        "LPS": "LPS_16h",
        "TAB": "T_cell_activation_beads_16h",
    }

    def audit(
        self,
        *,
        matrix_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/E-MTAB-12805/sample-audit"
        ),
    ) -> Gse232131SampleAuditRun:
        metadata = self._metadata(Path(matrix_path))
        accessions = metadata["!Sample_geo_accession"]
        titles = metadata["!Sample_title"]
        biosamples = self._relation_ids(
            metadata["!Sample_relation"], "biosample"
        )
        experiments = self._relation_ids(metadata["!Sample_relation"], "sra")
        files = metadata["!Sample_supplementary_file_1"]
        if not all(
            len(values) == len(accessions)
            for values in (titles, biosamples, experiments, files)
        ):
            raise ValueError("GSE232131 sample metadata columns are inconsistent")

        rows: list[dict[str, object]] = []
        inventory: list[dict[str, object]] = []
        donors: set[str] = set()
        for accession, title, biosample, experiment, source_uri in zip(
            accessions,
            titles,
            biosamples,
            experiments,
            files,
            strict=True,
        ):
            sample_donors = tuple(dict.fromkeys(re.findall(r"AS\d+", title)))
            if not sample_donors:
                raise ValueError(f"cannot identify donor in {title}")
            donors.update(sample_donors)
            condition = self._condition(title)
            pooled = len(sample_donors) > 1
            rows.append(
                {
                    "library_id": accession,
                    "sample_title": title,
                    "donor_ids": ";".join(sample_donors),
                    "donor_count": len(sample_donors),
                    "biological_unit": (
                        "pool_" + "_".join(sample_donors)
                        if pooled
                        else sample_donors[0]
                    ),
                    "diagnosis": "ankylosing_spondylitis",
                    "healthy_control": False,
                    "condition": condition,
                    "paired_condition_set": "yes",
                    "pooled_donors": pooled,
                    "donor_level_pseudobulk_eligible": not pooled,
                    "case_control_eligible": False,
                    "allowed_role": (
                        "within_unit_stimulation_mechanism"
                        if pooled
                        else "within_donor_stimulation_mechanism"
                    ),
                    "biosample": biosample,
                    "sra_experiment": experiment,
                }
            )
            inventory.append(
                {
                    "library_id": accession,
                    "condition": condition,
                    "source_uri": source_uri.replace("ftp://", "https://"),
                    "file_name": source_uri.rsplit("/", 1)[-1],
                    "file_type": "10x_filtered_feature_barcode_matrix",
                    "download_status": "not_downloaded",
                    "download_priority": "hold_no_case_control_contrast",
                }
            )

        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        sample_sheet_path = destination / "library-donor-condition.tsv"
        file_inventory_path = destination / "processed-file-inventory.tsv"
        audit_path = destination / "sample-audit.json"
        self._write(sample_sheet_path, rows)
        self._write(file_inventory_path, inventory)
        decision = "mechanistic_only_no_healthy_controls_and_pooled_donors"
        audit_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE232131",
                    "linked_accession": "E-MTAB-12805",
                    "decision": decision,
                    "automatic_download": False,
                    "libraries": len(rows),
                    "unique_named_donors": len(donors),
                    "donors": sorted(donors),
                    "diagnostic_groups": {
                        "ankylosing_spondylitis": len(donors),
                        "healthy_control": 0,
                    },
                    "library_structure": {
                        "single_donor_libraries": sum(
                            row["donor_count"] == 1 for row in rows
                        ),
                        "pooled_two_donor_libraries": sum(
                            row["donor_count"] == 2 for row in rows
                        ),
                        "conditions_per_biological_unit": 3,
                    },
                    "valid_uses": [
                        "within_donor_or_pool_stimulation_response",
                        "T_cell_monocyte_mechanism_generation",
                        "cell_type_localisation_of_targets",
                    ],
                    "invalid_uses": [
                        "AS_versus_healthy_validation",
                        "whole_blood_deconvolution_reference",
                        "separating_AS2311_from_AS1830",
                        "treating_cells_or_libraries_as_independent_donors",
                    ],
                    "next_action": (
                        "Do not download the large matrices for AXIS case-control "
                        "validation. Retain the file inventory for a future, "
                        "explicitly mechanistic stimulation analysis."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Gse232131SampleAuditRun(
            decision=decision,
            libraries=len(rows),
            donors=len(donors),
            sample_sheet_path=sample_sheet_path,
            file_inventory_path=file_inventory_path,
            audit_path=audit_path,
        )

    @staticmethod
    def _metadata(path: Path) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            for row in csv.reader(source, delimiter="\t"):
                if not row or not row[0].startswith("!Sample_"):
                    continue
                if row[0] == "!Sample_relation":
                    result.setdefault(row[0], []).extend(row[1:])
                else:
                    result.setdefault(row[0], row[1:])
        required = {
            "!Sample_geo_accession",
            "!Sample_title",
            "!Sample_relation",
            "!Sample_supplementary_file_1",
        }
        missing = required - result.keys()
        if missing:
            raise ValueError(
                "GSE232131 matrix is missing metadata: "
                + ", ".join(sorted(missing))
            )
        return result

    @staticmethod
    def _relation_ids(rows: list[str], relation: str) -> list[str]:
        prefix = f"{relation}:"
        matching = [
            row.rsplit("/", 1)[-1]
            for row in rows
            if row.lower().startswith(prefix)
        ]
        if not matching:
            raise ValueError(f"GSE232131 has no {relation} relations")
        return matching

    @classmethod
    def _condition(cls, title: str) -> str:
        for token, condition in cls.CONDITIONS.items():
            if f"_{token}_" in f"_{title}_":
                return condition
        raise ValueError(f"cannot identify condition in {title}")

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
