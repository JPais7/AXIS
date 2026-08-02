from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import mmread
from scipy.stats import ttest_ind


ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data/geo/GSE163314"
PROCESSED = GEO / "processed"
OUT = ROOT / "data/analysis/single-cell-validation/GSE163314"
METADATA = GEO / "GSE163314_All.combined.metadata.csv.gz"

SAMPLES = {
    "B3_AS": ("GSM4976995_3P", "axSpA"),
    "B27_AS": ("GSM4977005_7_27B", "axSpA"),
    "B5_Control": ("GSM4976997_5P", "healthy_control"),
    "B21_Control": ("GSM4977001_3_21B", "healthy_control"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cd8_barcodes() -> dict[str, set[str]]:
    selected = {sample: set() for sample in SAMPLES}
    with gzip.open(METADATA, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            sample = row["orig.ident"]
            if sample in selected and row["clusters"] == "CD8_T":
                # Seurat converted 10x "-1" to "_" and appended merge suffix.
                selected[sample].add(row[""].split("_", 1)[0] + "-1")
    return selected


def analyze_sample(sample: str, prefix: str, group: str, keep: set[str]) -> dict:
    barcode_path = PROCESSED / f"{prefix}_barcodes.tsv.gz"
    gene_path = PROCESSED / f"{prefix}_genes.tsv.gz"
    matrix_path = PROCESSED / f"{prefix}_matrix.mtx.gz"

    with gzip.open(barcode_path, "rt", encoding="utf-8") as handle:
        barcodes = [line.strip() for line in handle]
    selected_columns = np.array([i for i, value in enumerate(barcodes) if value in keep])
    if not selected_columns.size:
        raise ValueError(f"No CD8 cells matched for {sample}")

    with gzip.open(gene_path, "rt", encoding="utf-8") as handle:
        genes = [line.rstrip("\n").split("\t") for line in handle]
    # The reference contains two historical features labelled DDX24. Use the
    # canonical protein-coding Ensembl gene to avoid double counting.
    target_rows = [
        index
        for index, values in enumerate(genes)
        if values[0].split(".")[0] == "ENSG00000089737"
    ]
    if len(target_rows) != 1:
        raise ValueError(f"Expected one DDX24 feature in {sample}, found {target_rows}")

    with gzip.open(matrix_path, "rb") as handle:
        matrix = mmread(handle).tocsr()
    selected = matrix[:, selected_columns]
    total = float(selected.sum())
    target = float(selected[target_rows[0], :].sum())
    cpm = target / total * 1_000_000
    return {
        "donor": sample,
        "group": group,
        "cell_state": "CD8_T",
        "cells": int(selected_columns.size),
        "ddx24_counts": int(target),
        "library_counts": int(total),
        "ddx24_cpm": cpm,
        "ddx24_log2_cpm": math.log2(cpm + 1),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    selected = load_cd8_barcodes()
    rows = [
        analyze_sample(sample, prefix, group, selected[sample])
        for sample, (prefix, group) in SAMPLES.items()
    ]

    with (OUT / "donor-pseudobulk.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    case = np.array([row["ddx24_log2_cpm"] for row in rows if row["group"] == "axSpA"])
    control = np.array(
        [row["ddx24_log2_cpm"] for row in rows if row["group"] == "healthy_control"]
    )
    effect = float(case.mean() - control.mean())
    se = float(math.sqrt(case.var(ddof=1) / len(case) + control.var(ddof=1) / len(control)))
    test = ttest_ind(case, control, equal_var=False)
    summary = {
        "accession": "GSE163314",
        "status": "analysis_complete",
        "contrast": "axSpA_minus_healthy_control",
        "cell_state": "author_annotated_CD8_T_in_peripheral_blood",
        "cases": len(case),
        "controls": len(control),
        "effect_log2_cpm": effect,
        "standard_error": se,
        "welch_p_value": float(test.pvalue),
        "direction": "lower_in_case" if effect < 0 else "higher_in_case",
        "guardrails": [
            "Only two participants per group.",
            "Pilot cohort and high imprecision.",
            "Author CD8_T annotation is broader than the predeclared memory/effector CD8 state.",
            "Result should be treated as cell-state sensitivity until a memory CD8 subset is reproducibly defined.",
        ],
        "input_sha256": {
            "metadata": sha256(METADATA),
            "raw_tar": sha256(GEO / "GSE163314_RAW.tar"),
        },
    }
    (OUT / "validation-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
