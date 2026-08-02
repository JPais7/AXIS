import csv
import json
from pathlib import Path

from axis.analysis import Emtab12805Reviewer


def test_emtab_review_collapses_repositories_and_blocks_reference_use(
    tmp_path: Path,
) -> None:
    result = Emtab12805Reviewer().review(output_root=tmp_path / "review")

    review = json.loads(result.review_path.read_text(encoding="utf-8"))
    with result.overlap_path.open(encoding="utf-8", newline="") as source:
        overlap = list(csv.DictReader(source, delimiter="\t"))

    assert result.decision == "mechanistic_not_reference_ready"
    assert review["automatic_eligibility"] is False
    assert review["independent_cohorts"] == 1
    assert {row["accession"] for row in overlap} == {
        "E-MTAB-12805",
        "GSE232131",
    }
    assert {row["cohort_cluster"] for row in overlap} == {
        "EMTAB12805_GSE232131"
    }
    assert "whole_blood_cell_composition_reference" in review["prohibited_roles"]
