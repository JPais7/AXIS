"""Final confounding audit and frozen confirmation/refutation gates."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ConfoundingFreezeRun:
    checks: int
    criteria: int
    audit_path: Path
    criteria_path: Path
    freeze_path: Path
    decision_path: Path


class ConfoundingFreezeBuilder:
    """Convert available evidence and missing covariates into explicit gates."""

    def build(
        self,
        *,
        covariates_path: str | Path,
        batch_adjusted_path: str | Path,
        leave_one_out_path: str | Path,
        hierarchical_path: str | Path,
        context_path: str | Path,
        gse288581_sensitivity_path: str | Path,
        output_root: str | Path = Path("data/analysis/ddx24-evidence-freeze"),
    ) -> ConfoundingFreezeRun:
        inputs = tuple(
            Path(path)
            for path in (
                covariates_path,
                batch_adjusted_path,
                leave_one_out_path,
                hierarchical_path,
                context_path,
                gse288581_sensitivity_path,
            )
        )
        covariates = {row["covariate"]: row for row in self._read(inputs[0])}
        batch = [
            row
            for row in self._read(inputs[1])
            if row["gene_symbol"] == "DDX24"
            and row["cell_type"] in {"CD8 TEM", "CD8 Naive"}
        ]
        stability = [
            row
            for row in self._read(inputs[2])
            if row["gene_symbol"] == "DDX24"
            and row["cell_type"] in {"CD8 TEM", "CD8 Naive"}
        ]
        hierarchical = next(
            row
            for row in self._read(inputs[3])
            if row["gene_symbol"] == "DDX24"
        )
        contexts = [
            row
            for row in self._read(inputs[4])
            if row["gene_symbol"] == "DDX24"
        ]
        external_stability = [
            row
            for row in self._read(inputs[5])
            if row["gene_symbol"] == "DDX24"
        ]
        audit = self._audit(
            covariates,
            batch,
            stability,
            hierarchical,
            contexts,
            external_stability,
        )
        criteria = self._criteria()
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        audit_path = destination / "confounding-audit.tsv"
        criteria_path = destination / "confirmation-refutation-criteria.tsv"
        freeze_path = destination / "evidence-freeze.json"
        decision_path = destination / "decision-summary.json"
        self._write(audit_path, audit)
        self._write(criteria_path, criteria)
        freeze = {
            "frozen_at": datetime.now(UTC).isoformat(),
            "version": "DDX24_evidence_freeze_v1",
            "primary_hypothesis": (
                "DDX24 RNA expression is lower within human peripheral-blood "
                "CD8 T-cell populations in ankylosing spondylitis."
            ),
            "primary_direction": "lower_in_case",
            "primary_cell_context": "memory_or_effector_CD8_T_cells",
            "primary_unit": "human_participant",
            "inputs": [
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in inputs
            ],
            "rules_frozen_before_next_dataset": True,
        }
        freeze_path.write_text(
            json.dumps(freeze, indent=2) + "\n", encoding="utf-8"
        )
        unresolved = [
            row["check"] for row in audit if row["status"] == "unresolved"
        ]
        decision_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "target": "DDX24",
                    "computational_status": (
                        "strengthened_within_CD8_association"
                    ),
                    "laboratory_status": "eligible_for_falsification_pilot",
                    "therapeutic_status": "not_validated",
                    "passed_checks": sum(
                        row["status"] == "passed" for row in audit
                    ),
                    "caution_checks": sum(
                        row["status"] == "caution" for row in audit
                    ),
                    "unresolved_checks": unresolved,
                    "interpretation": (
                        "Batch, cell-state and participant-influence checks "
                        "support a within-CD8 association. Age, sex, medication "
                        "and activity remain unavailable and prevent a causal "
                        "or therapeutic claim."
                    ),
                    "next_decision": (
                        "Freeze computational discovery and use the listed "
                        "criteria for an independent cohort or RT-qPCR pilot."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ConfoundingFreezeRun(
            checks=len(audit),
            criteria=len(criteria),
            audit_path=audit_path,
            criteria_path=criteria_path,
            freeze_path=freeze_path,
            decision_path=decision_path,
        )

    @staticmethod
    def _audit(
        covariates: dict[str, dict[str, str]],
        batch: list[dict[str, str]],
        stability: list[dict[str, str]],
        hierarchical: dict[str, str],
        contexts: list[dict[str, str]],
        external_stability: list[dict[str, str]],
    ) -> list[dict[str, object]]:
        cd8_context = next(
            row for row in contexts if row["context"] == "CD8_single_cell"
        )
        microarray = next(
            row
            for row in contexts
            if row["context"] == "peripheral_blood_microarray"
        )
        sequencing = next(
            row
            for row in contexts
            if row["context"] == "whole_blood_RNA_sequencing"
        )
        rows: list[dict[str, object]] = [
            {
                "check": "diagnosis_exposure",
                "status": "passed",
                "evidence": covariates["diagnosis"]["action"],
                "implication": "case-control exposure explicitly modelled",
            },
            {
                "check": "processing_batch",
                "status": (
                    "passed"
                    if len(batch) == 2
                    and all(
                        float(row["adjusted_log2_cpm_difference"]) < 0
                        for row in batch
                    )
                    else "caution"
                ),
                "evidence": "batch-PC adjusted CD8 TEM and CD8 Naive",
                "implication": "CD8 direction survives available batch adjustment",
            },
            {
                "check": "cell_state_specificity",
                "status": (
                    "passed"
                    if cd8_context["context_direction"] == "lower_in_case"
                    else "caution"
                ),
                "evidence": "2 independent CD8 cohorts",
                "implication": "within-cell signal is not solely bulk composition",
            },
            {
                "check": "participant_influence_GSE194315",
                "status": (
                    "passed"
                    if all(
                        float(row["direction_stability_fraction"]) == 1.0
                        for row in stability
                    )
                    else "caution"
                ),
                "evidence": "leave-one-participant-out in two CD8 states",
                "implication": "no single participant reverses direction",
            },
            {
                "check": "participant_influence_GSE288581",
                "status": (
                    "passed"
                    if external_stability
                    and all(
                        row["direction_preserved"] == "True"
                        for row in external_stability
                    )
                    else "caution"
                ),
                "evidence": "8 of 8 donor omissions preserve direction",
                "implication": "external CD8 result is directionally stable",
            },
            {
                "check": "cross_cohort_direction",
                "status": (
                    "passed"
                    if int(hierarchical["lower_in_case_cohorts"]) >= 6
                    else "caution"
                ),
                "evidence": (
                    f"{hierarchical['lower_in_case_cohorts']} of "
                    f"{hierarchical['independent_cohorts']} cohorts lower"
                ),
                "implication": "direction recurs across independent cohorts",
            },
            {
                "check": "microarray_heterogeneity",
                "status": "caution",
                "evidence": (
                    f"{microarray['lower_in_case_cohorts']}/"
                    f"{microarray['cohorts']} lower but random-effects p="
                    f"{microarray['pooled_p_value']}"
                ),
                "implication": "bulk magnitude is heterogeneous",
            },
            {
                "check": "whole_blood_RNAseq",
                "status": "caution",
                "evidence": sequencing["context_direction"],
                "implication": "sequencing cohorts disagree directionally",
            },
        ]
        for covariate in ("age", "sex", "medication", "disease_activity"):
            available = covariates[covariate]["availability"] == "available"
            rows.append(
                {
                    "check": covariate,
                    "status": "passed" if available else "unresolved",
                    "evidence": covariates[covariate]["availability"],
                    "implication": covariates[covariate]["action"],
                }
            )
        return rows

    @staticmethod
    def _criteria() -> list[dict[str, object]]:
        return [
            {
                "stage": "independent_computational_replication",
                "criterion": "participant_unit",
                "confirmation": "donor-resolved labels; at least 3 per group",
                "refutation_or_stop": "pooled groups or cell-level inference",
                "locked": True,
            },
            {
                "stage": "independent_computational_replication",
                "criterion": "primary_direction",
                "confirmation": "DDX24 case-minus-control effect below zero in CD8",
                "refutation_or_stop": "effect at or above zero",
                "locked": True,
            },
            {
                "stage": "independent_computational_replication",
                "criterion": "uncertainty",
                "confirmation": "95% CI below zero or meta-analytic CI below zero",
                "refutation_or_stop": (
                    "adequately powered CI excludes meaningful reduction"
                ),
                "locked": True,
            },
            {
                "stage": "confounding",
                "criterion": "minimum_adjustment",
                "confirmation": (
                    "direction retained after available batch and covariates"
                ),
                "refutation_or_stop": (
                    "direction reverses after prespecified adjustment"
                ),
                "locked": True,
            },
            {
                "stage": "RT_qPCR_pilot",
                "criterion": "target_expression",
                "confirmation": (
                    "lower DDX24 in isolated CD8 cells in at least 4/6 cases"
                ),
                "refutation_or_stop": "no reduction or opposite direction",
                "locked": True,
            },
            {
                "stage": "functional_pilot",
                "criterion": "restoration_response",
                "confirmation": (
                    "dose-dependent normalization of both primary endpoints"
                ),
                "refutation_or_stop": (
                    "no normalization or equal/adverse control response"
                ),
                "locked": True,
            },
            {
                "stage": "functional_pilot",
                "criterion": "cell_fitness",
                "confirmation": "median fitness loss below 20%",
                "refutation_or_stop": "fitness loss at least 20%",
                "locked": True,
            },
            {
                "stage": "therapeutic_claim",
                "criterion": "causality",
                "confirmation": "independent functional rescue and lineage replication",
                "refutation_or_stop": "expression association alone",
                "locked": True,
            },
        ]

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

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
