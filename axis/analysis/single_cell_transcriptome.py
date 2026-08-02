"""Whole-transcriptome, subject-level analysis of GSE194315."""

from __future__ import annotations

import csv
import json
import math
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, cast

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from axis.analysis.single_cell_pseudobulk import SingleCellPseudobulkAnalyzer
from axis.ingestion.geo import GeoApiError

IMMUNE_PATHWAYS: dict[str, tuple[str, ...]] = {
    "T_cell_receptor_signalling": (
        "CD2",
        "CD3D",
        "CD3E",
        "CD3G",
        "LCK",
        "LAT",
        "TRAT1",
        "ZAP70",
    ),
    "IL2_JAK_STAT_signalling": (
        "IL2RA",
        "IL2RB",
        "IL2RG",
        "JAK1",
        "JAK3",
        "STAT5A",
        "STAT5B",
        "CISH",
    ),
    "cytotoxic_effector_programme": (
        "CCL5",
        "GNLY",
        "GZMA",
        "GZMB",
        "GZMH",
        "NKG7",
        "PRF1",
        "CTSW",
    ),
    "interferon_response": (
        "IFI6",
        "IFI27",
        "IFI44",
        "IFI44L",
        "IFIT1",
        "IFIT2",
        "IFIT3",
        "ISG15",
        "MX1",
        "OAS1",
        "STAT1",
    ),
    "NFkB_inflammatory_signalling": (
        "NFKB1",
        "NFKB2",
        "RELA",
        "RELB",
        "TNFAIP3",
        "NFKBIA",
        "TRAF1",
    ),
    "T_cell_exhaustion_regulation": (
        "CTLA4",
        "HAVCR2",
        "LAG3",
        "PDCD1",
        "TIGIT",
        "TOX",
        "ENTPD1",
    ),
    "cell_cycle": (
        "MKI67",
        "PCNA",
        "MCM2",
        "MCM3",
        "MCM4",
        "MCM5",
        "MCM6",
        "TOP2A",
    ),
}


@dataclass(frozen=True)
class SingleCellTranscriptomeRun:
    genes_tested: int
    pathways_tested: int
    candidates: int
    differential_path: Path
    pathway_path: Path
    candidate_path: Path
    summary_path: Path


