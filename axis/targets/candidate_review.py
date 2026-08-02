"""Rule-based causal review of transcriptomic target candidates."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class CandidateReviewRun:
    candidates: int
    advance: int
    evidence_generation: int
    output_path: Path
    summary_path: Path


class CandidateReviewBuilder:
    """Keep causal, safety and tractability dimensions explicit."""

    def build(
        self,
        candidate_path: str | Path,
        *,
        intelligence_path: str | Path,
        genetics_path: str | Path,
        context_path: str | Path,
        output_root: str | Path,
    ) -> CandidateReviewRun:
        candidates = self._rows(Path(candidate_path))
        intelligence = self._indexed(Path(intelligence_path))
        genetics = self._indexed(Path(genetics_path))
        context = self._indexed(Path(context_path))
        selected = [
            row
            for row in candidates
            if row.get("structural_triage") == "eligible_after_causal_review"
        ]
        rows = [
            self._review(
                candidate,
                intelligence.get(candidate["gene_symbol"], {}),
                genetics.get(candidate["gene_symbol"], {}),
                context.get(candidate["gene_symbol"], {}),
            )
            for candidate in selected
        ]
        order = {
            "advance_to_perturbation": 0,
            "generate_causal_evidence": 1,
            "deprioritise_safety_or_essentiality": 2,
        }
        rows.sort(
            key=lambda row: (
                order[str(row["decision"])],
                -float(str(row["exploratory_score"])),
            )
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "candidate-causal-review.tsv"
        self._write(output_path, rows)
        advance = sum(row["decision"] == "advance_to_perturbation" for row in rows)
        evidence = sum(row["decision"] == "generate_causal_evidence" for row in rows)
        summary_path = destination / "candidate-causal-review.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "candidate_causal_safety_review",
                    "created_at": datetime.now(UTC).isoformat(),
                    "candidates_reviewed": len(rows),
                    "advance_to_perturbation": advance,
                    "generate_causal_evidence": evidence,
                    "decision_rules": {
                        "advance_to_perturbation": (
                            "single-cell FDR <= 0.05, bulk direction agreement, "
                            "disease genetic evidence, locus-to-gene score >= 0.5, "
                            "no reported safety liability and not marked essential"
                        ),
                        "deprioritise_safety_or_essentiality": (
                            "reported safety liability or target marked essential"
                        ),
                        "generate_causal_evidence": (
                            "expression support exists but causal or safety gate "
                            "for perturbation is incomplete"
                        ),
                        "structural_assessment": (
                            "PDB/AlphaFold review is allowed only after the "
                            "advance_to_perturbation decision"
                        ),
                    },
                    "warning": (
                        "Absence of a reported safety liability is not evidence "
                        "of safety. Decisions prioritise experiments and are not "
                        "therapeutic recommendations."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CandidateReviewRun(
            candidates=len(rows),
            advance=advance,
            evidence_generation=evidence,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def selected_genes(path: str | Path) -> tuple[str, ...]:
        return tuple(
            row["gene_symbol"]
            for row in CandidateReviewBuilder._rows(Path(path))
            if row.get("structural_triage") == "eligible_after_causal_review"
        )

    @staticmethod
    def _review(
        candidate: dict[str, str],
        intelligence: dict[str, str],
        genetics: dict[str, str],
        context: dict[str, str],
    ) -> dict[str, object]:
        resolved = intelligence.get("resolved", "").lower() == "true"
        safety = int(intelligence.get("safety_liabilities") or 0)
        essential_value = intelligence.get("is_essential", "").lower()
        essential = essential_value in {"true", "yes", "1"}
        genetic_count = int(genetics.get("genetic_evidence_count") or 0)
        l2g = float(context.get("maximum_locus_to_gene_score") or 0.0)
        expression_gate = (
            float(candidate["best_single_cell_adjusted_p_value"]) <= 0.05
            and candidate.get("single_cell_bulk_direction_agrees", "").lower() == "true"
        )
        causal_gate = genetic_count > 0 and l2g >= 0.5
        safety_gate = resolved and safety == 0 and not essential
        if safety > 0 or essential:
            decision = "deprioritise_safety_or_essentiality"
        elif expression_gate and causal_gate and safety_gate:
            decision = "advance_to_perturbation"
        else:
            decision = "generate_causal_evidence"
        missing: list[str] = []
        if not resolved:
            missing.append("resolve_target_annotation")
        if not expression_gate:
            missing.append("independent_expression_replication")
        if genetic_count == 0:
            missing.append("disease_genetic_support")
        if l2g < 0.5:
            missing.append("causal_gene_assignment")
        if not intelligence.get("is_essential"):
            missing.append("experimental_essentiality_screen")
        if safety == 0:
            missing.append("experimental_safety_assessment")
        if decision == "advance_to_perturbation":
            next_experiment = "cell_type_specific_CRISPRi_CRISPRa"
            structure = "review_PDB_then_AlphaFold_if_needed"
        elif decision == "deprioritise_safety_or_essentiality":
            next_experiment = "stop_or_define_tissue_selective_strategy"
            structure = "defer"
        else:
            next_experiment = missing[0] if missing else "independent_replication"
            structure = "defer"
        return {
            "gene_symbol": candidate["gene_symbol"],
            "decision": decision,
            "exploratory_score": float(candidate["exploratory_score"]),
            "single_cell_fdr": float(candidate["best_single_cell_adjusted_p_value"]),
            "single_cell_direction": candidate["best_single_cell_direction"],
            "bulk_direction": candidate.get("bulk_direction", ""),
            "single_cell_bulk_agrees": expression_gate,
            "genetic_evidence_count": genetic_count,
            "therapeutic_direction": genetics.get("therapeutic_direction", "unknown"),
            "maximum_locus_to_gene_score": l2g,
            "strong_molecular_colocalisations": int(
                context.get("strong_molecular_colocalisations") or 0
            ),
            "tractability_modalities": intelligence.get("tractability_modalities", ""),
            "clinical_candidates": int(intelligence.get("clinical_candidates") or 0),
            "safety_liabilities": safety,
            "essentiality_annotation": intelligence.get("is_essential", ""),
            "missing_evidence": "|".join(missing),
            "next_experiment": next_experiment,
            "structural_assessment": structure,
        }

    @staticmethod
    def _rows(path: Path) -> list[dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return list(csv.DictReader(source, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(f"cannot read candidate table {path}: {error}") from error

    @staticmethod
    def _indexed(path: Path) -> dict[str, dict[str, str]]:
        return {
            row["gene_symbol"].strip().upper(): row
            for row in CandidateReviewBuilder._rows(path)
        }

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
