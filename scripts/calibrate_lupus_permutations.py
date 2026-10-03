"""Estimate the AXIS SLE benchmark pass rate under permuted labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import tempfile
import time
from pathlib import Path

from axis.analysis.biological_benchmark import BiologicalBenchmarkEvaluator
from axis.analysis.differential import DifferentialAnalyzer
from axis.analysis.eligibility import StudyAssessor
from axis.analysis.recurrence import RecurrenceRanker

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "benchmarks" / "lupus-ifn-permuted-v1" / "geo"
BENCHMARK = ROOT / "benchmarks" / "biological" / "lupus-ifn-permuted-v1"
OUTPUT = ROOT / "data" / "analysis" / "benchmarks" / "lupus-ifn-permutation-calibration"
STUDIES = {"GSE49454": "GPL10558", "GSE61635": "GPL570"}


def permuted_sheet(accession: str, seed: int, destination: Path) -> Path:
    source = (
        ROOT
        / "benchmarks"
        / "biological"
        / "lupus-ifn-v1"
        / f"{accession}-first-visit-sample-sheet.tsv"
    )
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    labels = [row["group"] for row in rows]
    accession_seed = int.from_bytes(
        hashlib.sha256(accession.encode("ascii")).digest()[:8], "big"
    )
    random.Random(seed ^ accession_seed).shuffle(labels)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("sample_id", "group", "subject_id", "seed"),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row, label in zip(rows, labels, strict=True):
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "group": label,
                    "subject_id": row["subject_id"],
                    "seed": seed,
                }
            )
    return destination


def run(repetitions: int, base_seed: int) -> Path:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    observations: list[dict[str, object]] = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="axis-sle-permutations-") as temporary:
        temporary_root = Path(temporary)
        for index in range(repetitions):
            seed = base_seed + index
            for accession, platform in STUDIES.items():
                sheet = permuted_sheet(
                    accession, seed, temporary_root / f"{accession}-{seed}.tsv"
                )
                DifferentialAnalyzer().analyze(
                    accession,
                    platform=platform,
                    data_root=DATA_ROOT,
                    sample_sheet=sheet,
                )
                StudyAssessor().assess(
                    accession,
                    decision="approved",
                    rationale=(
                        "Deterministic within-cohort label permutation for null "
                        f"calibration; seed={seed}."
                    ),
                    species="Homo sapiens",
                    tissue="whole blood",
                    phenotype="permuted-label negative control",
                    allowed_roles=("discovery",),
                    data_root=DATA_ROOT,
                )
            run_root = temporary_root / f"run-{index + 1:04d}"
            ranking = RecurrenceRanker().rank(
                tuple(STUDIES),
                data_root=DATA_ROOT,
                output_root=run_root,
                min_recurrence=2,
            )
            evaluation = BiologicalBenchmarkEvaluator().evaluate(
                ranking.output_path,
                protocol_path=BENCHMARK / "protocol.json",
                reference_path=BENCHMARK / "sealed-reference.json",
                output_root=run_root / "evaluation",
            )
            report = json.loads(evaluation.report_path.read_text(encoding="utf-8"))
            observations.append(
                {
                    "iteration": index + 1,
                    "seed": seed,
                    "false_positive_pass": evaluation.status == "passed",
                    "reference_hits_top_100": len(report["reference_hits"]),
                    "directionally_concordant_hits": len(
                        report["directionally_concordant_hits"]
                    ),
                    "enrichment_p_value": report["enrichment_p_value"],
                    "recurrent_genes": ranking.recurrent_genes,
                }
            )

    table = OUTPUT / "permutation-runs.tsv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(observations[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(observations)
    false_positives = sum(bool(row["false_positive_pass"]) for row in observations)
    hit_counts = [int(row["reference_hits_top_100"]) for row in observations]
    report_path = OUTPUT / "permutation-calibration-report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": "axis-sle-type-i-interferon-permutation-calibration-v1",
                "repetitions": repetitions,
                "base_seed": base_seed,
                "false_positive_passes": false_positives,
                "empirical_false_positive_rate": false_positives / repetitions,
                "upper_bound_if_zero_false_positives_rule_of_three": (
                    3 / repetitions if false_positives == 0 else None
                ),
                "reference_hits_top_100": {
                    "minimum": min(hit_counts),
                    "median": statistics.median(hit_counts),
                    "maximum": max(hit_counts),
                },
                "elapsed_seconds": time.perf_counter() - started,
                "runs": table.name,
                "interpretation": (
                    "Empirical calibration under deterministic within-cohort label "
                    "permutation. It does not cover every null mechanism or dataset."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=20260806)
    arguments = parser.parse_args()
    print(run(arguments.repetitions, arguments.base_seed))
