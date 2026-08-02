"""Select independent new cohorts without mixing incompatible evidence strata."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class CohortSelectionRun:
    evaluated: int
    selected: int
    primary_replication: int
    mechanistic_context: int
    output_path: Path
    selection_path: Path
    summary_path: Path


class CohortSelectionBuilder:
    """Apply disease, modality, independence and prior-use gates."""

    AXSPA = re.compile(
        r"ankylosing spondylitis|\baxspa\b|axial spondyloarthritis",
        re.IGNORECASE,
    )
    OTHER_DISEASE = re.compile(
        r"rheumatoid arthritis|psoriatic arthritis|\bpsa\b", re.IGNORECASE
    )

    def build(
        self,
        *,
        validation_path: str | Path = Path(
            "data/catalog/sample-proposals/study-validation.tsv"
        ),
        sample_metadata_path: str | Path = Path(
            "data/catalog/sample-audit/sample-metadata.tsv"
        ),
        catalog_path: str | Path = Path("data/catalog/study-catalog.tsv"),
        geo_root: str | Path = Path("data/geo"),
        output_root: str | Path = Path("data/catalog/cohort-selection"),
        maximum: int = 5,
    ) -> CohortSelectionRun:
        if not 1 <= maximum <= 20:
            raise ValueError("maximum must be between 1 and 20")
        validations = [
            row
            for row in self._read(validation_path)
            if row["validation_status"] == "axspa_design_review_candidate"
        ]
        catalog = {row["accession"]: row for row in self._read(catalog_path)}
        by_study: dict[str, list[dict[str, str]]] = {}
        for metadata_row in self._read(sample_metadata_path):
            by_study.setdefault(metadata_row["study_accession"], []).append(
                metadata_row
            )

        rows: list[dict[str, object]] = [
            self._evaluate(
                validation,
                catalog[validation["accession"]],
                by_study.get(validation["accession"], []),
                geo_root=Path(geo_root),
            )
            for validation in validations
        ]
        rows.sort(
            key=lambda row: (
                not bool(row["passes_hard_gates"]),
                -self._score(row["selection_score"]),
                str(row["accession"]),
            )
        )
        selected: list[dict[str, object]] = []
        used_clusters: set[str] = set()
        for row in rows:
            if not row["passes_hard_gates"] or len(selected) >= maximum:
                continue
            cluster = str(row["evidence_cluster"])
            if cluster in used_clusters:
                row["selection_decision"] = "not_selected_same_evidence_cluster"
                continue
            row["selection_decision"] = "selected_for_manual_confirmation"
            selected.append(row)
            used_clusters.add(cluster)

        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "cohort-evaluation.tsv"
        selection_path = destination / "next-cohort-selection.tsv"
        summary_path = destination / "cohort-selection.json"
        self._write(output_path, rows)
        self._write(selection_path, selected)
        primary = sum(
            row["evidence_role"] == "primary_blood_replication" for row in selected
        )
        mechanistic = len(selected) - primary
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "independent_new_cohort_selection",
                    "created_at": datetime.now(UTC).isoformat(),
                    "evaluated": len(rows),
                    "selected": len(selected),
                    "maximum_requested": maximum,
                    "primary_blood_replication": primary,
                    "mechanistic_context": mechanistic,
                    "selection_policy": [
                        "explicit axSpA signal must be present in proposed "
                        "case samples",
                        "treated cohorts and non-mRNA assays are not selected",
                        "already analysed studies are not selected as new cohorts",
                        "at most one Series is selected per evidence cluster",
                        "tissue strata remain separate and are never pooled blindly",
                    ],
                    "automatic_eligibility": False,
                    "warning": (
                        "Selection only nominates cohorts for manual confirmation "
                        "and download. It does not approve their sample sheets."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CohortSelectionRun(
            evaluated=len(rows),
            selected=len(selected),
            primary_replication=primary,
            mechanistic_context=mechanistic,
            output_path=output_path,
            selection_path=selection_path,
            summary_path=summary_path,
        )

    def _evaluate(
        self,
        validation: dict[str, str],
        catalog: dict[str, str],
        samples: list[dict[str, str]],
        *,
        geo_root: Path,
    ) -> dict[str, object]:
        accession = validation["accession"]
        cases = [row for row in samples if row["suggested_group"] == "case"]
        controls = [row for row in samples if row["suggested_group"] == "control"]
        case_text = " ".join(
            f"{row['title']} {row['characteristics']}" for row in cases
        )
        explicit_axspa = self.AXSPA.search(case_text) is not None
        other_disease = self.OTHER_DISEASE.search(case_text) is not None
        treated_cases = sum(row["treatment_signal"] == "treated" for row in cases)
        unknown_treatment = sum(row["treatment_signal"] == "unknown" for row in cases)
        stratum, role = self._stratum(catalog)
        already_analyzed = any(
            (geo_root / accession).rglob("gene-level-results.tsv")
        ) or any((geo_root / accession).rglob("study-eligibility.json"))
        blockers: list[str] = []
        if not explicit_axspa:
            blockers.append("no_explicit_axspa_in_case_samples")
        if other_disease and not explicit_axspa:
            blockers.append("different_disease_in_case_samples")
        if treated_cases:
            blockers.append("treated_cases")
        if role == "context_only_non_mrna":
            blockers.append("non_mrna_expression_modality")
        if already_analyzed:
            blockers.append("already_analyzed")
        if min(len(cases), len(controls)) < 3:
            blockers.append("insufficient_case_control_samples")

        score = min(len(cases), len(controls), 20)
        score += {
            "primary_blood_replication": 8,
            "mechanistic_sorted_immune": 5,
            "mechanistic_msc": 3,
            "context_only_serum": 0,
            "context_only_non_mrna": -5,
            "other_context": 1,
        }[role]
        if explicit_axspa:
            score += 4
        if unknown_treatment:
            score -= 1
        if validation["independence_status"] == "shared_source_cluster":
            score -= 1
        passes = not blockers
        return {
            "accession": accession,
            "selection_score": score,
            "passes_hard_gates": passes,
            "selection_decision": (
                "eligible_for_selection" if passes else "not_selected_hard_gate"
            ),
            "hard_gate_reasons": "|".join(blockers),
            "evidence_role": role,
            "tissue_stratum": stratum,
            "suggested_cases": len(cases),
            "suggested_controls": len(controls),
            "treated_cases": treated_cases,
            "unknown_treatment_cases": unknown_treatment,
            "explicit_axspa_in_cases": explicit_axspa,
            "different_disease_in_cases": other_disease,
            "already_analyzed": already_analyzed,
            "evidence_cluster": validation["evidence_cluster"],
            "cluster_members": validation["cluster_members"],
            "title": catalog["title"],
            "automatic_eligibility": False,
            "next_action": (
                "manually_confirm_sheet_then_download"
                if passes
                else "retain_as_context_or_existing_evidence"
            ),
        }

    @staticmethod
    def _stratum(catalog: dict[str, str]) -> tuple[str, str]:
        text = f"{catalog['title']} {catalog['summary']}".lower()
        experiment = catalog["experiment_type"].lower()
        if "circ" in text or "non-coding rna" in experiment:
            return "non_coding_rna", "context_only_non_mrna"
        if "serum" in text:
            return "serum_rna", "context_only_serum"
        if "mesenchymal stem" in text or re.search(r"\bmsc", text):
            return "mesenchymal_stem_cells", "mechanistic_msc"
        if any(
            term in text
            for term in ("il-17-producing", "t cell", "macrophage", "monocyte")
        ):
            return "sorted_immune_cells", "mechanistic_sorted_immune"
        if "blood" in text or "pbmc" in text:
            return "peripheral_blood", "primary_blood_replication"
        return "other", "other_context"

    @staticmethod
    def _score(value: object) -> int:
        if not isinstance(value, int):
            raise TypeError("cohort selection score must be an integer")
        return value

    @staticmethod
    def _read(path: str | Path) -> list[dict[str, str]]:
        with Path(path).open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
