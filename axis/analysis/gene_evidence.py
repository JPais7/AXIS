"""Build a conservative, auditable gene-level evidence master table."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class GeneEvidenceRun:
    genes: int
    pharmacological_priorities: int
    experimental_priorities: int
    secondary_hypotheses: int
    master_path: Path
    priority_path: Path
    methodology_path: Path


class GeneEvidenceBuilder:
    """Integrate independent evidence without allowing one source to dominate."""

    def build(
        self,
        *,
        shortlist_path: str | Path,
        single_cell_path: str | Path,
        causal_review_path: str | Path,
        karow_signature_path: str | Path,
        genetics_path: str | Path,
        intelligence_path: str | Path,
        output_root: str | Path = Path("data/analysis/gene-evidence"),
    ) -> GeneEvidenceRun:
        shortlist = self._indexed(Path(shortlist_path))
        single_cell = self._indexed(Path(single_cell_path))
        causal = self._indexed(Path(causal_review_path))
        genetics = self._indexed(Path(genetics_path))
        intelligence = self._indexed(Path(intelligence_path))
        karow = self._karow(Path(karow_signature_path))
        genes = sorted(set(shortlist) | set(causal))
        rows = [
            self._gene(
                gene,
                shortlist.get(gene, {}),
                single_cell.get(gene, {}),
                causal.get(gene, {}),
                karow.get(gene, []),
                genetics.get(gene, {}),
                intelligence.get(gene, {}),
            )
            for gene in genes
        ]
        rows.sort(
            key=lambda row: (
                -self._integer(str(row["total_score"])),
                str(row["gene_symbol"]),
            )
        )
        for rank, row in enumerate(rows, 1):
            row["master_rank"] = rank
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        master_path = destination / "gene-evidence-master.tsv"
        self._write(master_path, rows)
        priority_path = destination / "actionable-priorities.tsv"
        self._write(
            priority_path,
            [
                row
                for row in rows
                if row["priority_group"]
                in {"pharmacological_priority", "experimental_priority"}
            ],
        )
        methodology_path = destination / "evidence-methodology.json"
        methodology_path.write_text(
            json.dumps(self._methodology(rows), indent=2) + "\n",
            encoding="utf-8",
        )
        return GeneEvidenceRun(
            genes=len(rows),
            pharmacological_priorities=sum(
                row["priority_group"] == "pharmacological_priority"
                for row in rows
            ),
            experimental_priorities=sum(
                row["priority_group"] == "experimental_priority"
                for row in rows
            ),
            secondary_hypotheses=sum(
                row["priority_group"] == "secondary_hypothesis"
                for row in rows
            ),
            master_path=master_path,
            priority_path=priority_path,
            methodology_path=methodology_path,
        )

    def _gene(
        self,
        gene: str,
        bulk: dict[str, str],
        single: dict[str, str],
        causal: dict[str, str],
        karow: list[dict[str, str]],
        genetic: dict[str, str],
        target: dict[str, str],
    ) -> dict[str, object]:
        studies = self._integer(bulk.get("available_studies"))
        bulk_q = self._number(bulk.get("combined_adjusted_p_value"), 1.0)
        concordant = self._boolean(bulk.get("direction_concordant"))
        bulk_score = min(studies, 3) * 8
        bulk_score += 6 if concordant and studies >= 2 else 0
        bulk_score += 4 if bulk_q <= 0.05 else 0

        single_fdr = self._number(
            single.get("best_single_cell_adjusted_p_value"), 1.0
        )
        single_agrees = self._boolean(
            single.get("single_cell_bulk_direction_agrees")
        )
        if single_fdr <= 0.05 and single_agrees:
            single_score = 18
            single_status = "significant_directional_support"
        elif single_fdr <= 0.05:
            single_score = 6
            single_status = "significant_without_bulk_agreement"
        else:
            single_score = 0
            single_status = "not_significant_or_not_tested"

        expected = bulk.get("direction") or causal.get("bulk_direction", "")
        karow_support = {
            row["cohort"]
            for row in karow
            if row["direction"] == expected
        }
        karow_conflict = {
            row["cohort"]
            for row in karow
            if expected and row["direction"] != expected
        }
        karow_score = (
            (5 if "cohort_1" in karow_support else 0)
            + (9 if "cohort_2" in karow_support else 0)
            - (7 if "cohort_1" in karow_conflict else 0)
            - (10 if "cohort_2" in karow_conflict else 0)
        )

        genetic_count = self._integer(genetic.get("genetic_evidence_count"))
        genetic_max = self._number(genetic.get("maximum_evidence_score"), 0.0)
        genetics_score = min(20, genetic_count * 4 + round(genetic_max * 12))

        modalities = [
            value
            for value in target.get("tractability_modalities", "").split("|")
            if value
        ]
        clinical = self._integer(target.get("clinical_candidates"))
        safety = self._integer(target.get("safety_liabilities"))
        essential = self._integer(target.get("is_essential"))
        tractability_score = min(9, len(modalities) * 3)
        clinical_score = 6 if clinical > 0 else 0
        safety_penalty = min(12, safety * 3 + (5 if essential > 0 else 0))

        layers = sum(
            (
                studies >= 2,
                single_fdr <= 0.05,
                bool(karow),
                genetic_count > 0,
                bool(modalities) or clinical > 0,
            )
        )
        total = max(
            0,
            min(
                100,
                bulk_score
                + single_score
                + karow_score
                + genetics_score
                + tractability_score
                + clinical_score
                - safety_penalty,
            ),
        )
        if total >= 60 and layers >= 2 and (genetic_count > 0 or clinical > 0):
            group = "pharmacological_priority"
            next_action = "confirm_therapeutic_direction_and_drug_safety"
        elif total >= 35 and layers >= 2:
            group = "experimental_priority"
            next_action = "validate_mechanism_in_independent_model"
        else:
            group = "secondary_hypothesis"
            next_action = "collect_independent_evidence"
        conflict_count = len(karow_conflict) + (
            1 if single_fdr <= 0.05 and not single_agrees else 0
        )
        return {
            "master_rank": 0,
            "gene_symbol": gene,
            "priority_group": group,
            "total_score": total,
            "independent_evidence_layers": layers,
            "expected_direction": expected,
            "bulk_studies": studies,
            "bulk_direction_concordant": concordant,
            "bulk_adjusted_p_value": bulk_q if bulk else "",
            "bulk_score": bulk_score,
            "single_cell_status": single_status,
            "single_cell_adjusted_p_value": (
                single_fdr if single else ""
            ),
            "single_cell_score": single_score,
            "karow_supporting_cohorts": "|".join(sorted(karow_support)),
            "karow_conflicting_cohorts": "|".join(sorted(karow_conflict)),
            "karow_score": karow_score,
            "genetic_evidence_count": genetic_count,
            "maximum_genetic_score": genetic_max,
            "genetics_score": genetics_score,
            "tractability_modalities": "|".join(modalities),
            "clinical_candidates": clinical,
            "tractability_clinical_score": tractability_score + clinical_score,
            "safety_liabilities": safety,
            "is_essential": essential,
            "safety_penalty": safety_penalty,
            "directional_conflicts": conflict_count,
            "causal_review_decision": causal.get("decision", ""),
            "next_action": next_action,
        }

    @staticmethod
    def _indexed(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"].strip().upper(): row
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("gene_symbol")
            }

    @staticmethod
    def _karow(path: Path) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                gene = row.get("gene_symbol", "").strip().upper()
                if gene:
                    result.setdefault(gene, []).append(row)
        return result

    @staticmethod
    def _number(value: str | None, default: float) -> float:
        try:
            return float(value or default)
        except ValueError:
            return default

    @staticmethod
    def _integer(value: str | None) -> int:
        try:
            return int(float(value or 0))
        except ValueError:
            return 0

    @staticmethod
    def _boolean(value: str | None) -> bool:
        return (value or "").lower() == "true"

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _methodology(rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "genes": len(rows),
            "score_range": "0-100",
            "components": {
                "bulk_recurrence": "0-34",
                "single_cell": "0-18",
                "karow_publication": "-17 to +14",
                "human_genetics": "0-20",
                "tractability_and_clinical_precedent": "0-15",
                "safety_penalty": "0 to -12",
            },
            "classification": {
                "pharmacological_priority": (
                    "score >=60, at least two evidence layers, and human "
                    "genetics or a clinical candidate"
                ),
                "experimental_priority": (
                    "score >=35 and at least two evidence layers"
                ),
                "secondary_hypothesis": "all remaining genes",
            },
            "guardrails": [
                "Karow published lists receive less weight than subject-level data.",
                "Missing evidence is not treated as negative evidence.",
                "Directional conflicts are explicit and penalized.",
                "MicroRNA signals are not counted as gene-level causal evidence.",
                "A high score alone cannot create a pharmacological priority.",
            ],
        }
