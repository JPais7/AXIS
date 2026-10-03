from __future__ import annotations

import csv
import json
from pathlib import Path

from axis.analysis.biological_benchmark import BiologicalBenchmarkEvaluator


def _write_inputs(root: Path, genes: list[str]) -> tuple[Path, Path, Path]:
    ranking = root / "ranking.tsv"
    with ranking.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("gene_symbol", "directions"), delimiter="\t"
        )
        writer.writeheader()
        for gene in genes:
            writer.writerow(
                {"gene_symbol": gene, "directions": "A:higher_in_case|B:higher_in_case"}
            )
    protocol = root / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "benchmark_id": "test",
                "success_criteria": {
                    "top_n": 5,
                    "minimum_reference_hits": 2,
                    "maximum_enrichment_p_value": 1.0,
                    "required_direction": "higher_in_case",
                },
            }
        ),
        encoding="utf-8",
    )
    reference = root / "reference.json"
    reference.write_text(
        json.dumps({"benchmark_id": "test", "genes": ["IFI44L", "MX1"]}),
        encoding="utf-8",
    )
    return ranking, protocol, reference


def test_positive_control_passes_and_writes_auditable_outputs(tmp_path: Path) -> None:
    ranking, protocol, reference = _write_inputs(
        tmp_path, ["IFI44L", "MX1", "A", "B", "C", "D"]
    )
    result = BiologicalBenchmarkEvaluator().evaluate(
        ranking,
        protocol_path=protocol,
        reference_path=reference,
        output_root=tmp_path / "output",
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.status == "passed"
    assert report["reference_hits"] == ["IFI44L", "MX1"]
    assert report["checks"]["directional_concordance"] is True
    assert report["control_type"] == "positive"
    assert report["control_expectation_met"] is True
    assert result.gene_results_path.is_file()


def test_positive_control_retains_failure(tmp_path: Path) -> None:
    ranking, protocol, reference = _write_inputs(
        tmp_path, ["A", "B", "C", "D", "E", "IFI44L", "MX1"]
    )
    result = BiologicalBenchmarkEvaluator().evaluate(
        ranking,
        protocol_path=protocol,
        reference_path=reference,
        output_root=tmp_path / "output",
    )
    assert result.status == "not_passed"
