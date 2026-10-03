"""Create deterministic within-cohort label permutations for the SLE benchmark."""

from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSITIVE = ROOT / "benchmarks" / "biological" / "lupus-ifn-v1"
NEGATIVE = ROOT / "benchmarks" / "biological" / "lupus-ifn-permuted-v1"
SEED = 20260806


def permute(accession: str) -> Path:
    source = POSITIVE / f"{accession}-first-visit-sample-sheet.tsv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    original = [row["group"] for row in rows]
    labels = original.copy()
    accession_seed = int.from_bytes(
        hashlib.sha256(accession.encode("ascii")).digest()[:8], "big"
    )
    random.Random(SEED ^ accession_seed).shuffle(labels)
    if labels == original:
        raise RuntimeError(f"permutation for {accession} did not change labels")

    output = NEGATIVE / f"{accession}-permuted-sample-sheet.tsv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "sample_id",
                "group",
                "subject_id",
                "permutation_seed",
                "negative_control",
            ),
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
                    "permutation_seed": SEED,
                    "negative_control": "within_cohort_label_permutation",
                }
            )
    return output


if __name__ == "__main__":
    for study in ("GSE49454", "GSE61635"):
        print(permute(study))
