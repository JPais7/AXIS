"""Selective single-cell contact scan for planned 4D Nucleome loci."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

import httpx

from axis.ingestion.geo import GeoApiError

HF_ROOT = "https://huggingface.co/datasets/zhoujt1994"
METADATA_URL = (
    f"{HF_ROOT}/HumanCellEpigenomeAtlas_metadata/resolve/main/"
    "5kCG100k3C_summary.csv.gz?download=true"
)
CONTACT_ROOT = f"{HF_ROOT}/HumanCellEpigenomeAtlas_sc_contact/resolve/main"
DEFAULT_SUBTYPES = ("c1-b8", "c1-b12")


@dataclass(frozen=True)
class NucleomeContactRun:
    targets: int
    downloaded_cells: int
    targets_with_observed_contacts: int
    output_path: Path
    cell_manifest_path: Path
    summary_path: Path


class AtlasDownloadClient:
    """Stream small selected atlas files into a reusable local cache."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=120.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 nucleome-contacts"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def download(self, url: str, path: Path) -> str:
        if path.exists():
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        digest = hashlib.sha256()
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    self._copy(response, output, digest)
            temporary.replace(path)
        except (httpx.HTTPError, OSError) as error:
            temporary.unlink(missing_ok=True)
            raise GeoApiError(f"atlas download failed for {url}: {error}") from error
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _copy(
        response: httpx.Response, output: BinaryIO, digest: hashlib._Hash
    ) -> None:
        for chunk in response.iter_bytes():
            output.write(chunk)
            digest.update(chunk)


