import csv
import gzip
import json
from pathlib import Path

import pytest

from axis.ingestion import GeoApiError, GeoMatrixPreparer

ACCESSION = "GSE234339"


def write_matrix(path: Path, *, mismatched_header: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header_accessions = ("GSM1", "GSM2", "GSM9" if mismatched_header else "GSM3")
    lines = (
        '!Series_title\t"Example"\n'
        '!Sample_title\t"axSpA patient"\t"healthy volunteer"\t'
        '"treated patient control visit"\n'
        '!Sample_geo_accession\t"GSM1"\t"GSM2"\t"GSM3"\n'
        '!Sample_source_name_ch1\t"whole blood"\t"whole blood"\t"whole blood"\n'
        '!Sample_characteristics_ch1\t"disease: axSpA"\t'
        '"disease: healthy"\t"disease: axSpA"\n'
        '!Sample_characteristics_ch1\t"status: case"\t'
        '"status: control"\t"status: follow-up"\n'
        "!series_matrix_table_begin\n"
        f'"ID_REF"\t"{header_accessions[0]}"\t"{header_accessions[1]}"\t'
        f'"{header_accessions[2]}"\n'
        '"probe1"\t1.0\t2.0\t3.0\n'
        '"probe2"\t4.0\t5.0\t6.0\n'
        "!series_matrix_table_end\n"
    )
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        output.write(lines)


def read_gzip_tsv(path: Path) -> list[list[str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        return list(csv.reader(source, delimiter="\t"))


def test_prepare_separates_case_control_and_flags_ambiguous(
    tmp_path: Path,
) -> None:
    matrix = tmp_path / ACCESSION / f"{ACCESSION}_series_matrix.txt.gz"
    write_matrix(matrix)

    result = GeoMatrixPreparer().prepare(
        ACCESSION,
        data_root=tmp_path,
        case_pattern=r"status: case|disease: axSpA",
        control_pattern=r"status: control|healthy|control visit",
    )

    prepared = result.matrices[0]
    assert prepared.case_samples == 1
    assert prepared.control_samples == 1
    assert prepared.ambiguous_samples == 1
    assert prepared.unassigned_samples == 0
    assert prepared.feature_rows == 2
    assert read_gzip_tsv(prepared.case_matrix_path) == [
        ["ID_REF", "GSM1"],
        ["probe1", "1.0"],
        ["probe2", "4.0"],
    ]
    assert read_gzip_tsv(prepared.control_matrix_path) == [
        ["ID_REF", "GSM2"],
        ["probe1", "2.0"],
        ["probe2", "5.0"],
    ]
    manifest = prepared.sample_manifest_path.read_text(encoding="utf-8")
    assert "GSM3\tambiguous" in manifest
    summary = json.loads(
        (prepared.output_directory / "preparation.json").read_text(encoding="utf-8")
    )
    assert summary["feature_rows"] == 2


def test_prepare_rejects_invalid_regular_expression(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid case pattern"):
        GeoMatrixPreparer().prepare(
            ACCESSION,
            data_root=tmp_path,
            case_pattern="[",
            control_pattern="control",
        )


def test_prepare_include_pattern_excludes_nonmatching_samples(
    tmp_path: Path,
) -> None:
    matrix = tmp_path / ACCESSION / f"{ACCESSION}_series_matrix.txt.gz"
    write_matrix(matrix)

    result = GeoMatrixPreparer().prepare(
        ACCESSION,
        data_root=tmp_path,
        case_pattern=r"status: case",
        control_pattern=r"status: control",
        include_pattern=r"status: case|status: control",
    )

    prepared = result.matrices[0]
    assert prepared.case_samples == 1
    assert prepared.control_samples == 1
    assert prepared.excluded_samples == 1
    assert prepared.unassigned_samples == 0
    manifest = prepared.sample_manifest_path.read_text(encoding="utf-8")
    assert "GSM3\texcluded" in manifest
    assert read_gzip_tsv(prepared.case_matrix_path)[0] == ["ID_REF", "GSM1"]
    assert read_gzip_tsv(prepared.control_matrix_path)[0] == [
        "ID_REF",
        "GSM2",
    ]


def test_prepare_requires_a_downloaded_matrix(tmp_path: Path) -> None:
    with pytest.raises(GeoApiError, match="axis download"):
        GeoMatrixPreparer().prepare(
            ACCESSION,
            data_root=tmp_path,
            case_pattern="case",
            control_pattern="control",
        )


def test_prepare_rejects_mismatched_expression_columns(tmp_path: Path) -> None:
    matrix = tmp_path / ACCESSION / f"{ACCESSION}_series_matrix.txt.gz"
    write_matrix(matrix, mismatched_header=True)

    with pytest.raises(GeoApiError, match="do not match"):
        GeoMatrixPreparer().prepare(
            ACCESSION,
            data_root=tmp_path,
            case_pattern="case",
            control_pattern="control",
        )
