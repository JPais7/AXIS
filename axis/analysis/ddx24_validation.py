"""Predeclared, donor-aware validation plan for the DDX24 hypothesis."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Ddx24ValidationRun:
    donors: int
    experimental_units: int
    sample_sheet_path: Path
    endpoints_path: Path
    protocol_path: Path


class Ddx24ValidationPlanner:
    """Turn the DDX24 deep-dive decision into an auditable experiment."""

    CONDITIONS = (
        ("mock", "0"),
        ("non_targeting_control", "0"),
        ("DDX24_partial_restoration", "25"),
        ("DDX24_partial_restoration", "50"),
        ("DDX24_partial_restoration", "75"),
    )

    def build(
        self,
        *,
        decisions_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/gene-evidence/deep-dive/ddx24-validation"
        ),
        donors_per_group: int = 6,
        technical_replicates: int = 2,
    ) -> Ddx24ValidationRun:
        if donors_per_group < 6:
            raise ValueError("DDX24 validation requires at least 6 donors per group")
        if technical_replicates < 1:
            raise ValueError("technical_replicates must be at least 1")
        decision = self._ddx24_decision(Path(decisions_path))
        allowed = {
            "experimental_only_not_drug_ready",
            "deprioritise_pending_reference_deconvolution",
        }
        if decision.get("decision") not in allowed:
            raise ValueError("DDX24 is not currently approved for experimental testing")

        sample_rows = self._samples(donors_per_group, technical_replicates)
        endpoints = self._endpoints()
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        sample_sheet_path = destination / "ddx24-sample-sheet.tsv"
        endpoints_path = destination / "ddx24-endpoints.tsv"
        protocol_path = destination / "ddx24-preregistered-plan.json"
        self._write(sample_sheet_path, sample_rows)
        self._write(endpoints_path, endpoints)
        protocol_path.write_text(
            json.dumps(
                self._protocol(
                    decision=decision,
                    donors_per_group=donors_per_group,
                    technical_replicates=technical_replicates,
                    experimental_units=len(sample_rows),
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Ddx24ValidationRun(
            donors=donors_per_group * 2,
            experimental_units=len(sample_rows),
            sample_sheet_path=sample_sheet_path,
            endpoints_path=endpoints_path,
            protocol_path=protocol_path,
        )

    @classmethod
    def _samples(
        cls, donors_per_group: int, technical_replicates: int
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        unit = 0
        for group in ("axSpA", "control"):
            prefix = "AS" if group == "axSpA" else "HC"
            for donor_number in range(1, donors_per_group + 1):
                donor = f"{prefix}{donor_number:02d}"
                for condition, target_restoration in cls.CONDITIONS:
                    for replicate in range(1, technical_replicates + 1):
                        unit += 1
                        rows.append(
                            {
                                "experimental_unit_id": f"DDX24-{unit:03d}",
                                "donor_id": donor,
                                "disease_group": group,
                                "cell_type": "primary_CD14_monocyte",
                                "condition": condition,
                                "target_DDX24_restoration_percent": (
                                    target_restoration
                                ),
                                "technical_replicate": replicate,
                                "randomisation_block": donor,
                                "blinding_label": f"U{unit:03d}",
                            }
                        )
        return rows

    @staticmethod
    def _endpoints() -> list[dict[str, object]]:
        return [
            {
                "endpoint": "DDX24_target_engagement",
                "role": "manipulation_check",
                "measurement": "DDX24_mRNA_and_protein",
                "analysis": "paired_donor_dose_response",
                "success_rule": "ordered_25_50_75_percent_restoration_window",
            },
            {
                "endpoint": "RIG_I_IRF7_type_I_IFN_module",
                "role": "primary",
                "measurement": "predeclared_targeted_panel_or_RNA_seq",
                "analysis": "mixed_model_with_donor_random_intercept",
                "success_rule": (
                    "dose_response_toward_control_and_FDR_below_0.05"
                ),
            },
            {
                "endpoint": "AXIS_disease_signature",
                "role": "primary",
                "measurement": "frozen_gene_set_score",
                "analysis": "mixed_model_with_donor_random_intercept",
                "success_rule": (
                    "case_selective_normalisation_with_interaction_FDR_below_0.05"
                ),
            },
            {
                "endpoint": "cell_fitness",
                "role": "safety",
                "measurement": "viability_apoptosis_cell_count",
                "analysis": "paired_change_from_non_targeting",
                "success_rule": "less_than_20_percent_fitness_loss",
            },
            {
                "endpoint": "RNA_processing_integrity",
                "role": "safety",
                "measurement": "global_splicing_and_ribosome_biogenesis_modules",
                "analysis": "mixed_model_and_effect_size",
                "success_rule": "no_broad_dose_dependent_disruption",
            },
        ]

    @staticmethod
    def _protocol(
        *,
        decision: dict[str, str],
        donors_per_group: int,
        technical_replicates: int,
        experimental_units: int,
    ) -> dict[str, object]:
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "analysis_role": "DDX24_stage_1_functional_falsification",
            "status": (
                "suspended_pending_reference_deconvolution"
                if decision.get("decision")
                == "deprioritise_pending_reference_deconvolution"
                else "planned_not_executed"
            ),
            "hypothesis": (
                "Partial restoration of DDX24 in axSpA CD14 monocytes "
                "normalises the disease-associated RIG-I/IRF7/type-I-IFN "
                "programme without materially reducing cell fitness."
            ),
            "source_decision": decision,
            "design": {
                "disease_groups": ["axSpA", "matched_control"],
                "donors_per_group": donors_per_group,
                "independent_biological_replicates": donors_per_group * 2,
                "technical_replicates": technical_replicates,
                "experimental_units": experimental_units,
                "conditions": [
                    {
                        "name": condition,
                        "target_restoration_percent": target,
                    }
                    for condition, target in Ddx24ValidationPlanner.CONDITIONS
                ],
                "pairing": "all conditions measured within each donor",
                "randomisation": "randomise conditions within donor block",
                "blinding": "analyse using blinding_label until QC is frozen",
            },
            "eligibility": {
                "case_definition": "clinician_confirmed_axSpA",
                "matching_variables": ["age_band", "sex"],
                "record_as_covariates": [
                    "age",
                    "sex",
                    "HLA_B27",
                    "disease_activity",
                    "current_medication",
                    "processing_batch",
                ],
                "exclude": [
                    "active_infection",
                    "sample_viability_below_80_percent",
                    "missing_donor_level_metadata",
                ],
            },
            "analysis": {
                "experimental_unit": "human_donor",
                "technical_replicates": (
                    "aggregate_before_inference_and_never_count_as_donors"
                ),
                "primary_model": (
                    "endpoint ~ disease_group * restoration_dose + covariates "
                    "+ (1|donor_id)"
                ),
                "multiplicity": "Benjamini_Hochberg_within_endpoint_family",
                "missing_data": "no_single_value_imputation",
                "outliers": "retain_unless_predeclared_QC_failure",
            },
            "decision": {
                "advance": [
                    "target engagement reaches at least two restoration windows",
                    "both primary endpoints move dose-dependently toward controls",
                    "disease-by-dose interaction FDR is below 0.05",
                    "median fitness loss remains below 20 percent",
                    "effect is reproduced in at least 4 of 6 axSpA donors",
                ],
                "stop": [
                    "DDX24 restoration fails target engagement",
                    "primary disease programme does not normalise",
                    "response is equally strong or adverse in controls",
                    "fitness loss reaches 20 percent or more",
                    "broad RNA-processing disruption increases with dose",
                ],
            },
            "limitations": [
                "This plan does not establish clinical efficacy.",
                "The initial sample size is a falsification screen, not a trial.",
                "Exact delivery conditions require a laboratory optimisation pilot.",
                (
                    "A successful result requires independent lineage and "
                    "cohort replication."
                ),
            ],
        }

    @staticmethod
    def _ddx24_decision(path: Path) -> dict[str, str]:
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                if row.get("gene_symbol", "").strip().upper() == "DDX24":
                    return row
        raise ValueError(f"DDX24 decision is missing from {path}")

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