class NucleomeContactBuilder:
    """Sample annotated blood cells and scan only target contact anchors."""

    def build(
        self,
        plan_path: str | Path,
        *,
        output_root: str | Path = Path("data/targets/nucleome"),
        cells_per_subtype_donor: int = 3,
        anchor_radius: int = 25_000,
        subtypes: tuple[str, ...] = DEFAULT_SUBTYPES,
        client: AtlasDownloadClient | None = None,
    ) -> NucleomeContactRun:
        if cells_per_subtype_donor < 1 or anchor_radius < 1:
            raise ValueError("cell count and anchor radius must be positive")
        plan = self._read_plan(Path(plan_path))
        destination = Path(output_root)
        cache = destination / "cache" / "atlas"
        owns_client = client is None
        api = client or AtlasDownloadClient()
        try:
            metadata_path = cache / "5kCG100k3C_summary.csv.gz"
            metadata_checksum = api.download(METADATA_URL, metadata_path)
            cells = self._select_cells(
                metadata_path,
                subtypes=subtypes,
                per_group=cells_per_subtype_donor,
            )
            observations: dict[tuple[str, str, str], dict[str, object]] = {}
            manifest: list[dict[str, object]] = []
            for cell in cells:
                path = (
                    cache
                    / "contacts"
                    / cell["donor"]
                    / (cell["cell"] + ".3C.contact.rmbkl.tsv.gz")
                )
                url = (
                    f"{CONTACT_ROOT}/PBMC_{cell['donor']}/"
                    f"{cell['cell']}.3C.contact.rmbkl.tsv.gz?download=true"
                )
                checksum = api.download(url, path)
                contacts = self._scan(path, plan, anchor_radius=anchor_radius)
                manifest.append(
                    {
                        **cell,
                        "source_url": url,
                        "cache_path": str(path),
                        "response_checksum": checksum,
                        "matched_contacts": sum(contacts.values()),
                    }
                )
                for locus in plan:
                    key = (
                        str(locus["gene_symbol"]),
                        cell["subtype"],
                        cell["donor"],
                    )
                    summary = observations.setdefault(
                        key,
                        {
                            "gene_symbol": locus["gene_symbol"],
                            "lead_variant": locus["lead_variant"],
                            "cell_subtype_code": cell["subtype"],
                            "cell_subtype": cell["subtype_label"],
                            "donor": cell["donor"],
                            "sampled_cells": 0,
                            "cells_with_observed_contact": 0,
                            "observed_contacts": 0,
                        },
                    )
                    summary["sampled_cells"] = cast(int, summary["sampled_cells"]) + 1
                    count = contacts.get(str(locus["gene_symbol"]), 0)
                    summary["observed_contacts"] = (
                        cast(int, summary["observed_contacts"]) + count
                    )
                    if count:
                        summary["cells_with_observed_contact"] = (
                            cast(int, summary["cells_with_observed_contact"]) + 1
                        )
        finally:
            if owns_client:
                api.close()
        rows = []
        for summary in observations.values():
            observed = cast(int, summary["observed_contacts"]) > 0
            rows.append(
                {
                    **summary,
                    "contact_status": (
                        "observed_in_sample"
                        if observed
                        else "not_observed_in_sparse_sample"
                    ),
                }
            )
        rows.sort(
            key=lambda row: (
                str(row["gene_symbol"]),
                str(row["cell_subtype_code"]),
                str(row["donor"]),
            )
        )
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "atlas-contact-evidence.tsv"
        self._write(output_path, rows)
        manifest_path = destination / "atlas-contact-cells.tsv"
        self._write(manifest_path, manifest)
        observed_targets = {
            str(row["gene_symbol"])
            for row in rows
            if cast(int, row["observed_contacts"]) > 0
        }
        summary_path = destination / "atlas-contact-evidence.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "reference_single_cell_3d_contact_scan",
                    "created_at": datetime.now(UTC).isoformat(),
                    "genome_assembly": "GRCh38",
                    "targets": len({str(row["gene_symbol"]) for row in plan}),
                    "downloaded_cells": len(cells),
                    "subtypes": list(subtypes),
                    "cells_per_subtype_donor": cells_per_subtype_donor,
                    "anchor_radius": anchor_radius,
                    "targets_with_observed_contacts": len(observed_targets),
                    "metadata_checksum": metadata_checksum,
                    "sampling_policy": (
                        "highest CisLongContact cells per subtype and donor; "
                        "deterministic tie-break by cell identifier"
                    ),
                    "absence_policy": (
                        "zero matches means not observed in this sparse sample, "
                        "not biological absence"
                    ),
                    "warning": (
                        "Contacts are from healthy reference PBMCs and do not "
                        "establish disease causality, effect direction or "
                        "therapeutic actionability."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return NucleomeContactRun(
            targets=len({str(row["gene_symbol"]) for row in plan}),
            downloaded_cells=len(cells),
            targets_with_observed_contacts=len(observed_targets),
            output_path=output_path,
            cell_manifest_path=manifest_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _read_plan(path: Path) -> tuple[dict[str, object], ...]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                rows = tuple(csv.DictReader(source, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise GeoApiError(f"cannot read nucleome plan {path}: {error}") from error
        return tuple(
            {
                "gene_symbol": row["gene_symbol"],
                "lead_variant": row["lead_variant"],
                "chromosome": row["variant_chromosome"],
                "variant_position": int(row["variant_position_1based"]),
                "transcription_start": int(row["transcription_start_1based"]),
            }
            for row in rows
            if row.get("query_status") == "ready_for_processed_contact_query"
        )

    @staticmethod
    def _select_cells(
        path: Path, *, subtypes: tuple[str, ...], per_group: int
    ) -> list[dict[str, str]]:
        labels = {
            "c1-b8": "Hema Tmem Central CD4 Blood",
            "c1-b12": "Hema Tmem Effector CD8 Blood",
        }
        groups: dict[tuple[str, str], list[dict[str, str]]] = {}
        try:
            with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    if (
                        row.get("Tissue") != "PBMC"
                        or row.get("subtype") not in subtypes
                    ):
                        continue
                    donor = row["Donor"]
                    if donor not in {"11714", "4809"}:
                        continue
                    cell = {
                        "cell": row["cell"],
                        "donor": donor,
                        "subtype": row["subtype"],
                        "subtype_label": labels.get(row["subtype"], row["subtype"]),
                        "cis_long_contacts_qc": row["CisLongContact"],
                    }
                    groups.setdefault((donor, row["subtype"]), []).append(cell)
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read atlas metadata {path}: {error}") from error
        selected: list[dict[str, str]] = []
        for group in groups.values():
            group.sort(
                key=lambda row: (
                    -int(row["cis_long_contacts_qc"]),
                    row["cell"],
                )
            )
            selected.extend(group[:per_group])
        selected.sort(key=lambda row: (row["donor"], row["subtype"], row["cell"]))
        return selected

    @staticmethod
    def _scan(
        path: Path,
        plan: tuple[dict[str, object], ...],
        *,
        anchor_radius: int,
    ) -> dict[str, int]:
        matches: dict[str, int] = {}
        by_chromosome: dict[str, list[dict[str, object]]] = {}
        for locus in plan:
            by_chromosome.setdefault(str(locus["chromosome"]), []).append(locus)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as source:
                for line in source:
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 7 or fields[1] != fields[5]:
                        continue
                    loci = by_chromosome.get(fields[1], ())
                    if not loci:
                        continue
                    left, right = int(fields[2]), int(fields[6])
                    for locus in loci:
                        variant = cast(int, locus["variant_position"])
                        promoter = cast(int, locus["transcription_start"])
                        direct = (
                            abs(left - variant) <= anchor_radius
                            and abs(right - promoter) <= anchor_radius
                        )
                        reverse = (
                            abs(right - variant) <= anchor_radius
                            and abs(left - promoter) <= anchor_radius
                        )
                        if direct or reverse:
                            gene = str(locus["gene_symbol"])
                            matches[gene] = matches.get(gene, 0) + 1
        except (OSError, UnicodeError, ValueError) as error:
            raise GeoApiError(f"cannot scan atlas contacts {path}: {error}") from error
        return matches

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
