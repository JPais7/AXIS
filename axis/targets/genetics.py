"""Disease-specific human genetic support and modulation direction."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from axis.ingestion.geo import GeoApiError
from axis.targets.opentargets import API_URL, OpenTargetsClient


@dataclass(frozen=True)
class GeneticEvidenceRun:
    disease_id: str
    targets: int
    genetically_supported: int
    direction_resolved: int
    output_path: Path
    summary_path: Path


class GeneticEvidenceBuilder:
    """Build target-level genetic evidence without inventing direction."""

    def build(
        self,
        target_table: str | Path,
        *,
        disease_id: str = "MONDO_0005306",
        disease_name: str = "ankylosing spondylitis",
        output_root: str | Path = Path("data/targets/genetics"),
        refresh: bool = False,
        client: OpenTargetsClient | None = None,
    ) -> GeneticEvidenceRun:
        if not disease_id.strip() or not disease_name.strip():
            raise ValueError("disease identifier and name must not be empty")
        targets = self._read_targets(Path(target_table))
        destination = Path(output_root)
        cache = destination / "cache" / disease_id
        cache.mkdir(parents=True, exist_ok=True)
        owns_client = client is None
        api = client or OpenTargetsClient()
        rows: list[dict[str, object]] = []
        try:
            for gene, ensembl_id in targets:
                cache_path = cache / f"{gene}.json"
                if cache_path.exists() and not refresh:
                    payload = cast(
                        dict[str, object],
                        json.loads(cache_path.read_text(encoding="utf-8")),
                    )
                else:
                    evidences = api.genetic_evidence(ensembl_id, disease_id)
                    payload = {
                        "gene_symbol": gene,
                        "ensembl_id": ensembl_id,
                        "disease_id": disease_id,
                        "disease_name": disease_name,
                        "evidences": evidences,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "source_uri": API_URL,
                    }
                    canonical = json.dumps(payload, sort_keys=True).encode()
                    payload["response_checksum"] = (
                        "sha256:" + hashlib.sha256(canonical).hexdigest()
                    )
                    cache_path.write_text(
                        json.dumps(payload, indent=2) + "\n",
                        encoding="utf-8",
                    )
                rows.append(self._summarize(payload))
        finally:
            if owns_client:
                api.close()

        rows.sort(
            key=lambda row: (
                -cast(int, row["genetic_evidence_count"]),
                -cast(float, row["maximum_evidence_score"]),
                str(row["gene_symbol"]),
            )
        )
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "as-genetic-evidence.tsv"
        self._write(output_path, rows)
        supported = sum(cast(int, row["genetic_evidence_count"]) > 0 for row in rows)
        resolved = sum(
            row["therapeutic_direction"] not in {"unknown", "conflicting"}
            for row in rows
        )
        summary_path = destination / "as-genetic-evidence.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "disease_specific_genetic_evidence",
                    "source": "Open Targets Platform",
                    "source_uri": API_URL,
                    "created_at": datetime.now(UTC).isoformat(),
                    "disease_id": disease_id,
                    "disease_name": disease_name,
                    "targets": len(rows),
                    "genetically_supported_targets": supported,
                    "direction_resolved_targets": resolved,
                    "direction_policy": {
                        "GoF+risk": "inhibit",
                        "LoF+risk": "activate",
                        "GoF+protect": "activate",
                        "LoF+protect": "inhibit",
                        "missing_or_conflicting": "unknown",
                    },
                    "warning": (
                        "A target-disease genetic association does not prove "
                        "that pharmacological modulation will be effective or "
                        "safe. Missing direction remains unknown."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return GeneticEvidenceRun(
            disease_id=disease_id,
            targets=len(rows),
            genetically_supported=supported,
            direction_resolved=resolved,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _read_targets(path: Path) -> tuple[tuple[str, str], ...]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return tuple(
                    (row["gene_symbol"], row["ensembl_id"])
                    for row in csv.DictReader(source, delimiter="\t")
                    if row.get("resolved", "").lower() == "true"
                    and row.get("ensembl_id", "").strip()
                )
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read target table {path}: {error}") from error

    @staticmethod
    def _summarize(payload: dict[str, object]) -> dict[str, object]:
        collection = cast(dict[str, Any], payload["evidences"])
        evidences = cast(list[dict[str, Any]], collection.get("rows", []))
        sources = sorted({str(row["datasourceId"]) for row in evidences})
        directions = [
            GeneticEvidenceBuilder._direction(
                row.get("directionOnTarget"),
                row.get("directionOnTrait"),
            )
            for row in evidences
        ]
        known = {direction for direction in directions if direction != "unknown"}
        therapeutic_direction = (
            next(iter(known))
            if len(known) == 1
            else "conflicting"
            if len(known) > 1
            else "unknown"
        )
        return {
            "gene_symbol": payload["gene_symbol"],
            "ensembl_id": payload["ensembl_id"],
            "disease_id": payload["disease_id"],
            "genetic_evidence_count": int(collection.get("count", 0)),
            "returned_evidence_records": len(evidences),
            "maximum_evidence_score": max(
                (float(row["score"]) for row in evidences),
                default=0.0,
            ),
            "data_sources": "|".join(sources),
            "directional_records": sum(
                direction != "unknown" for direction in directions
            ),
            "therapeutic_direction": therapeutic_direction,
            "response_checksum": payload["response_checksum"],
        }

    @staticmethod
    def _direction(target: object, trait: object) -> str:
        target_value = str(target or "").strip().lower()
        trait_value = str(trait or "").strip().lower()
        gain = target_value in {"gof", "gain_of_function", "increase"}
        loss = target_value in {"lof", "loss_of_function", "decrease"}
        risk = trait_value in {"risk", "increase", "increased_risk"}
        protect = trait_value in {
            "protect",
            "protection",
            "decrease",
            "decreased_risk",
        }
        if (gain and risk) or (loss and protect):
            return "inhibit"
        if (loss and risk) or (gain and protect):
            return "activate"
        return "unknown"

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = (
            "gene_symbol",
            "ensembl_id",
            "disease_id",
            "genetic_evidence_count",
            "returned_evidence_records",
            "maximum_evidence_score",
            "data_sources",
            "directional_records",
            "therapeutic_direction",
            "response_checksum",
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
