import csv
from pathlib import Path

from axis.analysis import SingleCellReferenceExpander


def test_reference_expansion_selects_all_eligible_cell_types(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.tsv"
    with design.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=("cell_type", "eligible_for_pseudobulk"),
            delimiter="\t",
        )
        writer.writeheader()
        for index in range(6):
            writer.writerow(
                {
                    "cell_type": f"type_{index}",
                    "eligible_for_pseudobulk": index < 5,
                }
            )

    assert SingleCellReferenceExpander._eligible_cell_types(design) == (
        "type_0",
        "type_1",
        "type_2",
        "type_3",
        "type_4",
    )
