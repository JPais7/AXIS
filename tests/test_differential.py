import csv
import gzip
import json
from pathlib import Path

import pytest

from axis.analysis import DifferentialAnalyzer
from axis.ingestion import GeoApiError


def write_matrix(path: Path, rows: tuple[tuple[str, ...], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def write_annotation(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        output.write("# GEO annotation\n")
        output.write("ID\tGene symbol\tGene title\n")
        output.write("probe_up\tIL17A\tinterleukin 17A\n")
        output.write("probe_alt\tIL17A\tinterleukin 17A\n")
        output.write("probe_flat\t---\tunknown\n")


def make_analysis_files(tmp_path: Path) -> None:
    prepared = tmp_path / "GSE1" / "prepared" / "matrix"
    write_matrix(
        prepared / "case-matrix.tsv.gz",
        (
            ("ID_REF", "case1", "case2", "case3"),
            ("probe_up", "10", "11", "9"),
            ("probe_alt", "8", "9", "7"),
            ("probe_flat", "4", "4.1", "3.9"),
        ),
    )
    write_matrix(
        prepared / "control-matrix.tsv.gz",
        (
            ("ID_REF", "control1", "control2", "control3"),
            ("probe_up", "1", "2", "0"),
            ("probe_alt", "1", "2", "0"),
            ("probe_flat", "4", "4.1", "3.9"),
        ),
    )
    write_annotation(tmp_path / "platforms" / "GPL1" / "GPL1.annot.gz")


def test_analysis_maps_genes_adjusts_p_values_and_writes_summary(
    tmp_path: Path,
) -> None:
    make_analysis_files(tmp_path)

    result = DifferentialAnalyzer().analyze(
        "GSE1",
        platform="GPL1",
        data_root=tmp_path,
        alpha=0.05,
        min_abs_difference=1.0,
    )[0]

    assert result.features == 3
    assert result.mapped_features == 2
    assert result.significant_features == 2
    assert result.genes == 1
    assert result.significant_genes == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["probe_id"] == "probe_up"
    assert rows[0]["gene_symbols"] == "IL17A"
    assert rows[0]["mean_difference"] == "9"
    assert rows[0]["significant"] == "true"
    with result.gene_output_path.open(encoding="utf-8", newline="") as source:
        gene_rows = list(csv.DictReader(source, delimiter="\t"))
    assert gene_rows[0]["gene_symbol"] == "IL17A"
    assert gene_rows[0]["probe_count"] == "2"
    assert gene_rows[0]["probe_ids"] == "probe_up|probe_alt"
    assert gene_rows[0]["median_mean_difference"] == "8"
    assert gene_rows[0]["direction"] == "higher_in_case"
    assert gene_rows[0]["significant"] == "true"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["method"]["name"] == ("Welch independent two-sample t-test")
    assert summary["gene_aggregation"]["p_value"] == ("Simes combination across probes")
    assert "Exploratory" in summary["warning"]


def test_analysis_requires_platform_annotation(tmp_path: Path) -> None:
    with pytest.raises(GeoApiError, match="axis platform"):
        DifferentialAnalyzer().analyze(
            "GSE1",
            platform="GPL1",
            data_root=tmp_path,
        )


def test_analysis_requires_two_samples_per_group(tmp_path: Path) -> None:
    prepared = tmp_path / "GSE1" / "prepared" / "matrix"
    write_matrix(
        prepared / "case-matrix.tsv.gz",
        (("ID_REF", "case1"), ("probe", "1")),
    )
    write_matrix(
        prepared / "control-matrix.tsv.gz",
        (("ID_REF", "control1", "control2"), ("probe", "1", "2")),
    )
    write_annotation(tmp_path / "platforms" / "GPL1" / "GPL1.annot.gz")

    with pytest.raises(GeoApiError, match="at least two"):
        DifferentialAnalyzer().analyze(
            "GSE1",
            platform="GPL1",
            data_root=tmp_path,
        )
