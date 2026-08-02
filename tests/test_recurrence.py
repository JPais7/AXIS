import csv
import hashlib
import json
from pathlib import Path

import pytest

from axis.analysis import RecurrenceRanker
from axis.ingestion import GeoApiError


def write_gene_results(
    root: Path,
    study: str,
    rows: tuple[tuple[str, str, str, str], ...],
) -> None:
    path = root / study / "prepared" / "matrix" / "gene-level-results.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "gene_symbol",
                "probe_count",
                "probe_ids",
                "median_mean_difference",
                "direction",
                "simes_p_value",
                "adjusted_p_value",
                "significant",
            )
        )
        for gene, effect, p_value, adjusted in rows:
            writer.writerow(
                (
                    gene,
                    "1",
                    f"probe_{gene}",
                    effect,
                    "higher_in_case",
                    p_value,
                    adjusted,
                    str(float(adjusted) <= 0.05).lower(),
                )
            )
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


def make_studies(tmp_path: Path) -> None:
    write_gene_results(
        tmp_path,
        "GSE1",
        (
            ("IL17A", "2.0", "0.0001", "0.01"),
            ("PITX2", "-1.0", "0.01", "0.04"),
            ("TNF", "0.2", "0.2", "0.3"),
        ),
    )
    write_gene_results(
        tmp_path,
        "GSE2",
        (
            ("IL17A", "1.5", "0.001", "0.02"),
            ("PITX2", "0.1", "0.3", "0.4"),
            ("TNF", "0.5", "0.01", "0.04"),
        ),
    )


def test_rank_identifies_recurrent_gene_and_preserves_study_evidence(
    tmp_path: Path,
) -> None:
    make_studies(tmp_path)

    result = RecurrenceRanker().rank(
        ["gse1", "GSE2", "GSE1"],
        data_root=tmp_path,
        output_root=tmp_path / "output",
        min_recurrence=2,
    )

    assert result.studies == ("GSE1", "GSE2")
    assert result.genes == 3
    assert result.recurrent_genes == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["gene_symbol"] == "IL17A"
    assert rows[0]["significant_studies"] == "2"
    assert rows[0]["significant_study_ids"] == "GSE1|GSE2"
    assert rows[0]["direction_consistency"] == "1.0"
    assert rows[0]["recurrent"] == "True"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["minimum_recurrent_studies"] == 2
    assert summary["method"]["combined_p_value"] == ("Fisher across available studies")


def test_rank_requires_two_studies(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least two"):
        RecurrenceRanker().rank(["GSE1"], data_root=tmp_path)


def test_rank_reports_missing_gene_level_analysis(tmp_path: Path) -> None:
    write_gene_results(
        tmp_path,
        "GSE1",
        (("IL17A", "2", "0.001", "0.01"),),
    )

    with pytest.raises(GeoApiError, match="axis analyze GSE2"):
        RecurrenceRanker().rank(["GSE1", "GSE2"], data_root=tmp_path)


def test_rank_rejects_significant_opposite_directions(tmp_path: Path) -> None:
    write_gene_results(
        tmp_path,
        "GSE1",
        (("IL17A", "2", "0.001", "0.01"),),
    )
    write_gene_results(
        tmp_path,
        "GSE2",
        (("IL17A", "-2", "0.001", "0.01"),),
    )

    result = RecurrenceRanker().rank(
        ["GSE1", "GSE2"],
        data_root=tmp_path,
        output_root=tmp_path / "output",
    )
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))

    assert result.recurrent_genes == 0
    assert row["direction_concordant"] == "False"
    assert row["contradictory"] == "True"
    assert row["recurrent"] == "False"
