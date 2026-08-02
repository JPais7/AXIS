"""Resource-conscious expansion of target validation across eligible PBMC types."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.analysis.single_cell_pseudobulk import SingleCellPseudobulkAnalyzer


@dataclass(frozen=True)
class SingleCellReferenceExpansionRun:
    cell_types: int
    targets: int
    comparisons: int
    results_path: Path
    summary_path: Path


class SingleCellReferenceExpander:
    """Validate DDX24 and ADA without loading the full matrix into memory."""

    TARGETS = ("DDX24", "ADA")

    def expand(
        self,
        *,
        archive_path: str | Path,
        metadata_path: str | Path,
        cell_type_design_path: str | Path,
        output_root: str | Path = Path(
            "data/single-cell/GSE194315/reference-expansion"
        ),
    ) -> SingleCellReferenceExpansionRun:
        cell_types = self._eligible_cell_types(Path(cell_type_design_path))
        if len(cell_types) < 5:
            raise ValueError(
                "too few eligible GSE194315 cell types for reference expansion"
            )
        destination = Path(output_root)
        targeted = destination / "pseudobulk"
        result = SingleCellPseudobulkAnalyzer().analyze(
            archive_path,
            metadata_path,
            target_genes=self.TARGETS,
            cell_types=cell_types,
            case_status="AXI",
            control_status="Healthy",
            minimum_cells=20,
            output_root=targeted,
        )
        results_path = destination / "target-cell-type-validation.tsv"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_bytes(result.output_path.read_bytes())
        summary_path = destination / "reference-expansion.json"
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE194315",
                    "analysis_role": (
                        "independent_case_control_cell_type_localisation"
                    ),
                    "case_subjects": 10,
                    "control_subjects": 29,
                    "statistical_unit": "subject",
                    "targets": list(self.TARGETS),
                    "eligible_cell_types": list(cell_types),
                    "cell_type_count": len(cell_types),
                    "comparisons": result.comparisons,
                    "compute_strategy": (
                        "single_pass_streaming_of_10x_archive_for_two_targets"
                    ),
                    "memory_strategy": (
                        "retain_only_selected_gene_counts_aggregated_by_subject"
                    ),
                    "limitations": [
                        (
                            "PBMCs cannot provide a complete whole-blood "
                            "reference for granulocytes and platelets."
                        ),
                        (
                            "Welch tests do not adjust clinical covariates; "
                            "results remain external validation."
                        ),
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SingleCellReferenceExpansionRun(
            cell_types=len(cell_types),
            targets=len(self.TARGETS),
            comparisons=result.comparisons,
            results_path=results_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _eligible_cell_types(path: Path) -> tuple[str, ...]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = csv.DictReader(source, delimiter="\t")
            return tuple(
                row["cell_type"]
                for row in rows
                if row["eligible_for_pseudobulk"].lower() == "true"
            )