class SingleCellTranscriptomeAnalyzer:
    """Stream all genes and compare subject pseudobulks within cell types."""

    def analyze(
        self,
        archive_path: str | Path,
        metadata_path: str | Path,
        *,
        cell_types: tuple[str, ...] = ("CD4 TCM", "CD8 TEM"),
        case_status: str = "AXI",
        control_status: str = "Healthy",
        minimum_cells: int = 20,
        minimum_cpm: float = 1.0,
        minimum_group_fraction: float = 0.2,
        bulk_path: str | Path | None = None,
        readiness_path: str | Path | None = None,
        output_root: str | Path = Path("data/single-cell/GSE194315/transcriptome"),
    ) -> SingleCellTranscriptomeRun:
        archive = Path(archive_path)
        metadata = Path(metadata_path)
        selected = SingleCellPseudobulkAnalyzer._metadata(
            metadata,
            cell_types=set(cell_types),
            statuses={case_status, control_status},
        )
        gene_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
        library_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        cell_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        seen_cells: set[str] = set()
        observed_genes: set[str] = set()
        run_parts: dict[str, dict[str, object]] = defaultdict(dict)
        completed_runs = 0
        try:
            with tarfile.open(archive, "r|gz") as source:
                for member in source:
                    if not member.isfile():
                        continue
                    run, kind = SingleCellPseudobulkAnalyzer._member(member.name)
                    if run is None:
                        continue
                    extracted = source.extractfile(member)
                    if extracted is None:
                        continue
                    if kind == "barcodes":
                        run_parts[run]["barcodes"] = (
                            SingleCellPseudobulkAnalyzer._barcodes(
                                extracted, run, selected
                            )
                        )
                    elif kind == "features":
                        feature_map = self._all_features(extracted)
                        observed_genes.update(feature_map.values())
                        run_parts[run]["features"] = feature_map
                    elif kind == "matrix":
                        parts = run_parts[run]
                        barcodes = parts.get("barcodes")
                        features = parts.get("features")
                        if not isinstance(barcodes, dict) or not isinstance(
                            features, dict
                        ):
                            raise GeoApiError(f"archive order is invalid for run {run}")
                        SingleCellPseudobulkAnalyzer._matrix(
                            extracted,
                            barcodes=barcodes,
                            features=features,
                            gene_counts=gene_counts,
                            library_counts=library_counts,
                            cell_counts=cell_counts,
                            seen_cells=seen_cells,
                        )
                        completed_runs += 1
                        del run_parts[run]
        except (OSError, tarfile.TarError, EOFError) as error:
            raise GeoApiError(
                f"cannot stream 10x archive {archive}: {error}"
            ) from error

        eligible = {
            group
            for group, cells in cell_counts.items()
            if cells >= minimum_cells and library_counts[group] > 0
        }
        values = self._log_cpm(gene_counts, library_counts, eligible, observed_genes)
        differential = self._differential(
            values,
            eligible,
            observed_genes,
            cell_types=cell_types,
            case_status=case_status,
            control_status=control_status,
            minimum_cpm=minimum_cpm,
            minimum_group_fraction=minimum_group_fraction,
        )
        pathways = self._pathways(
            values,
            eligible,
            cell_types=cell_types,
            case_status=case_status,
            control_status=control_status,
        )
        candidates = self._candidates(
            differential,
            bulk_path=Path(bulk_path) if bulk_path else None,
            readiness_path=Path(readiness_path) if readiness_path else None,
        )

        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        differential_path = destination / "cell-type-differential.tsv"
        pathway_path = destination / "cell-type-pathways.tsv"
        candidate_path = destination / "integrated-candidates.tsv"
        summary_path = destination / "transcriptome-analysis.json"
        self._write(differential_path, differential)
        self._write(pathway_path, pathways)
        self._write(candidate_path, candidates)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "exploratory_whole_transcriptome_pseudobulk",
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE194315",
                    "runs": completed_runs,
                    "matched_cells": len(seen_cells),
                    "eligible_subject_cell_type_groups": len(eligible),
                    "cell_types": list(cell_types),
                    "genes_observed": len(observed_genes),
                    "gene_tests": len(differential),
                    "pathway_tests": len(pathways),
                    "filter": {
                        "minimum_cells_per_subject_cell_type": minimum_cells,
                        "minimum_cpm": minimum_cpm,
                        "minimum_fraction_in_each_group": minimum_group_fraction,
                    },
                    "gene_method": (
                        "Welch test of subject-level log2(CPM + 0.5); "
                        "Benjamini-Hochberg within cell type"
                    ),
                    "pathway_method": (
                        "mean gene-wise standardised log-CPM per subject using "
                        "predeclared immune modules; Welch test and BH globally"
                    ),
                    "candidate_score": (
                        "transparent exploratory score combining single-cell FDR, "
                        "effect size, cross-cell consistency, bulk concordance and "
                        "existing therapeutic-readiness evidence"
                    ),
                    "structural_triage_policy": (
                        "PDB/AlphaFold assessment is deferred to the highest-ranked "
                        "biologically supported targets; structure does not increase "
                        "causal evidence"
                    ),
                    "warning": (
                        "Exploratory prioritisation only. The simple log-CPM model "
                        "does not adjust donor covariates and requires independent "
                        "replication and perturbation before target nomination."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SingleCellTranscriptomeRun(
            genes_tested=len(differential),
            pathways_tested=len(pathways),
            candidates=len(candidates),
            differential_path=differential_path,
            pathway_path=pathway_path,
            candidate_path=candidate_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _all_features(fileobj: IO[bytes]) -> dict[int, str]:
        result: dict[int, str] = {}
        with SingleCellPseudobulkAnalyzer._text(fileobj) as source:
            for index, line in enumerate(source, start=1):
                fields = line.rstrip("\n").split("\t")
                if len(fields) >= 2 and (
                    len(fields) < 3 or fields[2] == "Gene Expression"
                ):
                    symbol = fields[1].strip().upper()
                    if symbol:
                        result[index] = symbol
        return result

    @staticmethod
    def _log_cpm(
        counts: dict[tuple[str, str, str, str], int],
        libraries: dict[tuple[str, str, str], int],
        groups: set[tuple[str, str, str]],
        genes: set[str],
    ) -> dict[tuple[str, str, str, str], float]:
        values: dict[tuple[str, str, str, str], float] = {}
        baseline = math.log2(0.5)
        for group in groups:
            library = libraries[group]
            for gene in genes:
                count = counts.get((*group, gene), 0)
                values[(*group, gene)] = (
                    math.log2(count / library * 1_000_000 + 0.5) if count else baseline
                )
        return values

    @staticmethod
    def _differential(
        values: dict[tuple[str, str, str, str], float],
        groups: set[tuple[str, str, str]],
        genes: set[str],
        *,
        cell_types: tuple[str, ...],
        case_status: str,
        control_status: str,
        minimum_cpm: float,
        minimum_group_fraction: float,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        threshold = math.log2(minimum_cpm + 0.5)
        for cell_type in cell_types:
            case_groups = sorted(
                group
                for group in groups
                if group[1] == case_status and group[2] == cell_type
            )
            control_groups = sorted(
                group
                for group in groups
                if group[1] == control_status and group[2] == cell_type
            )
            cell_rows: list[dict[str, object]] = []
            p_values: list[float] = []
            for gene in sorted(genes):
                case = np.asarray([values[(*group, gene)] for group in case_groups])
                control = np.asarray(
                    [values[(*group, gene)] for group in control_groups]
                )
                case_fraction = float(np.mean(case >= threshold))
                control_fraction = float(np.mean(control >= threshold))
                if (
                    case_fraction < minimum_group_fraction
                    or control_fraction < minimum_group_fraction
                ):
                    continue
                statistic, p_value = stats.ttest_ind(case, control, equal_var=False)
                if not np.isfinite(p_value):
                    continue
                effect = float(np.mean(case) - np.mean(control))
                cell_rows.append(
                    {
                        "gene_symbol": gene,
                        "cell_type": cell_type,
                        "case_subjects": len(case),
                        "control_subjects": len(control),
                        "case_expression_fraction": case_fraction,
                        "control_expression_fraction": control_fraction,
                        "log2_cpm_difference": effect,
                        "direction": (
                            "higher_in_case" if effect > 0 else "lower_in_case"
                        ),
                        "welch_statistic": float(statistic),
                        "p_value": float(p_value),
                        "adjusted_p_value": 1.0,
                    }
                )
                p_values.append(float(p_value))
            adjusted = SingleCellPseudobulkAnalyzer._bh(p_values)
            for row, value in zip(cell_rows, adjusted, strict=True):
                row["adjusted_p_value"] = value
            rows.extend(cell_rows)
        rows.sort(
            key=lambda row: (
                float(cast(float, row["adjusted_p_value"])),
                -abs(float(cast(float, row["log2_cpm_difference"]))),
            )
        )
        return rows

    @staticmethod
    def _pathways(
        values: dict[tuple[str, str, str, str], float],
        groups: set[tuple[str, str, str]],
        *,
        cell_types: tuple[str, ...],
        case_status: str,
        control_status: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        p_values: list[float] = []
        for cell_type in cell_types:
            typed = sorted(group for group in groups if group[2] == cell_type)
            for pathway, declared_genes in IMMUNE_PATHWAYS.items():
                genes = [
                    gene
                    for gene in declared_genes
                    if any((*group, gene) in values for group in typed)
                ]
                gene_z: dict[str, np.ndarray] = {}
                for gene in genes:
                    raw = np.asarray([values[(*group, gene)] for group in typed])
                    standard_deviation = float(np.std(raw, ddof=1))
                    if standard_deviation > 0:
                        gene_z[gene] = (raw - np.mean(raw)) / standard_deviation
                if len(gene_z) < 3:
                    continue
                scores = np.mean(np.vstack(tuple(gene_z.values())), axis=0)
                case = scores[
                    [
                        index
                        for index, group in enumerate(typed)
                        if group[1] == case_status
                    ]
                ]
                control = scores[
                    [
                        index
                        for index, group in enumerate(typed)
                        if group[1] == control_status
                    ]
                ]
                statistic, p_value = stats.ttest_ind(case, control, equal_var=False)
                effect = float(np.mean(case) - np.mean(control))
                rows.append(
                    {
                        "pathway": pathway,
                        "cell_type": cell_type,
                        "genes_used": len(gene_z),
                        "gene_symbols": "|".join(gene_z),
                        "case_subjects": len(case),
                        "control_subjects": len(control),
                        "standardised_score_difference": effect,
                        "direction": (
                            "higher_in_case" if effect > 0 else "lower_in_case"
                        ),
                        "welch_statistic": float(statistic),
                        "p_value": float(p_value),
                        "adjusted_p_value": 1.0,
                    }
                )
                p_values.append(float(p_value))
        for row, value in zip(
            rows, SingleCellPseudobulkAnalyzer._bh(p_values), strict=True
        ):
            row["adjusted_p_value"] = value
        rows.sort(key=lambda row: float(cast(float, row["adjusted_p_value"])))
        return rows

    @staticmethod
    def _indexed(path: Path | None) -> dict[str, dict[str, str]]:
        if path is None or not path.exists():
            return {}
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"].strip().upper(): row
                for row in csv.DictReader(source, delimiter="\t")
            }

    @classmethod
    def _candidates(
        cls,
        differential: list[dict[str, object]],
        *,
        bulk_path: Path | None,
        readiness_path: Path | None,
    ) -> list[dict[str, object]]:
        bulk = cls._indexed(bulk_path)
        readiness = cls._indexed(readiness_path)
        by_gene: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in differential:
            by_gene[str(row["gene_symbol"])].append(row)
        candidates: list[dict[str, object]] = []
        for gene, rows in by_gene.items():
            best = min(
                rows, key=lambda row: float(cast(float, row["adjusted_p_value"]))
            )
            best_fdr = float(cast(float, best["adjusted_p_value"]))
            best_effect = float(cast(float, best["log2_cpm_difference"]))
            directions = {str(row["direction"]) for row in rows}
            bulk_row = bulk.get(gene, {})
            bulk_direction = bulk_row.get("direction", "")
            single_direction = str(best["direction"])
            bulk_agrees = bool(bulk_direction) and bulk_direction == single_direction
            ready = readiness.get(gene, {})
            genetic = int(ready.get("genetic_evidence_count") or 0) > 0
            clinical = int(ready.get("clinical_candidate_count") or 0) > 0
            score = (
                min(-math.log10(max(best_fdr, 1e-300)), 10.0) * 3.0
                + min(abs(best_effect), 2.0) * 2.0
                + (1.0 if len(directions) == 1 and len(rows) > 1 else 0.0)
                + (2.0 if bulk_agrees else 0.0)
                + (2.0 if genetic else 0.0)
                + (1.0 if clinical else 0.0)
            )
            candidates.append(
                {
                    "gene_symbol": gene,
                    "exploratory_score": score,
                    "best_cell_type": best["cell_type"],
                    "best_single_cell_direction": single_direction,
                    "best_single_cell_log2_cpm_difference": best_effect,
                    "best_single_cell_adjusted_p_value": best_fdr,
                    "direction_consistent_across_tested_cell_types": (
                        len(directions) == 1 and len(rows) > 1
                    ),
                    "bulk_direction": bulk_direction,
                    "bulk_direction_concordant": bulk_row.get(
                        "direction_concordant", ""
                    ),
                    "single_cell_bulk_direction_agrees": bulk_agrees,
                    "genetic_evidence_available": genetic,
                    "clinical_precedent_available": clinical,
                    "therapeutic_direction": ready.get(
                        "genetic_therapeutic_direction", "unknown"
                    ),
                    "structural_triage": (
                        "eligible_after_causal_review"
                        if best_fdr <= 0.05 and (bulk_agrees or genetic)
                        else "defer"
                    ),
                }
            )
        candidates.sort(
            key=lambda row: (
                -float(cast(float, row["exploratory_score"])),
                str(row["gene_symbol"]),
            )
        )
        return candidates

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
