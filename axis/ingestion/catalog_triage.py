"""Conservative, auditable triage of direct-disease GEO catalog candidates."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class CatalogTriageRun:
    candidates: int
    high_priority: int
    medium_priority: int
    manual_review: int
    output_path: Path
    priority_path: Path
    summary_path: Path


class CatalogTriageBuilder:
    """Rank direct candidates without mistaking keyword matches for eligibility."""

    REQUIRED_FIELDS = {
        "accession",
        "primary_role",
        "title",
        "summary",
        "organisms",
        "experiment_type",
        "sample_count",
        "eligibility_status",
        "estimated_download_class",
    }

    def build(
        self,
        catalog_path: str | Path = Path("data/catalog/study-catalog.tsv"),
        *,
        output_root: str | Path = Path("data/catalog"),
    ) -> CatalogTriageRun:
        source = Path(catalog_path)
        with source.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            missing = self.REQUIRED_FIELDS - set(reader.fieldnames or ())
            if missing:
                raise ValueError(
                    f"catalog is missing required fields: {sorted(missing)}"
                )
            candidates = [
                self._classify(row)
                for row in reader
                if row["primary_role"] == "direct_disease_candidate"
                and row["eligibility_status"] == "metadata_review_candidate"
            ]

        candidates.sort(
            key=lambda row: (
                -self._priority_score(row["priority_score"]),
                -self._sample_count(str(row["sample_count"])),
                str(row["accession"]),
            ),
        )
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "direct-study-triage.tsv"
        priority_path = destination / "direct-study-priority-queue.tsv"
        summary_path = destination / "direct-study-triage.json"
        self._write(output_path, candidates)
        actionable = [
            row for row in candidates if row["priority_tier"] in {"high", "medium"}
        ]
        self._write(priority_path, actionable)

        tiers = Counter(str(row["priority_tier"]) for row in candidates)
        tissues = Counter(str(row["tissue_signal"]) for row in candidates)
        assays = Counter(str(row["assay_signal"]) for row in candidates)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "direct_disease_metadata_triage",
                    "created_at": datetime.now(UTC).isoformat(),
                    "source_catalog": str(source),
                    "candidates": len(candidates),
                    "priority_tiers": dict(sorted(tiers.items())),
                    "tissue_signals": dict(sorted(tissues.items())),
                    "assay_signals": dict(sorted(assays.items())),
                    "priority_queue": len(actionable),
                    "policy": (
                        "Rules use GEO title, summary and Series-level metadata. "
                        "They prioritize manual review and never approve a study."
                    ),
                    "mandatory_manual_checks": [
                        "verify case and control sample labels",
                        "verify untreated baseline samples and treatment arms",
                        "verify tissue and cell composition",
                        "verify subject independence and repeated measures",
                        "verify covariates, batch, sex and age",
                        "verify processed expression and annotation availability",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CatalogTriageRun(
            candidates=len(candidates),
            high_priority=tiers["high"],
            medium_priority=tiers["medium"],
            manual_review=tiers["manual_review"],
            output_path=output_path,
            priority_path=priority_path,
            summary_path=summary_path,
        )

    @classmethod
    def _classify(cls, row: dict[str, str]) -> dict[str, object]:
        text = f"{row['title']} {row['summary']}".lower()
        disease = cls._first_signal(
            text,
            (
                ("axspa_specific", r"\baxspa\b|axial spondyloarthritis"),
                ("ankylosing_spondylitis", r"ankylosing spondylitis"),
                ("spondyloarthritis_unspecified", r"\bspondyloarthritis\b"),
                ("hla_b27_context", r"hla[\s-]?b27"),
            ),
        )
        tissue = cls._first_signal(
            text,
            (
                ("enthesis_bone_cartilage", r"enthes|bone|osteoblast|cartilage"),
                ("synovial", r"synovi"),
                ("pbmc", r"\bpbmc|peripheral blood mononuclear"),
                (
                    "sorted_immune_cells",
                    r"\bt[\s-]?cell|\bb[\s-]?cell|monocyte|macrophage|neutrophil",
                ),
                ("whole_blood", r"whole blood|\bblood\b"),
                ("intestinal", r"\bgut\b|intestinal|colon|ileum"),
                ("skin", r"\bskin\b|keratinocyte"),
            ),
        )
        assay = cls._first_signal(
            f"{row['experiment_type']} {text}".lower(),
            (
                ("single_cell", r"single[\s-]?cell|scrna"),
                ("bulk_rna_seq", r"rna[\s-]?seq|high throughput sequencing"),
                ("microarray", r"\barray\b|microarray"),
            ),
        )
        design = cls._first_signal(
            text,
            (
                (
                    "case_control_signal",
                    r"case[\s/-]?control|patients? (?:and|versus|vs\.?) "
                    r"(?:healthy )?controls?|healthy (?:donors|subjects|controls)",
                ),
                (
                    "treatment_response_signal",
                    r"before and after|pre[\s-]?treatment|post[\s-]?treatment|"
                    r"treatment response|drug response|anti[\s-]?tnf|adalimumab|"
                    r"infliximab|secukinumab",
                ),
                (
                    "mechanistic_signal",
                    r"in vitro|stimulat|knockdown|crispr|cell line",
                ),
            ),
        )
        treatment = cls._first_signal(
            text,
            (
                ("untreated_signal", r"untreated|treatment[\s-]?naive|drug[\s-]?naive"),
                (
                    "treated_or_longitudinal_signal",
                    r"treated|therapy|therapeutic|anti[\s-]?tnf|adalimumab|"
                    r"infliximab|secukinumab|before and after",
                ),
            ),
        )

        score = 0
        reasons: list[str] = []
        if disease in {"axspa_specific", "ankylosing_spondylitis"}:
            score += 3
            reasons.append("specific_disease_term")
        elif disease == "spondyloarthritis_unspecified":
            score += 1
            reasons.append("broad_disease_term")
        if design == "case_control_signal":
            score += 3
            reasons.append("case_control_language")
        elif design in {"treatment_response_signal", "mechanistic_signal"}:
            score -= 2
            reasons.append(design)
        if tissue in {
            "enthesis_bone_cartilage",
            "synovial",
            "pbmc",
            "sorted_immune_cells",
            "whole_blood",
        }:
            score += 2
            reasons.append(f"relevant_tissue:{tissue}")
        if treatment == "untreated_signal":
            score += 1
            reasons.append("untreated_language")
        elif treatment == "treated_or_longitudinal_signal":
            score -= 2
            reasons.append("treatment_confounding_signal")
        if assay in {"bulk_rna_seq", "microarray", "single_cell"}:
            score += 1
            reasons.append(f"supported_assay:{assay}")
        if row["shared_bioproject_flag"] == "True":
            reasons.append("shared_bioproject_review")
        if row["shared_publication_flag"] == "True":
            reasons.append("shared_publication_review")

        if score >= 7 and design == "case_control_signal":
            tier = "high"
        elif score >= 4:
            tier = "medium"
        else:
            tier = "manual_review"
        return {
            **row,
            "disease_signal": disease,
            "tissue_signal": tissue,
            "assay_signal": assay,
            "design_signal": design,
            "treatment_signal": treatment,
            "priority_score": score,
            "priority_tier": tier,
            "priority_reasons": "|".join(reasons) or "insufficient_metadata_signals",
            "automatic_eligibility": False,
            "next_action": (
                "inspect_GEO_sample_metadata"
                if tier in {"high", "medium"}
                else "manual_relevance_review"
            ),
        }

    @staticmethod
    def _first_signal(text: str, patterns: tuple[tuple[str, str], ...]) -> str:
        for label, pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return label
        return "unclear"

    @staticmethod
    def _sample_count(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    @staticmethod
    def _priority_score(value: object) -> int:
        if not isinstance(value, int):
            raise TypeError("triage priority score must be an integer")
        return value

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
