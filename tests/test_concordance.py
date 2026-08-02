import csv
import hashlib
import json
from pathlib import Path

from axis.analysis import DirectionConcordanceAnalyzer


def write_study(
    root: Path,
    study: str,
    rows: tuple[tuple[str, float, float], ...],
) -> None:
    path = root / study / "prepared" / "matrix" / "gene-level-results.tsv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "gene_symbol",
                "median_mean_difference",
                "simes_p_value",
                "adjusted_p_value",
            )
        )
        for gene, effect, p_value in rows:
            writer.writerow((gene, effect, p_value, min(p_value * 2, 1.0)))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / "study-eligibility.json").write_text(
        json.dumps(
            {
                "accession": study,
                "decision": "approved",
                "species": "Homo sapiens",
                "tissue": "blood",
                "phenotype": "ankylosing spondylitis",
                "allowed_roles": ["discovery"],
                "gene_results_checksum": f"sha256:{checksum}",
            }
        ),
        encoding="utf-8",
    )


def test_concordance_ranks_same_direction_without_calling_it_recurrence(
    tmp_path: Path,
) -> None:
    write_study(
        tmp_path,
        "GSE1",
        (("SAME", 2.0, 0.2), ("MIXED", 1.0, 0.01)),
    )
    write_study(
        tmp_path,
        "GSE2",
        (("SAME", 1.5, 0.3), ("MIXED", -1.0, 0.01)),
    )

    result = DirectionConcordanceAnalyzer().run(
        ["GSE1", "GSE2"],
        data_root=tmp_path,
        output_root=tmp_path / "output",
    )

    assert result.genes == 2
    assert result.concordant_genes == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["gene_symbol"] == "SAME"
    assert rows[0]["direction_concordant"] == "True"
    assert rows[0]["nominal_supporting_studies"] == "0"
    assert rows[1]["direction"] == "mixed"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["publication_eligible"] is False
    assert "not statistical recurrence" in summary["warning"]
