"""Auditable therapeutic-readiness matrix for genetically supported targets."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class TherapeuticReadinessRun:
    targets: int
    mechanistic_priorities: int
    direction_resolved: int
    output_path: Path
    summary_path: Path


class TherapeuticReadinessBuilder:
    """Join evidence dimensions while preserving uncertainty and provenance."""

    def build(
        self,
        *,
        genetics_path: str | Path,
        context_path: str | Path,
        discovery_path: str | Path,
        validation_path: str | Path,
        intelligence_path: str | Path,
        nucleome_path: str | Path | None = None,
        output_root: str | Path = Path("data/targets/readiness"),
    ) -> TherapeuticReadinessRun:
        genetics = self._indexed(Path(genetics_path))
        context = self._indexed(Path(context_path))
        discovery = self._indexed(Path(discovery_path))
        validation = self._indexed(Path(validation_path))
        intelligence = self._indexed(Path(intelligence_path))
        nucleome = (
            self._nucleome(Path(nucleome_path)) if nucleome_path is not None else {}
        )
        genes = tuple(
            gene
            for gene, row in genetics.items()
            if int(row["genetic_evidence_count"]) > 0
        )
        rows = [
            self._row(
                gene,
                genetics[gene],
                context.get(gene, {}),
                discovery.get(gene, {}),
                validation.get(gene, {}),
                intelligence.get(gene, {}),
                nucleome.get(gene, {}),
            )
            for gene in genes
        ]
        rows.sort(
            key=lambda row: (
                row["follow_up_priority"] != "mechanistic_priority",
                -cast(float, row["maximum_locus_to_gene_score"]),
                str(row["gene_symbol"]),
            )
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "therapeutic-readiness.tsv"
        self._write(output_path, rows)
        priorities = sum(
            row["follow_up_priority"] == "mechanistic_priority" for row in rows
        )
        resolved = sum(
            row["genetic_therapeutic_direction"] in {"inhibit", "activate"}
            for row in rows
        )
        summary_path = destination / "therapeutic-readiness.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "therapeutic_readiness",
                    "created_at": datetime.now(UTC).isoformat(),
                    "targets": len(rows),
                    "mechanistic_priorities": priorities,
                    "therapeutic_direction_resolved": resolved,
                    "decision_rules": {
                        "mechanistic_priority": (
                            "locus-to-gene score >= 0.5 and external direction agrees"
                        ),
                        "supportive_follow_up": (
                            "external direction agrees but locus-to-gene score "
                            "is below 0.5"
                        ),
                        "deprioritised_pending_replication": (
                            "external direction disagrees or is unavailable"
                        ),
                        "drug_actionability": (
                            "requires explicit genetic therapeutic direction; "
                            "disease expression is not used as a substitute"
                        ),
                        "nucleome_context": (
                            "reported independently and does not alter target "
                            "priority or therapeutic direction"
                        ),
                    },
                    "expression_scope": (
                        "bulk disease differential expression plus normal "
                        "baseline context; neither establishes cell-specific "
                        "causality"
                    ),
                    "drug_scope": (
                        "Open Targets clinical precedent for the target across "
                        "all diseases; not evidence of efficacy in ankylosing "
                        "spondylitis"
                    ),
                    "warning": (
                        "This matrix prioritises experiments. It does not "
                        "recommend treatment or establish that a listed drug "
                        "should be used for axial spondyloarthritis."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return TherapeuticReadinessRun(
            targets=len(rows),
            mechanistic_priorities=priorities,
            direction_resolved=resolved,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _indexed(path: Path) -> dict[str, dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return {
                    row["gene_symbol"].strip().upper(): row
                    for row in csv.DictReader(source, delimiter="\t")
                }
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read evidence table {path}: {error}") from error

    @staticmethod
    def _row(
        gene: str,
        genetics: dict[str, str],
        context: dict[str, str],
        discovery: dict[str, str],
        validation: dict[str, str],
        intelligence: dict[str, str],
        nucleome: dict[str, object],
    ) -> dict[str, object]:
        l2g = float(context.get("maximum_locus_to_gene_score") or 0.0)
        agrees = validation.get("direction_agrees", "").lower() == "true"
        validation_available = bool(validation.get("validation_direction"))
        if l2g >= 0.5 and agrees:
            priority = "mechanistic_priority"
        elif agrees:
            priority = "supportive_follow_up"
        else:
            priority = "deprioritised_pending_replication"
        direction = genetics.get("therapeutic_direction", "unknown")
        drugs = TherapeuticReadinessBuilder._drugs(intelligence)
        if direction in {"inhibit", "activate"} and drugs:
            actionability = "direction_resolved_with_clinical_precedent"
        elif drugs:
            actionability = "blocked_by_unknown_therapeutic_direction"
        else:
            actionability = "no_clinical_precedent_identified"
        normal_contexts = context.get("top_normal_expression_contexts", "")
        immune_terms = ("blood", "lymph", "t cell", "b cell", "immune", "spleen")
        immune_contexts = "|".join(
            item
            for item in normal_contexts.split("|")
            if any(term in item.lower() for term in immune_terms)
        )
        return {
            "gene_symbol": gene,
            "follow_up_priority": priority,
            "genetic_evidence_count": int(genetics["genetic_evidence_count"]),
            "maximum_genetic_evidence_score": float(genetics["maximum_evidence_score"]),
            "maximum_locus_to_gene_score": l2g,
            "strong_molecular_colocalisations": int(
                context.get("strong_molecular_colocalisations") or 0
            ),
            "discovery_expression_direction": discovery.get("direction", ""),
            "external_validation_available": validation_available,
            "external_expression_direction": validation.get("validation_direction", ""),
            "external_direction_agrees": agrees,
            "external_validation_p_value": validation.get("validation_p_value", ""),
            "normal_immune_contexts": immune_contexts,
            "reference_4d_contact_observed": bool(nucleome.get("observed", False)),
            "reference_4d_contact_donors": nucleome.get("donors", ""),
            "reference_4d_contact_cell_types": nucleome.get("cell_types", ""),
            "genetic_therapeutic_direction": direction,
            "clinical_candidate_count": int(
                intelligence.get("clinical_candidates") or 0
            ),
            "maximum_clinical_stage": intelligence.get("maximum_clinical_stage", ""),
            "known_target_drugs": drugs,
            "drug_actionability": actionability,
            "next_evidence_needed": TherapeuticReadinessBuilder._next_evidence(
                direction=direction,
                agrees=agrees,
                l2g=l2g,
                molecular=int(context.get("strong_molecular_colocalisations") or 0),
            ),
        }

    @staticmethod
    def _nucleome(path: Path) -> dict[str, dict[str, object]]:
        indexed: dict[str, dict[str, object]] = {}
        try:
            with path.open(encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source, delimiter="\t"):
                    gene = row["gene_symbol"].strip().upper()
                    record = indexed.setdefault(
                        gene,
                        {"observed": False, "donors_set": set(), "cells_set": set()},
                    )
                    if row.get("contact_status") != "observed_in_sample":
                        continue
                    record["observed"] = True
                    cast(set[str], record["donors_set"]).add(row["donor"])
                    cast(set[str], record["cells_set"]).add(row["cell_subtype"])
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(
                f"cannot read nucleome evidence table {path}: {error}"
            ) from error
        for record in indexed.values():
            record["donors"] = "|".join(sorted(cast(set[str], record["donors_set"])))
            record["cell_types"] = "|".join(sorted(cast(set[str], record["cells_set"])))
            del record["donors_set"]
            del record["cells_set"]
        return indexed

    @staticmethod
    def _drugs(intelligence: dict[str, str]) -> str:
        dossier = intelligence.get("dossier_path", "")
        if not dossier:
            return ""
        try:
            payload = json.loads(Path(dossier).read_text(encoding="utf-8"))
            target = cast(dict[str, Any], payload.get("target", {}))
            collection = cast(
                dict[str, Any], target.get("drugAndClinicalCandidates", {})
            )
            rows = cast(list[dict[str, Any]], collection.get("rows", []))
            return "|".join(
                dict.fromkeys(
                    str(row.get("drug", {}).get("name", "")).strip()
                    for row in rows
                    if str(row.get("drug", {}).get("name", "")).strip()
                )
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            return ""

    @staticmethod
    def _next_evidence(
        *, direction: str, agrees: bool, l2g: float, molecular: int
    ) -> str:
        needs: list[str] = []
        if direction not in {"inhibit", "activate"}:
            needs.append("resolve_causal_modulation_direction")
        if molecular == 0:
            needs.append("disease_relevant_cell_qtl_or_perturbation")
        if not agrees:
            needs.append("independent_expression_replication")
        if l2g < 0.5:
            needs.append("stronger_causal_gene_assignment")
        return "|".join(needs) or "preclinical_target_validation"

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
