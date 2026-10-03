"""Evaluate a frozen positive-control biological benchmark."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from scipy.stats import hypergeom  # type: ignore[import-untyped]


@dataclass(frozen=True)
class BiologicalBenchmarkRun:
    status: str
    report_path: Path
    gene_results_path: Path


class BiologicalBenchmarkEvaluator:
    """Score a ranked gene table against a reference fixed before analysis."""

    def evaluate(
        self,
        ranking_path: str | Path,
        *,
        protocol_path: str | Path,
        reference_path: str | Path,
        output_root: str | Path = Path("biological-benchmark-output"),
    ) -> BiologicalBenchmarkRun:
        ranking = Path(ranking_path)
        protocol_file = Path(protocol_path)
        reference_file = Path(reference_path)
        protocol = json.loads(protocol_file.read_text(encoding="utf-8"))
        reference = json.loads(reference_file.read_text(encoding="utf-8"))
        if protocol.get("benchmark_id") != reference.get("benchmark_id"):
            raise ValueError("protocol and reference benchmark identifiers differ")

        rows = self._read_ranking(ranking)
        top_n = int(protocol["success_criteria"]["top_n"])
        minimum_hits = int(protocol["success_criteria"]["minimum_reference_hits"])
        maximum_p = float(protocol["success_criteria"]["maximum_enrichment_p_value"])
        required_direction = str(protocol["success_criteria"]["required_direction"])
        reference_genes = tuple(str(gene).upper() for gene in reference["genes"])
        top = rows[:top_n]
        top_symbols = {row["gene_symbol"] for row in top}
        hits = tuple(gene for gene in reference_genes if gene in top_symbols)
        universe = {row["gene_symbol"] for row in rows}
        in_universe = tuple(gene for gene in reference_genes if gene in universe)
        enrichment_p = float(
            hypergeom.sf(
                len(hits) - 1,
                len(universe),
                len(in_universe),
                min(top_n, len(rows)),
            )
        )
        directions = {
            gene: self._direction(
                next(row for row in rows if row["gene_symbol"] == gene)
            )
            for gene in hits
        }
        concordant = tuple(
            gene
            for gene, direction in directions.items()
            if direction == required_direction
        )
        checks = {
            "minimum_reference_hits": len(hits) >= minimum_hits,
            "reference_enrichment": enrichment_p <= maximum_p,
            "directional_concordance": len(concordant) >= minimum_hits,
            "adequate_reference_coverage": len(in_universe) >= minimum_hits,
        }
        status = "passed" if all(checks.values()) else "not_passed"
        control_type = str(protocol.get("control_type", "positive"))
        expected_status = str(protocol.get("expected_evaluator_status", "passed"))
        expectation_met = status == expected_status
        if control_type == "negative":
            interpretation = (
                "Permuted-label negative control. A not_passed biological score is "
                "the expected outcome and supports absence of obvious label leakage "
                "for this deterministic permutation."
            )
        else:
            interpretation = (
                "Positive-control benchmark only; passing supports recovery of "
                "known biology and does not establish diagnostic performance, "
                "causality, or general superiority."
            )

        output = Path(output_root)
        output.mkdir(parents=True, exist_ok=True)
        gene_results = output / "reference-gene-results.tsv"
        with gene_results.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("gene_symbol", "present", "rank", "direction", "top_n_hit"),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            positions = {row["gene_symbol"]: index for index, row in enumerate(rows, 1)}
            for gene in reference_genes:
                writer.writerow(
                    {
                        "gene_symbol": gene,
                        "present": gene in positions,
                        "rank": positions.get(gene, ""),
                        "direction": directions.get(gene, "not_in_top_n"),
                        "top_n_hit": gene in hits,
                    }
                )

        report = output / "biological-benchmark-report.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "benchmark_id": protocol["benchmark_id"],
                    "status": status,
                    "control_type": control_type,
                    "expected_evaluator_status": expected_status,
                    "control_expectation_met": expectation_met,
                    "interpretation": interpretation,
                    "ranking": str(ranking),
                    "eligible_gene_universe": len(universe),
                    "reference_genes_in_universe": len(in_universe),
                    "top_n": min(top_n, len(rows)),
                    "reference_hits": list(hits),
                    "directionally_concordant_hits": list(concordant),
                    "enrichment_p_value": enrichment_p,
                    "checks": checks,
                    "gene_results": gene_results.name,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return BiologicalBenchmarkRun(status, report, gene_results)

    @staticmethod
    def _read_ranking(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        if not rows or "gene_symbol" not in rows[0]:
            raise ValueError(
                "ranking must contain a gene_symbol column and at least one row"
            )
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            gene = row["gene_symbol"].strip().upper()
            if gene and gene not in seen:
                seen.add(gene)
                normalized.append({**row, "gene_symbol": gene})
        return normalized

    @staticmethod
    def _direction(row: dict[str, str]) -> str:
        directions = row.get("directions", "")
        values = [part.rsplit(":", 1)[-1] for part in directions.split("|") if part]
        if values and len(set(values)) == 1:
            return values[0]
        return row.get("direction", "mixed_or_unreported") or "mixed_or_unreported"
