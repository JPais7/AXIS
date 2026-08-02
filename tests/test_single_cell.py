import csv
import gzip
import json
from pathlib import Path

from axis.analysis import SingleCellPlanBuilder


def test_single_cell_plan_uses_subjects_as_replicates(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.tsv.gz"
    rows = [
        "CellName\tSample\tSubject\tStatus\tIncludedInStudy\tCellType",
    ]
    for status, prefix in (("AXI", "A"), ("Healthy", "H")):
        for subject_number in range(2):
            subject = f"{prefix}{subject_number}"
            for cell_number in range(3):
                rows.append(
                    f"{subject}_{cell_number}\tS{subject}\t{subject}\t"
                    f"{status}\tTRUE\tCD4 TCM"
                )
    rows.append("excluded\tS0\tA0\tAXI\tFALSE\tCD4 TCM")
    with gzip.open(metadata, "wt", encoding="utf-8") as output:
        output.write("\n".join(rows) + "\n")

    result = SingleCellPlanBuilder().build(
        metadata,
        minimum_cells_per_subject=2,
        minimum_subjects_per_group=2,
        output_root=tmp_path / "plan",
    )

    assert result.included_cells == 12
    assert result.case_subjects == 2
    assert result.control_subjects == 2
    assert result.eligible_cell_types == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["eligible_for_pseudobulk"] == "True"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "subjects are biological replicates" in summary["independence_policy"]
    assert summary["target_genes"] == ["CD2", "IL2RB", "IKZF3"]
