"""Decision-focused therapeutic deep dives for DDX24 and ADA."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class TargetDeepDiveRun:
    targets: int
    promoted: int
    experimental_only: int
    deprioritised: int
    decision_path: Path
    experiment_path: Path
    summary_path: Path


class TargetDeepDiveBuilder:
    """Resolve whether convergent expression supports a drug programme."""

    LITERATURE = {
        "DDX24": (
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC3814876/",
            "https://journals.asm.org/doi/10.1128/jvi.00040-24",
        ),
        "ADA": (
            "https://pubmed.ncbi.nlm.nih.gov/40572058/",
            "https://www.accessdata.fda.gov/drugsatfda_docs/label/"
            "2025/020122s021lbl.pdf",
        ),
    }

    def build(
        self,
        *,
        master_path: str | Path,
        three_study_path: str | Path,
        external_validation_path: str | Path,
        single_cell_path: str | Path,
        karow_path: str | Path,
        genetics_path: str | Path,
        intelligence_path: str | Path,
        dossier_directory: str | Path,
        meta_analysis_path: str | Path | None = None,
        composition_path: str | Path | None = None,
        reference_expansion_path: str | Path | None = None,
        output_root: str | Path = Path(
            "data/analysis/gene-evidence/deep-dive/decisions"
        ),
    ) -> TargetDeepDiveRun:
        master = self._indexed(Path(master_path))
        three_study = self._indexed(Path(three_study_path))
        external = self._indexed(Path(external_validation_path))
        single = self._indexed(Path(single_cell_path))
        karow = self._indexed(Path(karow_path))
        genetics = self._indexed(Path(genetics_path))
        intelligence = self._indexed(Path(intelligence_path))
        decisions = [
            self._decision(
                gene,
                master.get(gene, {}),
                three_study.get(gene, {}),
                external.get(gene, {}),
                single.get(gene, {}),
                karow.get(gene, {}),
                genetics.get(gene, {}),
                intelligence.get(gene, {}),
                self._dossier(Path(dossier_directory), gene),
            )
            for gene in ("DDX24", "ADA")
        ]
        if meta_analysis_path is not None and composition_path is not None:
            meta = self._indexed(Path(meta_analysis_path))
            composition = self._all_rows(Path(composition_path))
            decisions = [
                self._apply_robustness(
                    row,
                    meta.get(str(row["gene_symbol"]), {}),
                    [
                        value
                        for value in composition
                        if value.get("gene_symbol") == row["gene_symbol"]
                    ],
                )
                for row in decisions
            ]
        if reference_expansion_path is not None:
            reference = self._all_rows(Path(reference_expansion_path))
            decisions = [
                self._apply_single_cell_reference(row, reference)
                for row in decisions
            ]
        experiments = [self._experiment(row) for row in decisions]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        decision_path = destination / "target-decisions.tsv"
        experiment_path = destination / "falsification-experiments.tsv"
        self._write(decision_path, decisions)
        self._write(experiment_path, experiments)
        summary_path = destination / "deep-dive.json"
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "therapeutic_target_deep_dive",
                    "targets": decisions,
                    "guardrails": [
                        "Disease expression direction is not therapeutic direction.",
                        "An approved drug for another disease is not axSpA efficacy.",
                        "No target is promoted without causal human evidence.",
                        "Experiments include a predeclared stop rule.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return TargetDeepDiveRun(
            targets=2,
            promoted=sum(
                row["decision"] == "promote_to_drug_program" for row in decisions
            ),
            experimental_only=sum(
                row["decision"] == "experimental_only_not_drug_ready"
                for row in decisions
            ),
            deprioritised=sum(
                str(row["decision"]).startswith("deprioritise")
                for row in decisions
            ),
            decision_path=decision_path,
            experiment_path=experiment_path,
            summary_path=summary_path,
        )

    def _decision(
        self,
        gene: str,
        master: dict[str, str],
        three: dict[str, str],
        external: dict[str, str],
        single: dict[str, str],
        karow: dict[str, str],
        genetics: dict[str, str],
        intelligence: dict[str, str],
        dossier: dict[str, Any],
    ) -> dict[str, object]:
        drugs = self._drugs(dossier)
        if gene == "DDX24":
            decision = "experimental_only_not_drug_ready"
            therapeutic = (
                "unresolved; test partial restoration before considering modulation"
            )
            mechanism = (
                "DDX24 is reported as a negative regulator of RIG-I-like "
                "receptor/IRF7 signalling; further reduction could increase "
                "innate interferon signalling."
            )
            risk = (
                "Intracellular RNA helicase with no clinical candidate, ligand, "
                "or validated pocket; broad RNA biology creates on-target risk."
            )
            stop = (
                "Stop if partial DDX24 restoration does not normalize the "
                "case-associated IFN/RLR programme or impairs cell fitness."
            )
        else:
            decision = "deprioritise_systemic_ada_inhibition"
            therapeutic = (
                "do not infer inhibition; measure ADA activity and adenosine first"
            )
            mechanism = (
                "ADA removes immunosuppressive adenosine, but severe ADA loss "
                "causes immune deficiency. Lower disease expression does not "
                "establish whether activity is low or causal."
            )
            risk = (
                "Pentostatin inhibits ADA but is an oncology immunosuppressant "
                "with serious renal, hepatic, pulmonary, CNS and infection risk."
            )
            stop = (
                "Stop direct targeting if ADA activity is not altered in fresh "
                "axSpA samples or if inhibition amplifies immune dysfunction."
            )
        return {
            "gene_symbol": gene,
            "decision": decision,
            "current_master_score": master.get("total_score", ""),
            "three_study_direction": three.get("direction", ""),
            "three_study_directions_concordant": three.get(
                "direction_concordant", ""
            ),
            "three_study_adjusted_p_value": three.get(
                "combined_adjusted_p_value", ""
            ),
            "external_validation_status": external.get("validation_status", ""),
            "external_validation_direction": external.get(
                "validation_direction", ""
            ),
            "single_cell_adjusted_p_value": single.get(
                "best_single_cell_adjusted_p_value", ""
            ),
            "single_cell_direction": single.get(
                "best_single_cell_direction", ""
            ),
            "karow_status": karow.get("status", ""),
            "human_genetic_records": genetics.get(
                "genetic_evidence_count", "0"
            ),
            "genetic_therapeutic_direction": genetics.get(
                "therapeutic_direction", "unknown"
            ),
            "tractability_modalities": intelligence.get(
                "tractability_modalities", ""
            ),
            "clinical_candidates": intelligence.get("clinical_candidates", "0"),
            "known_drugs": "|".join(drugs),
            "mechanistic_interpretation": mechanism,
            "therapeutic_direction": therapeutic,
            "principal_risk": risk,
            "stop_rule": stop,
            "literature_sources": "|".join(self.LITERATURE[gene]),
        }

    @staticmethod
    def _experiment(decision: dict[str, object]) -> dict[str, object]:
        gene = str(decision["gene_symbol"])
        if gene == "DDX24":
            return {
                "gene_symbol": gene,
                "priority": 1,
                "material": "primary_CD14_monocytes_and_CD8_TEM",
                "groups": "at_least_6_axSpA_and_6_matched_controls",
                "perturbation": (
                    "CRISPRa_or_mRNA_partial_restoration_at_25_50_75_percent"
                ),
                "primary_endpoint": (
                    "RIG_I_IRF7_type_I_IFN_module_and_predeclared_AXIS_signature"
                ),
                "safety_endpoint": (
                    "viability|ribosome_biogenesis|global_RNA_processing"
                ),
                "advance_rule": (
                    "dose-dependent disease-selective normalization with less "
                    "than 20_percent fitness loss"
                ),
                "stop_rule": decision["stop_rule"],
            }
        return {
            "gene_symbol": gene,
            "priority": 2,
            "material": "fresh_PBMC_plasma_and_CD14_monocytes",
            "groups": "at_least_20_axSpA_and_20_matched_controls",
            "perturbation": (
                "observational_activity_assay_then_ex_vivo_titration_only"
            ),
            "primary_endpoint": (
                "ADA_enzyme_activity|adenosine|inosine|cytokine_response"
            ),
            "safety_endpoint": "T_B_cell_viability|proliferation|infection_response",
            "advance_rule": (
                "advance only if activity, metabolites and inflammatory "
                "phenotype define a consistent reversible direction"
            ),
            "stop_rule": decision["stop_rule"],
        }

    @staticmethod
    def _apply_robustness(
        decision: dict[str, object],
        meta: dict[str, str],
        composition: list[dict[str, str]],
    ) -> dict[str, object]:
        row = dict(decision)
        meta_p = float(meta.get("p_value") or 1.0)
        heterogeneity = float(meta.get("i_squared_percent") or 0.0)
        attenuated = sum(
            bool(value.get("effect_retained_percent"))
            and float(value["effect_retained_percent"]) < 50
            for value in composition
        )
        row.update(
            {
                "random_effects_p_value": meta.get("p_value", ""),
                "random_effects_i_squared_percent": meta.get(
                    "i_squared_percent", ""
                ),
                "composition_attenuated_studies": attenuated,
            }
        )
        if (
            row["gene_symbol"] == "DDX24"
            and (meta_p > 0.05 or heterogeneity >= 75 or attenuated >= 2)
        ):
            row["decision"] = "deprioritise_pending_reference_deconvolution"
            row["therapeutic_direction"] = (
                "do not perturb until a validated cell-composition adjustment "
                "and independent cohort support a within-cell effect"
            )
            row["principal_risk"] = (
                "The random-effects signal is non-significant and highly "
                "heterogeneous; marker-score adjustment strongly attenuates "
                "the bulk association."
            )
            row["stop_rule"] = (
                "Keep laboratory perturbation suspended unless reference-based "
                "deconvolution retains the DDX24 effect in independent cohorts."
            )
        return row

    @staticmethod
    def _apply_single_cell_reference(
        decision: dict[str, object],
        reference: list[dict[str, str]],
    ) -> dict[str, object]:
        row = dict(decision)
        target_rows = [
            value
            for value in reference
            if value.get("gene_symbol") == row["gene_symbol"]
        ]
        significant = [
            value
            for value in target_rows
            if float(value.get("adjusted_p_value") or 1.0) < 0.05
        ]
        lower = [
            value
            for value in significant
            if value.get("direction") == "lower_in_case"
        ]
        row.update(
            {
                "reference_cell_types_tested": len(target_rows),
                "reference_significant_cell_types": len(significant),
                "reference_lower_in_case_cell_types": len(lower),
                "reference_validation_role": (
                    "subject_level_GSE194315_PBMC_pseudobulk"
                ),
            }
        )
        if row["gene_symbol"] == "DDX24" and len(lower) >= 5:
            row["decision"] = "experimental_only_not_drug_ready"
            row["therapeutic_direction"] = (
                "within-cell support justifies controlled partial-restoration "
                "experiments; it does not justify a drug programme"
            )
            row["principal_risk"] = (
                "DDX24 is lower across multiple independently replicated PBMC "
                "cell types, reducing the likelihood of a pure composition "
                "artifact, but causality, tractability and safety remain unknown."
            )
            row["stop_rule"] = (
                "Stop if partial restoration fails to normalize the "
                "case-associated IFN/RLR programme or impairs cell fitness."
            )
        return row

    @staticmethod
    def _indexed(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"].strip().upper(): row
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("gene_symbol")
            }

    @staticmethod
    def _all_rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _dossier(directory: Path, gene: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            json.loads((directory / f"{gene}.json").read_text(encoding="utf-8")),
        )

    @staticmethod
    def _drugs(payload: dict[str, Any]) -> list[str]:
        target = cast(dict[str, Any], payload.get("target", {}))
        collection = cast(
            dict[str, Any], target.get("drugAndClinicalCandidates", {})
        )
        rows = cast(list[dict[str, Any]], collection.get("rows", []))
        return list(
            dict.fromkeys(
                str(row.get("drug", {}).get("name", "")).strip()
                for row in rows
                if str(row.get("drug", {}).get("name", "")).strip()
            )
        )

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0])
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
