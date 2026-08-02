import csv
import gzip
import json
from pathlib import Path

import pytest

from axis.analysis import NormalizedRnaSeqAnalyzer
from axis.ingestion import GeoApiError


def write_rnaseq(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("mRNA", "Gene", "H1", "H2", "H3", "A1", "A2", "A3"))
        writer.writerow(("NM_1", "IL17A", "1", "2", "1", "100", "110", "90"))
        writer.writerow(("NM_2", "IL17A", "2", "1", "2", "80", "90", "70"))
        writer.writerow(("NM_3", "TNF", "10", "11", "9", "10", "11", "9"))


def test_normalized_rnaseq_analysis_produces_rank_compatible_genes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.tsv.gz"
    write_rnaseq(source)

    result = NormalizedRnaSeqAnalyzer().analyze(
        "GSE1",
        input_path=source,
        case_pattern=r"^A\d+$",
        control_pattern=r"^H\d+$",
        data_root=tmp_path,
        min_abs_log2_fold_change=1.0,
    )

    assert result.transcripts == 3
    assert result.genes == 2
    assert result.significant_genes == 1
    assert (result.output_directory / "case-matrix.tsv.gz").exists()
    assert (result.output_directory / "control-matrix.tsv.gz").exists()
    with result.gene_output_path.open(encoding="utf-8", newline="") as source_file:
        rows = list(csv.DictReader(source_file, delimiter="\t"))
    assert rows[0]["gene_symbol"] == "IL17A"
    assert rows[0]["probe_count"] == "2"
    assert rows[0]["direction"] == "higher_in_case"
    assert rows[0]["significant"] == "true"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["transformation"] == "log2(value + 1)"
    assert summary["case_columns"] == ["A1", "A2", "A3"]
    assert summary["case_samples"] == 3
    assert summary["control_samples"] == 3


def test_normalized_rnaseq_requires_two_columns_per_group(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.tsv.gz"
    write_rnaseq(source)

    with pytest.raises(GeoApiError, match="at least two"):
        NormalizedRnaSeqAnalyzer().analyze(
            "GSE1",
            input_path=source,
            case_pattern=r"^A1$",
            control_pattern=r"^H\d+$",
            data_root=tmp_path,
        )


def test_normalized_rnaseq_rejects_overlapping_column_patterns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.tsv.gz"
    write_rnaseq(source)

    with pytest.raises(GeoApiError, match="both groups"):
        NormalizedRnaSeqAnalyzer().analyze(
            "GSE1",
            input_path=source,
            case_pattern=r"\d$",
            control_pattern=r"\d$",
            data_root=tmp_path,
        )


def test_normalized_rnaseq_can_exclude_outlier_without_overwriting(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.tsv.gz"
    write_rnaseq(source)

    result = NormalizedRnaSeqAnalyzer().analyze(
        "GSE1",
        input_path=source,
        case_pattern=r"^A\d+$",
        control_pattern=r"^H\d+$",
        exclude_column_pattern=r"^A1$",
        analysis_label="without-A1",
        data_root=tmp_path,
    )

    assert result.output_directory.name == "rnaseq-normalized-without-A1"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["case_columns"] == ["A2", "A3"]
    assert summary["excluded_column_pattern"] == "^A1$"
