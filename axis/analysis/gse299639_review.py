"""Frozen eligibility and target review for the GSE299639 validation cohort."""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Gse299639ReviewRun:
    decision: str
    samples: int
    sample_sheet_path: Path
    target_validation_path: Path
    review_path: Path
    metadata_request_path: Path


class Gse299639Reviewer:
    """Resolve what GSE299639 can and cannot contribute to AXIS."""

    TARGETS = ("DDX24", "ADA")
    EXPECTED_SAMPLES = (
        "AS_F1",
        "AS_F2",
        "AS_F3",
        "AS_M1",
        "AS_M2",
        "AS_M3",
        "HC_F1",
        "HC_F2",
        "HC_F3",
        "HC_M1",
        "HC_M2",
        "HC_M3",
    )

    def review(
        self,
        *,
        abundance_path: str | Path,
        full_results_path: str | Path,
        sensitivity_results_path: str | Path,
        qc_path: str | Path,
        sensitivity_summary_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/external-validation/GSE299639"
        ),
    ) -> Gse299639ReviewRun:
        abundance = Path(abundance_path)
        observed = self._sample_columns(abundance)
        if observed != self.EXPECTED_SAMPLES:
            raise ValueError(
                "GSE299639 abundance columns do not match the frozen design"
            )
        full = self._indexed(Path(full_results_path))
        sensitivity = self._indexed(Path(sensitivity_results_path))
        qc = json.loads(Path(qc_path).read_text(encoding="utf-8"))
        sensitivity_summary = json.loads(
            Path(sensitivity_summary_path).read_text(encoding="utf-8")
        )
        samples = self._sample_rows()
        target_rows = [
            self._target_row(gene, full[gene], sensitivity[gene])
            for gene in self.TARGETS
        ]
        decision = "hold_missing_biologic_exposure_and_raw_counts"
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        sample_sheet_path = destination / "frozen-sample-sheet.tsv"
        target_validation_path = destination / "target-validation.tsv"
        review_path = destination / "eligibility-review.json"
        metadata_request_path = destination / "missing-metadata-request.md"
        self._write(sample_sheet_path, samples)
        self._write(target_validation_path, target_rows)
        review_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE299639",
                    "decision": decision,
                    "automatic_eligibility": False,
                    "allowed_role": (
                        "exploratory_external_directional_support_only"
                    ),
                    "participants": {
                        "cases": 6,
                        "controls": 6,
                        "independence": (
                            "12 unique named samples; no repeated measures "
                            "reported"
                        ),
                        "sex": "3 female and 3 male in each group",
                        "diagnosis": "modified_New_York_criteria",
                        "disease_activity": "BASDAI_at_least_4",
                        "HLA_B27": "6_of_6_cases_and_0_of_6_controls",
                    },
                    "assay": {
                        "technology": "Oxford_Nanopore_long_read_RNA_sequencing",
                        "tissue": "peripheral_whole_blood",
                        "local_input": "processed_gene_TPM",
                        "local_raw_counts": False,
                        "analysis": "Welch_on_log2_TPM_plus_1_exploratory",
                    },
                    "blocking_issues": [
                        (
                            "Biologic exposure was collected but individual "
                            "values are not reported."
                        ),
                        (
                            "Only processed TPM is locally available; an "
                            "integer-count model cannot be reproduced."
                        ),
                        (
                            "AS_M1 is a candidate PCA outlier and the number of "
                            "FDR hits is threshold-sensitive."
                        ),
                        (
                            "The publication itself reanalysed GSE25101 and "
                            "GSE73754, creating analytical but not participant "
                            "overlap with AXIS discovery."
                        ),
                        "The cohort contains only 6 cases and 6 controls.",
                    ],
                    "quality_control": {
                        "candidate_outliers": qc.get("outlier_samples", []),
                        "minimum_sample_correlation": qc.get(
                            "minimum_sample_correlation"
                        ),
                        "sensitivity_decision": sensitivity_summary.get(
                            "decision"
                        ),
                    },
                    "target_results": target_rows,
                    "advance_rule": (
                        "Obtain sample-level treatment exposure and raw counts "
                        "or a documented count matrix; then freeze covariates "
                        "before reanalysis."
                    ),
                    "sources": [
                        (
                            "https://www.frontiersin.org/journals/immunology/"
                            "articles/10.3389/fimmu.2026.1640271/full"
                        ),
                        (
                            "https://www.ncbi.nlm.nih.gov/geo/query/"
                            "acc.cgi?acc=GSE299639"
                        ),
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
        return Gse299639ReviewRun(
            decision=decision,
            samples=len(samples),
            sample_sheet_path=sample_sheet_path,
            target_validation_path=target_validation_path,
            review_path=review_path,
            metadata_request_path=metadata_request_path,
        )

    @classmethod
    def _sample_rows(cls) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for sample in cls.EXPECTED_SAMPLES:
            case = sample.startswith("AS_")
            rows.append(
                {
                    "sample_id": sample,
                    "participant_id": sample,
                    "group": "case" if case else "control",
                    "sex": "female" if "_F" in sample else "male",
                    "tissue": "peripheral_whole_blood",
                    "biologic_exposure": "unknown" if case else "not_applicable",
                    "inclusion_status": (
                        "hold_treatment_metadata" if case else "include_if_cases_clear"
                    ),
                    "outlier_status": (
                        "candidate_retain_for_sensitivity"
                        if sample == "AS_M1"
                        else "not_flagged_initial_QC"
                    ),
                    "automatic_eligibility": False,
                }
            )
        return rows

    @staticmethod
    def _target_row(
        gene: str,
        full: dict[str, str],
        sensitivity: dict[str, str],
    ) -> dict[str, object]:
        full_direction = full["direction"]
        sensitivity_direction = sensitivity["direction"]
        return {
            "gene_symbol": gene,
            "full_effect": full["median_mean_difference"],
            "full_p_value": full["simes_p_value"],
            "full_adjusted_p_value": full["adjusted_p_value"],
            "full_direction": full_direction,
            "without_AS_M1_effect": sensitivity["median_mean_difference"],
            "without_AS_M1_p_value": sensitivity["simes_p_value"],
            "without_AS_M1_adjusted_p_value": sensitivity["adjusted_p_value"],
            "without_AS_M1_direction": sensitivity_direction,
            "direction_stable": full_direction == sensitivity_direction,
            "validation_status": (
                "exploratory_directional_support_not_significant"
                if full_direction == sensitivity_direction
                else "outlier_sensitive_direction"
            ),
        }

    @staticmethod
    def _sample_columns(path: Path) -> tuple[str, ...]:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            header = next(csv.reader(source, delimiter="\t"))
        return tuple(header[1 : header.index("Symbol")])

    @staticmethod
    def _indexed(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"]: row
                for row in csv.DictReader(source, delimiter="\t")
                if row["gene_symbol"] in Gse299639Reviewer.TARGETS
            }

    @staticmethod
    def _metadata_request() -> str:
        return "\n".join(
            [
                "# GSE299639 missing-data request",
                "",
                (
                    "To determine whether GSE299639 can serve as an independent "
                    "axSpA validation cohort, request the following from the "
                    "study authors or repository:"
                ),
                "",
                "1. Biologic exposure for each AS_F1-AS_M3 sample.",
                "2. Conventional DMARD, NSAID and corticosteroid exposure.",
                "3. Confirmation that all 12 sample labels are unique participants.",
                "4. Individual age, BASDAI, CRP, HLA-B27 and processing batch.",
                "5. Gene-level integer counts used by DESeq2.",
                "6. Stable links or accessions for raw POD5/FASTQ data.",
                "7. Confirmation of whether sampling preceded treatment changes.",
                "",
                (
                    "Do not promote the cohort beyond exploratory directional "
                    "support until items 1, 3 and 5 are resolved."
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
