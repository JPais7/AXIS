"""Auditable exploratory shortlist from direction-concordance results."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class ExploratoryShortlist:
    source_path: Path
    output_path: Path
    summary_path: Path
    candidates: int


class ShortlistBuilder:
    """Apply declared filters without converting exploration into evidence."""

    def build(
        self,
        concordance_path: str | Path,
        *,
        output_root: str | Path | None = None,
        minimum_nominal_studies: int = 2,
        maximum_combined_fdr: float = 0.05,
        minimum_effect_percentile: float = 0.8,
    ) -> ExploratoryShortlist:
        source_path = Path(concordance_path)
        if not source_path.exists():
            raise GeoApiError(f"direction-concordance file not found: {source_path}")
        if minimum_nominal_studies < 0:
            raise ValueError("minimum nominal studies must not be negative")
        if not 0.0 < maximum_combined_fdr < 1.0:
            raise ValueError("maximum combined FDR must be between 0 and 1")
        if not 0.0 <= minimum_effect_percentile <= 1.0:
            raise ValueError("minimum effect percentile must be between 0 and 1")
        method_path = source_path.with_name("direction-concordance-analysis.json")
        if not method_path.exists():
            raise GeoApiError(f"concordance method file not found: {method_path}")
        method = json.loads(method_path.read_text(encoding="utf-8"))
        if method.get("analysis_role") != "exploratory_direction_concordance":
            raise GeoApiError("source is not an AXIS direction analysis")
        studies = tuple(str(value) for value in method.get("studies", ()))
        if minimum_nominal_studies > len(studies):
            raise ValueError("minimum nominal studies exceeds the number of studies")

        rows = self._read_rows(source_path)
        selected = [
            row
            for row in rows
            if row.get("direction_concordant", "").lower() == "true"
            and int(row["nominal_supporting_studies"]) >= minimum_nominal_studies
            and float(row["combined_adjusted_p_value"]) <= maximum_combined_fdr
            and float(row["mean_absolute_effect_percentile"])
            >= minimum_effect_percentile
        ]
        selected.sort(
            key=lambda row: (
                -float(row["mean_absolute_effect_percentile"]),
                float(row["combined_adjusted_p_value"]),
                row["gene_symbol"],
            )
        )
        for rank, row in enumerate(selected, start=1):
            row["shortlist_rank"] = str(rank)
            row["selection_status"] = "exploratory_candidate"

        destination = (
            Path(output_root) if output_root is not None else source_path.parent
        )
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "exploratory-shortlist.tsv"
        self._write_rows(output_path, selected)
        checksum = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
        summary_path = destination / "exploratory-shortlist.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "exploratory_shortlist",
                    "publication_eligible": False,
                    "created_at": datetime.now(UTC).isoformat(),
                    "source_path": str(source_path),
                    "source_checksum": checksum,
                    "studies": studies,
                    "criteria": {
                        "direction_concordant": True,
                        "minimum_nominal_supporting_studies": (minimum_nominal_studies),
                        "maximum_combined_adjusted_p_value": (maximum_combined_fdr),
                        "minimum_mean_absolute_effect_percentile": (
                            minimum_effect_percentile
                        ),
                    },
                    "candidates": len(selected),
                    "warning": (
                        "Hypothesis-generation list only. Selection from the "
                        "same studies is not independent validation and cannot "
                        "be published as a primary AXIS claim."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ExploratoryShortlist(
            source_path=source_path,
            output_path=output_path,
            summary_path=summary_path,
            candidates=len(selected),
        )

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return list(csv.DictReader(source, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(
                f"cannot read direction concordance {path}: {error}"
            ) from error

    @staticmethod
    def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
        source_fields = (
            "gene_symbol",
            "available_studies",
            "direction",
            "direction_concordant",
            "nominal_supporting_studies",
            "study_directions",
            "study_effects",
            "mean_absolute_effect_percentile",
            "combined_p_value",
            "combined_adjusted_p_value",
        )
        fields = ("shortlist_rank", "selection_status", *source_fields)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
