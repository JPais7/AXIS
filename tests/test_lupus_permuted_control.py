from __future__ import annotations

import csv
from pathlib import Path

import scripts.build_lupus_permuted_control as control


def test_permutation_is_deterministic_and_preserves_group_sizes(
    tmp_path: Path, monkeypatch: object
) -> None:
    positive = tmp_path / "positive"
    negative = tmp_path / "negative"
    positive.mkdir()
    source = positive / "GSE1-first-visit-sample-sheet.tsv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("sample_id", "group", "subject_id", "visit_policy"),
            delimiter="\t",
        )
        writer.writeheader()
        for index, group in enumerate(("case", "case", "control", "control")):
            writer.writerow(
                {
                    "sample_id": f"S{index}",
                    "group": group,
                    "subject_id": f"P{index}",
                    "visit_policy": "first",
                }
            )
    monkeypatch.setattr(control, "POSITIVE", positive)  # type: ignore[attr-defined]
    monkeypatch.setattr(control, "NEGATIVE", negative)  # type: ignore[attr-defined]
    first = control.permute("GSE1").read_text(encoding="utf-8")
    second = control.permute("GSE1").read_text(encoding="utf-8")
    rows = list(csv.DictReader(first.splitlines(), delimiter="\t"))
    assert first == second
    assert [row["group"] for row in rows].count("case") == 2
    assert [row["group"] for row in rows].count("control") == 2
