"""External validation of a frozen exploratory shortlist."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.eligibility import verify_study_eligibility
from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class ExternalValidation:
    accession: str
    candidates: int
    matched_candidates: int
    direction_validated: int
    nominally_validated: int
    output_path: Path
    summary_path: Path


class ExternalValidator:
    """Test a checksum-frozen candidate list in an independent study."""

    def validate(
        self,
        shortlist_path: str | Path,
        validation_accession: str,
        *,
        data_root: str | Path = Path("data/geo"),
        output_root: str | Path = Path("data/analysis/external-validation"),
        nominal_alpha: float = 0.05,
    ) -> ExternalValidation:
        shortlist_path = Path(shortlist_path)
        accession = validation_accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if not 0.0 < nominal_alpha < 1.0:
            raise ValueError("nominal alpha must be between 0 and 1")
        audit_path = shortlist_path.with_suffix(".json")
        if not shortlist_path.exists() or not audit_path.exists():
            raise GeoApiError("shortlist TSV and audit JSON are required")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("analysis_role") != "exploratory_shortlist":
            raise GeoApiError("source is not an AXIS exploratory shortlist")
        discovery_studies = tuple(str(value) for value in audit.get("studies", ()))
        if accession in discovery_studies:
            raise GeoApiError(
                f"{accession} was used for discovery and is not independent"
            )
        expected_checksum = audit.get("source_checksum")
        source_path = Path(str(audit.get("source_path", "")))
        if not source_path.is_absolute():
            candidate = shortlist_path.parent / source_path.name
            if candidate.exists():
                source_path = candidate
        actual_checksum = (
            "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
            if source_path.exists()
            else ""
        )
        if expected_checksum != actual_checksum:
            raise GeoApiError("shortlist source concordance is missing or has changed")

        gene_paths = tuple(
            sorted(
                (Path(data_root) / accession / "prepared").glob(
                    "*/gene-level-results.tsv"
                )
            )
        )
        if len(gene_paths) != 1:
            raise GeoApiError(
                f"external validation requires one analyzed matrix for {accession}"
            )
        eligibility = verify_study_eligibility(
            gene_paths[0],
            required_role="external_validation",
        )
        validation = self._gene_results(gene_paths[0])
        shortlist = self._read_rows(shortlist_path)
        discovery = {
            row["gene_symbol"]: row
            for row in self._read_rows(source_path)
            if row["direction_concordant"].lower() == "true"
        }
        candidate_genes = {row["gene_symbol"] for row in shortlist}
        records: list[dict[str, object]] = []
        for row in shortlist:
            gene = row["gene_symbol"]
            result = validation.get(gene)
            if result is None:
                records.append(self._missing_record(row))
                continue
            expected_direction = row["direction"]
            observed_direction = self._direction(result["effect"])
            agrees = expected_direction == observed_direction
            nominal = agrees and result["p_value"] <= nominal_alpha
            records.append(
                {
                    "shortlist_rank": row["shortlist_rank"],
                    "gene_symbol": gene,
                    "discovery_direction": expected_direction,
                    "validation_direction": observed_direction,
                    "direction_agrees": agrees,
                    "validation_effect": result["effect"],
                    "validation_p_value": result["p_value"],
                    "validation_adjusted_p_value": result["adjusted_p_value"],
                    "nominally_validated": nominal,
                    "validation_status": (
                        "nominal_directional_support"
                        if nominal
                        else "direction_only"
                        if agrees
                        else "opposite_direction"
                    ),
                }
            )
        matched = [row for row in records if row["validation_status"] != "missing"]
        direction_validated = sum(bool(row["direction_agrees"]) for row in matched)
        nominally_validated = sum(bool(row["nominally_validated"]) for row in matched)
        background = [
            (gene, row, validation[gene])
            for gene, row in discovery.items()
            if gene not in candidate_genes and gene in validation
        ]
        background_direction = sum(
            row["direction"] == self._direction(result["effect"])
            for _, row, result in background
        )
        background_nominal = sum(
            row["direction"] == self._direction(result["effect"])
            and result["p_value"] <= nominal_alpha
            for _, row, result in background
        )
        direction_test = self._enrichment(
            direction_validated,
            len(matched),
            background_direction,
            len(background),
        )
        nominal_test = self._enrichment(
            nominally_validated,
            len(matched),
            background_nominal,
            len(background),
        )

        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / f"{accession}-candidate-validation.tsv"
        self._write(output_path, records)
        summary_path = destination / f"{accession}-validation.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "independent_external_validation",
                    "publication_eligible": False,
                    "created_at": datetime.now(UTC).isoformat(),
                    "validation_accession": accession,
                    "validation_eligibility": eligibility,
                    "discovery_studies": discovery_studies,
                    "shortlist_path": str(shortlist_path),
                    "shortlist_checksum": (
                        "sha256:"
                        + hashlib.sha256(shortlist_path.read_bytes()).hexdigest()
                    ),
                    "nominal_alpha": nominal_alpha,
                    "candidates": len(shortlist),
                    "matched_candidates": len(matched),
                    "direction_validated": direction_validated,
                    "nominally_validated": nominally_validated,
                    "background_genes": len(background),
                    "direction_enrichment": direction_test,
                    "nominal_directional_enrichment": nominal_test,
                    "warning": (
                        "Exploratory external validation in a small normalized "
                        "RNA-seq cohort; no primary claim is created."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ExternalValidation(
            accession=accession,
            candidates=len(shortlist),
            matched_candidates=len(matched),
            direction_validated=direction_validated,
            nominally_validated=nominally_validated,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _gene_results(path: Path) -> dict[str, dict[str, float]]:
        return {
            row["gene_symbol"]: {
                "effect": float(row["median_mean_difference"]),
                "p_value": float(row["simes_p_value"]),
                "adjusted_p_value": float(row["adjusted_p_value"]),
            }
            for row in ExternalValidator._read_rows(path)
        }

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return list(csv.DictReader(source, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(
                f"cannot read validation input {path}: {error}"
            ) from error

    @staticmethod
    def _direction(effect: float) -> str:
        return (
            "higher_in_case"
            if effect > 0
            else "lower_in_case"
            if effect < 0
            else "unchanged"
        )

    @staticmethod
    def _missing_record(row: dict[str, str]) -> dict[str, object]:
        return {
            "shortlist_rank": row["shortlist_rank"],
            "gene_symbol": row["gene_symbol"],
            "discovery_direction": row["direction"],
            "validation_direction": "",
            "direction_agrees": False,
            "validation_effect": "",
            "validation_p_value": "",
            "validation_adjusted_p_value": "",
            "nominally_validated": False,
            "validation_status": "missing",
        }

    @staticmethod
    def _enrichment(
        supported: int,
        total: int,
        background_supported: int,
        background_total: int,
    ) -> dict[str, float | int]:
        table = (
            (supported, total - supported),
            (
                background_supported,
                background_total - background_supported,
            ),
        )
        test = stats.fisher_exact(table, alternative="greater")
        return {
            "candidate_supported": supported,
            "candidate_total": total,
            "background_supported": background_supported,
            "background_total": background_total,
            "odds_ratio": float(test.statistic),
            "p_value": float(test.pvalue),
        }

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = (
            "shortlist_rank",
            "gene_symbol",
            "discovery_direction",
            "validation_direction",
            "direction_agrees",
            "validation_effect",
            "validation_p_value",
            "validation_adjusted_p_value",
            "nominally_validated",
            "validation_status",
        )
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
