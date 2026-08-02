"""Focused mechanistic dossier for a convergent transcriptomic candidate."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class FocusedTargetDossierRun:
    gene: str
    decision: str
    evidence_path: Path
    experiment_path: Path
    dossier_path: Path


class FocusedTargetDossierBuilder:
    """Convert convergent association into a falsifiable experiment."""

    def build(
        self,
        gene: str,
        *,
        bulk_path: str | Path,
        single_cell_path: str | Path,
        published_path: str | Path,
        intelligence_path: str | Path,
        genetics_path: str | Path,
        dossier_directory: str | Path,
        output_root: str | Path,
    ) -> FocusedTargetDossierRun:
        symbol = gene.strip().upper()
        bulk = self._one(Path(bulk_path), symbol)
        single = self._all(Path(single_cell_path), symbol)
        published = self._one(Path(published_path), symbol)
        intelligence = self._one(Path(intelligence_path), symbol)
        genetics = self._one(Path(genetics_path), symbol)
        target_payload = json.loads(
            (Path(dossier_directory) / f"{symbol}.json").read_text(encoding="utf-8")
        )
        target = target_payload.get("target", {})
        prioritisation = {
            str(row.get("key")): str(row.get("value"))
            for row in target.get("prioritisation", {}).get("items", [])
        }
        tractability = target.get("tractability", [])
        high_quality_pocket = any(
            row.get("label") == "High-Quality Pocket" and row.get("value") is True
            for row in tractability
        )
        genetic_count = int(genetics.get("genetic_evidence_count") or 0)
        published_support = (
            published.get("validation_status") == "published_directional_support"
        )
        concordant_bulk = bulk.get("direction_concordant", "").lower() == "true"
        significant_single = [
            row for row in single if float(row.get("adjusted_p_value") or 1.0) <= 0.05
        ]
        if published_support and concordant_bulk and significant_single:
            decision = "mechanistic_perturbation_candidate"
        else:
            decision = "observational_biomarker_only"
        therapeutic = (
            "not_ready_no_causal_direction"
            if genetic_count == 0
            else "causal_review_required"
        )
        structural = (
            "defer_alphafold_intracellular_rbp_without_validated_pocket"
            if not high_quality_pocket
            else "review_structure_after_perturbation"
        )
        evidence = self._evidence_rows(
            symbol,
            bulk,
            single,
            published,
            intelligence,
            genetics,
        )
        experiment = self._experiment_rows(symbol)
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        evidence_path = destination / f"{symbol.lower()}-evidence.tsv"
        experiment_path = destination / f"{symbol.lower()}-experiment.tsv"
        dossier_path = destination / f"{symbol.lower()}-dossier.json"
        self._write(evidence_path, evidence)
        self._write(experiment_path, experiment)
        dossier_path.write_text(
            json.dumps(
                {
                    "analysis_role": "focused_mechanistic_target_dossier",
                    "created_at": datetime.now(UTC).isoformat(),
                    "gene_symbol": symbol,
                    "decision": decision,
                    "therapeutic_status": therapeutic,
                    "structural_status": structural,
                    "causal_evidence": {
                        "disease_genetic_records": genetic_count,
                        "therapeutic_direction": genetics.get(
                            "therapeutic_direction", "unknown"
                        ),
                        "interpretation": (
                            "Expression convergence does not establish whether "
                            "raising or lowering EWSR1 would improve disease."
                        ),
                    },
                    "expression_convergence": {
                        "bulk_studies": int(bulk.get("available_studies") or 0),
                        "bulk_direction": bulk.get("direction", ""),
                        "bulk_adjusted_p_value": float(
                            bulk.get("combined_adjusted_p_value") or 1.0
                        ),
                        "significant_single_cell_types": [
                            row["cell_type"] for row in significant_single
                        ],
                        "published_validation": published.get("validation_status", ""),
                        "published_cell_subtype": published.get(
                            "best_published_cell_subtype", ""
                        ),
                    },
                    "target_risk": {
                        "intracellular": prioritisation.get("isInMembrane") == "0",
                        "secreted": prioritisation.get("isSecreted") == "1",
                        "high_quality_pocket": high_quality_pocket,
                        "reported_safety_liabilities": int(
                            intelligence.get("safety_liabilities") or 0
                        ),
                        "clinical_candidates": int(
                            intelligence.get("clinical_candidates") or 0
                        ),
                        "warning": (
                            "No reported liability is not evidence of safety. "
                            "EWSR1 has broad RNA-processing and haematopoietic roles."
                        ),
                    },
                    "falsification_rule": (
                        "Deprioritise if partial EWSR1 modulation fails to change "
                        "the disease-associated programme, produces the same "
                        "response in cases and controls, or causes substantial "
                        "loss of viability/lineage identity."
                    ),
                    "literature_sources": [
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC6527469/",
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC9371696/",
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC10130905/",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return FocusedTargetDossierRun(
            gene=symbol,
            decision=decision,
            evidence_path=evidence_path,
            experiment_path=experiment_path,
            dossier_path=dossier_path,
        )

    @staticmethod
    def _evidence_rows(
        gene: str,
        bulk: dict[str, str],
        single: list[dict[str, str]],
        published: dict[str, str],
        intelligence: dict[str, str],
        genetics: dict[str, str],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = [
            {
                "gene_symbol": gene,
                "evidence_layer": "bulk_three_study_concordance",
                "context": "whole_blood",
                "direction": bulk.get("direction", ""),
                "effect": bulk.get("study_effects", ""),
                "adjusted_p_value": bulk.get("combined_adjusted_p_value", ""),
                "interpretation": "convergent_observational_expression",
            }
        ]
        rows.extend(
            {
                "gene_symbol": gene,
                "evidence_layer": "subject_level_single_cell",
                "context": row["cell_type"],
                "direction": row["direction"],
                "effect": row["log2_cpm_difference"],
                "adjusted_p_value": row["adjusted_p_value"],
                "interpretation": "cell_type_specific_observational_expression",
            }
            for row in single
        )
        rows.extend(
            (
                {
                    "gene_symbol": gene,
                    "evidence_layer": "published_independent_table",
                    "context": published.get("best_published_cell_subtype", ""),
                    "direction": published.get("best_published_direction", ""),
                    "effect": "",
                    "adjusted_p_value": published.get(
                        "best_published_adjusted_p_value", ""
                    ),
                    "interpretation": published.get("validation_status", ""),
                },
                {
                    "gene_symbol": gene,
                    "evidence_layer": "human_genetics",
                    "context": "ankylosing_spondylitis",
                    "direction": genetics.get("therapeutic_direction", "unknown"),
                    "effect": genetics.get("maximum_evidence_score", "0"),
                    "adjusted_p_value": "",
                    "interpretation": (
                        "no_disease_specific_genetic_support"
                        if int(genetics.get("genetic_evidence_count") or 0) == 0
                        else "genetic_support"
                    ),
                },
                {
                    "gene_symbol": gene,
                    "evidence_layer": "target_intelligence",
                    "context": intelligence.get("tractability_modalities", ""),
                    "direction": "unknown",
                    "effect": intelligence.get("clinical_candidates", "0"),
                    "adjusted_p_value": "",
                    "interpretation": "tractability_is_not_causality",
                },
            )
        )
        return rows

    @staticmethod
    def _experiment_rows(gene: str) -> list[dict[str, object]]:
        common = {
            "gene_symbol": gene,
            "biological_replicate": "independent_human_donor",
            "minimum_donors_per_group": 6,
        }
        return [
            {
                **common,
                "stage": 1,
                "cell_type": "primary_CD14_monocytes",
                "perturbation": "CRISPRi_titrated_partial_reduction",
                "comparators": "non_targeting|two_independent_guides|rescue",
                "primary_endpoint": (
                    "predeclared_AS_expression_module_and_cytokine_response"
                ),
                "safety_endpoint": "viability|apoptosis|lineage_markers",
                "advance_rule": (
                    "reproducible disease-selective molecular rescue without "
                    "more than 20_percent viability loss"
                ),
            },
            {
                **common,
                "stage": 2,
                "cell_type": "primary_CD4_TCM",
                "perturbation": "CRISPRi_and_CRISPRa_bidirectional_titration",
                "comparators": "non_targeting|two_guides_each_direction|rescue",
                "primary_endpoint": (
                    "TCR_activation|IL2_STAT5_response|RNA_processing_signature"
                ),
                "safety_endpoint": "viability|proliferation|lineage_identity",
                "advance_rule": (
                    "directional dose-response replicated across donors and "
                    "consistent with monocyte findings"
                ),
            },
            {
                **common,
                "stage": 3,
                "cell_type": "cross_lineage",
                "perturbation": "mechanism_and_off_target_validation",
                "comparators": "unedited|non_targeting|rescue",
                "primary_endpoint": "RNA_seq|splicing|proteomics|target_engagement",
                "safety_endpoint": "global_transcription|DNA_damage|cell_fitness",
                "advance_rule": (
                    "specific mechanism with acceptable therapeutic window"
                ),
            },
        ]

    @staticmethod
    def _all(path: Path, gene: str) -> list[dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return [
                    row
                    for row in csv.DictReader(source, delimiter="\t")
                    if row["gene_symbol"].strip().upper() == gene
                ]
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read evidence table {path}: {error}") from error

    @staticmethod
    def _one(path: Path, gene: str) -> dict[str, str]:
        rows = FocusedTargetDossierBuilder._all(path, gene)
        return rows[0] if rows else {}

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
