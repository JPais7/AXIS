"""Focused query plans for the Human Cell Epigenome/4D Nucleome Atlas."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from axis.ingestion.geo import GeoApiError

ENSEMBL_REST = "https://rest.ensembl.org"
ATLAS_BROWSER = "https://humancellepigenomeatlas.arcinstitute.org"
CONTACT_REPOSITORY = (
    "https://huggingface.co/datasets/zhoujt1994/"
    "HumanCellEpigenomeAtlas_sc_contact/tree/main"
)
PUBLISHED_PBMC_DONORS = ("PBMC_11714", "PBMC_4809")
VARIANT_PATTERN = re.compile(
    r"^(?:chr)?(?P<chromosome>[0-9XYM]+)[_:]"
    r"(?P<position>[0-9]+)(?:[_:][A-Z]+[_:][A-Z]+)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NucleomePlanRun:
    targets: int
    loci: int
    output_path: Path
    regions_path: Path
    summary_path: Path


class EnsemblClient:
    """Minimal GRCh38 coordinate lookup with injectable HTTP transport."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = ENSEMBL_REST,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "AXIS/0.1 nucleome-plan",
            },
        )
        self._owns_client = client is None
        self.endpoint = endpoint.rstrip("/")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def lookup(self, ensembl_id: str) -> dict[str, object]:
        try:
            response = self._client.get(
                f"{self.endpoint}/lookup/id/{ensembl_id}",
                params={"content-type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GeoApiError(f"Ensembl coordinate lookup failed: {error}") from error
        if not isinstance(payload, dict):
            raise GeoApiError("Ensembl coordinate response is not an object")
        return cast(dict[str, object], payload)


class NucleomePlanBuilder:
    """Create small GRCh38 locus queries instead of downloading raw atlas data."""

    def build(
        self,
        context_path: str | Path,
        *,
        output_root: str | Path = Path("data/targets/nucleome"),
        variant_flank: int = 250_000,
        promoter_flank: int = 5_000,
        refresh: bool = False,
        client: EnsemblClient | None = None,
    ) -> NucleomePlanRun:
        if variant_flank < 1 or promoter_flank < 1:
            raise ValueError("query flanks must be positive")
        targets = self._read_context(Path(context_path))
        destination = Path(output_root)
        cache = destination / "cache" / "ensembl"
        cache.mkdir(parents=True, exist_ok=True)
        owns_client = client is None
        api = client or EnsemblClient()
        rows: list[dict[str, object]] = []
        try:
            for target in targets:
                location = self._location(
                    target["ensembl_id"],
                    cache=cache,
                    refresh=refresh,
                    client=api,
                )
                for variant in target["variants"]:
                    parsed = self._parse_variant(variant)
                    if parsed is None:
                        continue
                    chromosome, position = parsed
                    rows.append(
                        self._plan_row(
                            target=target,
                            variant=variant,
                            chromosome=chromosome,
                            position=position,
                            location=location,
                            variant_flank=variant_flank,
                            promoter_flank=promoter_flank,
                        )
                    )
        finally:
            if owns_client:
                api.close()
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "atlas-query-plan.tsv"
        self._write(output_path, rows)
        regions_path = destination / "atlas-query-regions.bed"
        self._write_bed(regions_path, rows)
        summary_path = destination / "atlas-query-plan.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "reference_4d_nucleome_query_plan",
                    "created_at": datetime.now(UTC).isoformat(),
                    "genome_assembly": "GRCh38",
                    "targets": len({str(row["gene_symbol"]) for row in rows}),
                    "loci": len(rows),
                    "atlas_browser": ATLAS_BROWSER,
                    "contact_repository": CONTACT_REPOSITORY,
                    "recommended_donors": list(PUBLISHED_PBMC_DONORS),
                    "recommended_cell_scope": (
                        "blood immune major types and subtypes, beginning with "
                        "memory T cells"
                    ),
                    "interpretation": (
                        "A variant-promoter contact in this healthy reference "
                        "supports a cell-context mechanism but is not "
                        "disease-specific evidence or therapeutic direction."
                    ),
                    "compute_policy": (
                        "query processed pseudobulk/cell-type contact maps only; "
                        "do not download or reconstruct all single-cell contacts"
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return NucleomePlanRun(
            targets=len({str(row["gene_symbol"]) for row in rows}),
            loci=len(rows),
            output_path=output_path,
            regions_path=regions_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _read_context(path: Path) -> tuple[dict[str, Any], ...]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                rows = tuple(csv.DictReader(source, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(f"cannot read causal context {path}: {error}") from error
        result: list[dict[str, Any]] = []
        for row in rows:
            variants = tuple(
                value.strip()
                for value in row.get("lead_variants", "").split("|")
                if value.strip()
            )
            if variants:
                result.append(
                    {
                        "gene_symbol": row["gene_symbol"],
                        "ensembl_id": row["ensembl_id"],
                        "l2g_score": float(
                            row.get("maximum_locus_to_gene_score") or 0.0
                        ),
                        "variants": variants,
                    }
                )
        return tuple(result)

    @staticmethod
    def _location(
        ensembl_id: str,
        *,
        cache: Path,
        refresh: bool,
        client: EnsemblClient,
    ) -> dict[str, object]:
        path = cache / f"{ensembl_id}.json"
        if path.exists() and not refresh:
            return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        payload = client.lookup(ensembl_id)
        canonical = json.dumps(payload, sort_keys=True).encode()
        record = {
            **payload,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source_uri": f"{client.endpoint}/lookup/id/{ensembl_id}",
            "response_checksum": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        }
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record

    @staticmethod
    def _parse_variant(value: str) -> tuple[str, int] | None:
        match = VARIANT_PATTERN.match(value)
        if match is None:
            return None
        chromosome = match.group("chromosome").upper()
        if chromosome == "M":
            chromosome = "MT"
        return chromosome, int(match.group("position"))

    @staticmethod
    def _plan_row(
        *,
        target: dict[str, Any],
        variant: str,
        chromosome: str,
        position: int,
        location: dict[str, object],
        variant_flank: int,
        promoter_flank: int,
    ) -> dict[str, object]:
        gene_chromosome = str(location["seq_region_name"]).removeprefix("chr")
        strand = int(str(location["strand"]))
        transcription_start = (
            int(str(location["start"]))
            if strand == 1
            else int(str(location["end"]))
        )
        same_chromosome = chromosome == gene_chromosome
        return {
            "gene_symbol": target["gene_symbol"],
            "ensembl_id": target["ensembl_id"],
            "lead_variant": variant,
            "locus_to_gene_score": target["l2g_score"],
            "genome_assembly": str(location.get("assembly_name") or "GRCh38"),
            "variant_chromosome": f"chr{chromosome}",
            "variant_position_1based": position,
            "variant_window_start_0based": max(0, position - variant_flank - 1),
            "variant_window_end_0based": position + variant_flank,
            "gene_chromosome": f"chr{gene_chromosome}",
            "gene_strand": strand,
            "transcription_start_1based": transcription_start,
            "promoter_start_0based": max(0, transcription_start - promoter_flank - 1),
            "promoter_end_0based": transcription_start + promoter_flank,
            "same_chromosome": same_chromosome,
            "atlas_tissue": "peripheral blood",
            "atlas_donors": "|".join(PUBLISHED_PBMC_DONORS),
            "priority_cell_context": "Hema Tmem|other blood immune subtypes",
            "query_status": (
                "ready_for_processed_contact_query"
                if same_chromosome
                else "coordinate_mismatch_review"
            ),
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

    @staticmethod
    def _write_bed(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as output:
            for row in rows:
                output.write(
                    f"{row['variant_chromosome']}\t"
                    f"{row['variant_window_start_0based']}\t"
                    f"{row['variant_window_end_0based']}\t"
                    f"{row['gene_symbol']}:{row['lead_variant']}:variant\n"
                )
                output.write(
                    f"{row['gene_chromosome']}\t"
                    f"{row['promoter_start_0based']}\t"
                    f"{row['promoter_end_0based']}\t"
                    f"{row['gene_symbol']}:{row['lead_variant']}:promoter\n"
                )
