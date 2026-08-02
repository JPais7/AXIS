"""Hierarchical target synthesis without pooling incompatible assay contexts."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class HierarchicalEvidenceRun:
    targets: int
    cohorts: int
    participants: int
    cohort_path: Path
    context_path: Path
    synthesis_path: Path
    method_path: Path


class HierarchicalEvidenceAnalyzer:
    """Summarize CD8 and bulk evidence in strata, never as one pooled effect."""

    TARGETS = ("DDX24", "ADA")

    def analyze(
        self,
        *,
        cd8_effects_path: str | Path,
        cd8_summary_path: str | Path,
        microarray_effects_path: str | Path,
        microarray_summary_path: str | Path,
        gse181364_path: str | Path,
        gse299639_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/hierarchical-target-evidence"
        ),
    ) -> HierarchicalEvidenceRun:
        cohorts = self._cd8(Path(cd8_effects_path))
        cohorts.extend(self._microarray(Path(microarray_effects_path)))
        cohorts.extend(self._sequencing(Path(gse181364_path), Path(gse299639_path)))
        contexts = self._contexts(
            cohorts,
            Path(microarray_summary_path),
            Path(cd8_summary_path),
        )
        synthesis = [self._synthesis(gene, cohorts, contexts) for gene in self.TARGETS]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        cohort_path = destination / "cohort-evidence.tsv"
        context_path = destination / "context-summary.tsv"
        synthesis_path = destination / "hierarchical-synthesis.tsv"
        method_path = destination / "synthesis-method.json"
        self._write(cohort_path, cohorts)
        self._write(context_path, contexts)
        self._write(synthesis_path, synthesis)
        method_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "hierarchical_multimodal_validation",
                    "principle": (
                        "Pool only within compatible assay/tissue strata; "
                        "compare directions across strata without a global effect."
                    ),
                    "strata": [
                        "donor-level CD8 single-cell pseudobulk",
                        "normalized peripheral-blood microarray",
                        "exploratory whole-blood RNA sequencing",
                    ],
                    "primary_target": "DDX24",
                    "negative_control_target": "ADA",
                    "guardrails": [
                        "No cross-platform pooled effect or global p-value.",
                        "Each independent cohort counts once.",
                        "Cells are never treated as independent observations.",
                        "GSE181364 and GSE299639 remain directional evidence.",
                        "Association does not establish causality or druggability.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        participants = sum(
            int(cast(Any, row["case_samples"]))
            + int(cast(Any, row["control_samples"]))
            for row in cohorts
            if row["gene_symbol"] == "DDX24"
        )
        return HierarchicalEvidenceRun(
            targets=2,
            cohorts=len(cohorts) // 2,
            participants=participants,
            cohort_path=cohort_path,
            context_path=context_path,
            synthesis_path=synthesis_path,
            method_path=method_path,
        )

    def _cd8(self, path: Path) -> list[dict[str, object]]:
        rows = self._read(path)
        return [
            {
                "gene_symbol": row["gene_symbol"],
                "cohort": row["cohort"],
                "context": "CD8_single_cell",
                "assay": "donor_pseudobulk_log2_CPM",
                "case_samples": row["case_donors"],
                "control_samples": row["control_donors"],
                "effect": row["effect"],
                "p_value": row["p_value"],
                "direction": self._direction(float(row["effect"])),
                "inferential_role": "compatible_within_CD8_pool",
            }
            for row in rows
        ]

    def _microarray(self, path: Path) -> list[dict[str, object]]:
        return [
            {
                "gene_symbol": row["gene_symbol"],
                "cohort": row["study"],
                "context": "peripheral_blood_microarray",
                "assay": "normalized_microarray_log_expression",
                "case_samples": row["case_samples"],
                "control_samples": row["control_samples"],
                "effect": row["effect"],
                "p_value": row["p_value"],
                "direction": self._direction(float(row["effect"])),
                "inferential_role": "compatible_within_microarray_pool",
            }
            for row in self._read(path)
            if row["gene_symbol"] in self.TARGETS
        ]

    def _sequencing(self, gse181: Path, gse299: Path) -> list[dict[str, object]]:
        first = {
            row["gene_symbol"]: row
            for row in self._read(gse181)
            if row["gene_symbol"] in self.TARGETS
        }
        second = {
            row["gene_symbol"]: row
            for row in self._read(gse299)
            if row["gene_symbol"] in self.TARGETS
        }
        output: list[dict[str, object]] = []
        for gene in self.TARGETS:
            for cohort, row, cases, controls, effect_key, p_key, assay in (
                (
                    "GSE181364",
                    first[gene],
                    5,
                    3,
                    "validation_effect",
                    "validation_p_value",
                    "normalized_FPKM",
                ),
                (
                    "GSE299639",
                    second[gene],
                    6,
                    6,
                    "full_effect",
                    "full_p_value",
                    "long_read_TPM",
                ),
            ):
                effect = float(row[effect_key])
                output.append(
                    {
                        "gene_symbol": gene,
                        "cohort": cohort,
                        "context": "whole_blood_RNA_sequencing",
                        "assay": assay,
                        "case_samples": cases,
                        "control_samples": controls,
                        "effect": effect,
                        "p_value": row[p_key],
                        "direction": self._direction(effect),
                        "inferential_role": "directional_only_incompatible_scales",
                    }
                )
        return output

    def _contexts(
        self, cohorts: list[dict[str, object]], microarray: Path, cd8: Path
    ) -> list[dict[str, object]]:
        pooled = {
            ("CD8_single_cell", row["gene_symbol"]): row
            for row in self._read(cd8)
        }
        pooled.update(
            {
                ("peripheral_blood_microarray", row["gene_symbol"]): row
                for row in self._read(microarray)
            }
        )
        output: list[dict[str, object]] = []
        for gene in self.TARGETS:
            for context in (
                "CD8_single_cell",
                "peripheral_blood_microarray",
                "whole_blood_RNA_sequencing",
            ):
                selected = [
                    row
                    for row in cohorts
                    if row["gene_symbol"] == gene and row["context"] == context
                ]
                lower = sum(row["direction"] == "lower_in_case" for row in selected)
                entry = pooled.get((context, gene))
                output.append(
                    {
                        "gene_symbol": gene,
                        "context": context,
                        "cohorts": len(selected),
                        "participants": sum(
                            int(cast(Any, row["case_samples"]))
                            + int(cast(Any, row["control_samples"]))
                            for row in selected
                        ),
                        "lower_in_case_cohorts": lower,
                        "higher_in_case_cohorts": len(selected) - lower,
                        "context_direction": (
                            "lower_in_case"
                            if lower > len(selected) / 2
                            else "higher_in_case"
                            if lower < len(selected) / 2
                            else "mixed"
                        ),
                        "pooled_effect": (
                            entry.get("random_effect", entry.get("pooled_effect", ""))
                            if entry
                            else ""
                        ),
                        "pooled_p_value": entry.get("p_value", "") if entry else "",
                        "pooling_status": (
                            "within_context_random_effects"
                            if entry
                            else "directional_summary_only"
                        ),
                    }
                )
        return output

    @staticmethod
    def _synthesis(
        gene: str,
        cohorts: list[dict[str, object]],
        contexts: list[dict[str, object]],
    ) -> dict[str, object]:
        gene_cohorts = [row for row in cohorts if row["gene_symbol"] == gene]
        gene_contexts = [row for row in contexts if row["gene_symbol"] == gene]
        lower = sum(row["direction"] == "lower_in_case" for row in gene_cohorts)
        supporting = sum(
            row["context_direction"] == "lower_in_case" for row in gene_contexts
        )
        return {
            "gene_symbol": gene,
            "independent_cohorts": len(gene_cohorts),
            "participants": sum(
                int(cast(Any, row["case_samples"]))
                + int(cast(Any, row["control_samples"]))
                for row in gene_cohorts
            ),
            "lower_in_case_cohorts": lower,
            "higher_in_case_cohorts": len(gene_cohorts) - lower,
            "lower_in_case_contexts": supporting,
            "total_contexts": len(gene_contexts),
            "cross_context_conclusion": (
                "directionally_supported_across_contexts"
                if supporting >= 2 and lower >= 5
                else "context_dependent_or_mixed"
            ),
            "global_effect": "not_estimated_incompatible_contexts",
            "global_p_value": "not_estimated",
        }

    @staticmethod
    def _direction(effect: float) -> str:
        return "lower_in_case" if effect < 0 else "higher_in_case"

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
