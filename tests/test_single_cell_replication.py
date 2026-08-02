import csv
from pathlib import Path

from axis.analysis import SingleCellReplicationPlanner


def test_replication_plan_keeps_study_roles_separate(tmp_path: Path) -> None:
    candidates = tmp_path / "review.tsv"
    candidates.write_text(
        "gene_symbol\tdecision\n"
        "ATG14\tgenerate_causal_evidence\n"
        "OTHER\tdeprioritise_safety_or_essentiality\n",
        encoding="utf-8",
    )

    result = SingleCellReplicationPlanner().build(
        candidates, output_root=tmp_path / "out"
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        studies = {
            row["accession"]: row for row in csv.DictReader(source, delimiter="\t")
        }
    assert studies["GSE194315"]["direct_replication_eligible"] == "False"
    assert studies["GSE277791"]["direct_replication_eligible"] == "False"
    assert studies["PRJNA749866"]["direct_replication_eligible"] == "True"
    assert studies["PRJNA749866"]["executable_now"] == "False"
    with result.candidate_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["gene_symbol"] == "ATG14"
    assert "PRJNA749866" in rows[0]["replication_accessions"]
