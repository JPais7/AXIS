"""Targeted, donor-level external validation in GSE288581."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.single_cell_pseudobulk import SingleCellPseudobulkAnalyzer
from axis.ingestion.geo import GeoApiError


@dataclass(frozen=True)
class Gse288581ValidationRun:
    donors: int
    targets: int
    downloaded_files: int
    results_path: Path
    sensitivity_path: Path
    manifest_path: Path
    summary_path: Path


class Gse288581Validator:
    """Download only blood GEX matrices and test donors, never cells."""

    TARGETS = ("DDX24", "ADA")

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=120.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 GSE288581 validation"},
        )
        self._owns_client = http_client is None

    def __enter__(self) -> Gse288581Validator:
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_client:
            self._client.close()

    def validate(
        self,
        *,
        series_matrix_path: str | Path,
        output_root: str | Path = Path(
            "data/analysis/single-cell-validation/GSE288581"
        ),
    ) -> Gse288581ValidationRun:
        samples = self._selected_samples(Path(series_matrix_path))
        if len(samples) != 8:
            raise ValueError("expected four AS and four healthy blood GEX donors")
        destination = Path(output_root)
        files_root = destination / "processed"
        files_root.mkdir(parents=True, exist_ok=True)
        manifest_rows: list[dict[str, object]] = []
        donor_rows: list[dict[str, object]] = []
        downloads = 0
        for sample in samples:
            local: dict[str, Path] = {}
            for kind in ("features", "matrix"):
                uri = str(sample[kind])
                path = files_root / uri.rsplit("/", 1)[-1]
                downloaded = self._download(uri, path)
                downloads += int(downloaded)
                local[kind] = path
                manifest_rows.append(
                    {
                        "library_id": sample["library_id"],
                        "donor_id": sample["donor_id"],
                        "group": sample["group"],
                        "kind": kind,
                        "source_uri": uri,
                        "local_path": str(path),
                        "size_bytes": path.stat().st_size,
                        "sha256": self._checksum(path),
                    }
                )
            donor_rows.extend(
                self._donor_targets(
                    donor_id=str(sample["donor_id"]),
                    group=str(sample["group"]),
                    features_path=local["features"],
                    matrix_path=local["matrix"],
                )
            )
        results = self._results(donor_rows)
        sensitivity = self._sensitivity(donor_rows, results)
        manifest_path = destination / "download-manifest.tsv"
        donor_path = destination / "donor-pseudobulk.tsv"
        results_path = destination / "target-validation.tsv"
        sensitivity_path = destination / "leave-one-donor-out.tsv"
        summary_path = destination / "validation-summary.json"
        self._write(manifest_path, manifest_rows)
        self._write(donor_path, donor_rows)
        self._write(results_path, results)
        self._write(sensitivity_path, sensitivity)
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE288581",
                    "analysis_role": "independent_targeted_CD8_memory_validation",
                    "case_donors": 4,
                    "control_donors": 4,
                    "cell_scope": "FACS_sorted_CD45RO_positive_CD8_T_cells",
                    "statistical_unit": "donor",
                    "targets": list(self.TARGETS),
                    "method": "Welch test on donor log2(CPM + 0.5)",
                    "multiple_testing": "BH across two predeclared targets",
                    "download_policy": (
                        "only peripheral-blood GEX feature and matrix files"
                    ),
                    "warning": (
                        "Small external cohort; report effect and leave-one-donor-"
                        "out stability rather than treating non-significance as "
                        "absence."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Gse288581ValidationRun(
            donors=8,
            targets=2,
            downloaded_files=downloads,
            results_path=results_path,
            sensitivity_path=sensitivity_path,
            manifest_path=manifest_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _selected_samples(path: Path) -> list[dict[str, object]]:
        metadata: dict[str, list[str]] = {}
        with gzip.open(path, "rt", encoding="utf-8", newline="") as matrix_file:
            for row in csv.reader(matrix_file, delimiter="\t"):
                if row and (
                    row[0]
                    in {
                        "!Sample_title",
                        "!Sample_geo_accession",
                        "!Sample_source_name_ch1",
                        "!Sample_supplementary_file_2",
                        "!Sample_supplementary_file_3",
                    }
                ):
                    metadata[row[0]] = row[1:]
        rows: list[dict[str, object]] = []
        for library, title, tissue, features, matrix in zip(
            metadata["!Sample_geo_accession"],
            metadata["!Sample_title"],
            metadata["!Sample_source_name_ch1"],
            metadata["!Sample_supplementary_file_2"],
            metadata["!Sample_supplementary_file_3"],
            strict=True,
        ):
            if tissue != "Peripheral Blood" or "_GEX" not in title:
                continue
            healthy = title.startswith("HC")
            donor = title.split("_", 1)[0].removeprefix("PB").removeprefix("HC")
            rows.append(
                {
                    "library_id": library,
                    "donor_id": ("HC" if healthy else "AS") + donor,
                    "group": "Healthy" if healthy else "AXI",
                    "features": features.replace("ftp://", "https://"),
                    "matrix": matrix.replace("ftp://", "https://"),
                }
            )
        return rows

    def _download(self, uri: str, path: Path) -> bool:
        if path.exists() and path.stat().st_size > 0:
            return False
        try:
            with self._client.stream("GET", uri) as response:
                response.raise_for_status()
                with path.open("wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        target.write(chunk)
        except (httpx.HTTPError, OSError) as error:
            path.unlink(missing_ok=True)
            raise GeoApiError(f"failed to download {uri}: {error}") from error
        return True

    @classmethod
    def _donor_targets(
        cls,
        *,
        donor_id: str,
        group: str,
        features_path: Path,
        matrix_path: Path,
    ) -> list[dict[str, object]]:
        indices: dict[int, str] = {}
        with gzip.open(features_path, "rt", encoding="utf-8") as source:
            for index, line in enumerate(source, 1):
                fields = line.rstrip("\n").split("\t")
                if len(fields) >= 2 and fields[1] in cls.TARGETS:
                    indices[index] = fields[1]
        counts = {gene: 0 for gene in cls.TARGETS}
        library = 0
        dimensions = False
        with gzip.open(matrix_path, "rt", encoding="utf-8") as source:
            for line in source:
                if line.startswith("%"):
                    continue
                if not dimensions:
                    dimensions = True
                    continue
                feature, _, value = map(int, line.split())
                library += value
                gene = indices.get(feature)
                if gene:
                    counts[gene] += value
        if not library:
            raise ValueError(f"empty GSE288581 matrix for {donor_id}")
        return [
            {
                "donor_id": donor_id,
                "group": group,
                "gene_symbol": gene,
                "raw_count": counts[gene],
                "library_count": library,
                "cpm": counts[gene] / library * 1_000_000,
                "log2_cpm": math.log2(counts[gene] / library * 1_000_000 + 0.5),
            }
            for gene in cls.TARGETS
        ]

    @classmethod
    def _results(
        cls, rows: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        p_values: list[float] = []
        for gene in cls.TARGETS:
            case = np.asarray(
                [
                    float(str(row["log2_cpm"]))
                    for row in rows
                    if row["gene_symbol"] == gene and row["group"] == "AXI"
                ]
            )
            control = np.asarray(
                [
                    float(str(row["log2_cpm"]))
                    for row in rows
                    if row["gene_symbol"] == gene
                    and row["group"] == "Healthy"
                ]
            )
            statistic, p_value = stats.ttest_ind(case, control, equal_var=False)
            effect = float(np.mean(case) - np.mean(control))
            p_values.append(float(p_value))
            results.append(
                {
                    "gene_symbol": gene,
                    "case_donors": len(case),
                    "control_donors": len(control),
                    "log2_cpm_difference": effect,
                    "direction": "lower_in_case" if effect < 0 else "higher_in_case",
                    "welch_statistic": float(statistic),
                    "p_value": float(p_value),
                    "adjusted_p_value": 1.0,
                }
            )
        for row, adjusted in zip(
            results,
            SingleCellPseudobulkAnalyzer._bh(p_values),
            strict=True,
        ):
            row["adjusted_p_value"] = adjusted
        return results

    @classmethod
    def _sensitivity(
        cls,
        rows: list[dict[str, object]],
        results: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for result in results:
            gene = result["gene_symbol"]
            selected = [row for row in rows if row["gene_symbol"] == gene]
            for excluded in selected:
                retained = [
                    row
                    for row in selected
                    if row["donor_id"] != excluded["donor_id"]
                ]
                case = [
                    float(str(row["log2_cpm"]))
                    for row in retained
                    if row["group"] == "AXI"
                ]
                control = [
                    float(str(row["log2_cpm"]))
                    for row in retained
                    if row["group"] == "Healthy"
                ]
                effect = float(np.mean(case) - np.mean(control))
                output.append(
                    {
                        "gene_symbol": gene,
                        "excluded_donor": excluded["donor_id"],
                        "excluded_group": excluded["group"],
                        "full_effect": result["log2_cpm_difference"],
                        "leave_one_out_effect": effect,
                        "direction_preserved": effect
                        * float(str(result["log2_cpm_difference"]))
                        > 0,
                    }
                )
        return output

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
